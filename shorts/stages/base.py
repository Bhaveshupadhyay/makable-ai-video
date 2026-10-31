"""What every stage is: what it makes, what it reads, and how it plans and makes its files.

A stage plans before it makes. `plan` names its product's files (by their names in the contract, `shorts.run`)
and fingerprints what each would be made from now, without loading anything heavy, so every stage's status
can be worked out on any machine. `make` writes the files it's given. Stage modules import their heavy
packages (google-genai, httpx, Pillow) inside `make` only.
"""

from pathlib import Path

from .. import COMMAND
from ..run import SCRIPT, Made, Record, Run, Settings, file_hash
from ..script import Script

# The states of a planned file.
CURRENT = "up to date"
EDITED = "edited by hand"  # changed since its stage wrote it: kept as it is
ELSEWHERE = "made elsewhere"  # there, with no record of what made it: used as it is
MISSING = "missing"
STALE = "out of date"  # what it would be made from now isn't what it was made from
TO_MAKE = {MISSING, STALE}


class NotReady(Exception):
    """A stage can't plan or make its files yet: something they're made from isn't there."""


class Stage:
    """One stage: a program of its own, run as `python -m shorts <name> RUN`."""

    name = ""  # its command
    product = ""  # what it makes: one of run.PRODUCTS
    needs: tuple[str, ...] = ()  # the products it reads (`requires` says which, when the settings decide)
    extra = ""  # its packages: pip install 'makable-shorts[<extra>]'
    where = ""  # where it runs, for a machine without them
    cost = ""  # what each run costs, for a paid stage: `python -m shorts run` never runs one on its own

    def by(self, settings: Settings) -> str:
        """What the stage calls itself in a file's record."""
        return self.name

    def requires(self, settings: Settings) -> tuple[str, ...]:
        """The products it reads, with these settings."""
        return self.needs

    def extra_for(self, settings: Settings) -> str:
        """Its packages' extra, with these settings: speak's is Kokoro's, for a run Kokoro narrates."""
        return self.extra

    def packages(self, settings: Settings) -> list[str]:
        """The modules it imports, to check whether a Python can run it."""
        return []

    def plan(self, run: Run) -> dict[str, str]:
        """Its product's files (paths in the run folder), each with a fingerprint of what it'd be made from."""
        raise NotImplementedError

    def make(self, run: Run, paths: list[str]) -> None:
        """Writes the files in `paths` (some of what `plan` names)."""
        raise NotImplementedError


def read_script(run: Run) -> Script:
    if not run.path(SCRIPT).exists():
        raise NotReady(f"{SCRIPT} isn't written yet")
    return run.script()


def voice_sample(run: Run, settings: Settings) -> Path:
    if settings.voice is None:
        raise NotReady(
            f"run.json has no voice sample: {COMMAND} new RUN --voice SAMPLE ({COMMAND} me --voice keeps one for new runs)"
        )
    sample = run.resolve(settings.voice)
    if not sample.exists():
        raise NotReady(f"the voice sample {sample} isn't there")
    return sample


def states(run: Run, product: str, plan: dict[str, str]) -> dict[str, str]:
    """Each planned file's state, from the product's record."""
    record = run.record(product)
    result = {}
    for path, source in plan.items():
        file, made = run.path(path), record.files.get(path)
        if not file.exists():
            result[path] = MISSING
        elif made is None:
            result[path] = ELSEWHERE
        elif file_hash(file) != made.sha256:
            result[path] = EDITED
        elif made.source != source:
            result[path] = STALE
        else:
            result[path] = CURRENT
    return result


def execute(run: Run, stage: Stage, *, force: bool = False) -> list[str]:
    """Makes the stage's files that are missing or out of date (all of them, edited ones too, with `force`),
    and records what they were made from. Returns the files it made."""
    settings = run.settings()
    plan = stage.plan(run)
    todo = [path for path, state in states(run, stage.product, plan).items() if force or state in TO_MAKE]
    if not todo:
        print(f"{stage.product}: {CURRENT}")
        return []

    def written(path: str) -> int | None:
        file = run.path(path)
        return file.stat().st_mtime_ns if file.exists() else None

    before = {path: written(path) for path in plan}
    stage.make(run, todo)
    record = run.record(stage.product)
    files = {path: made for path, made in record.files.items() if path in plan}  # forget what's no longer planned
    for path in plan:  # what it was asked for, and anything else it wrote over
        if path in todo or written(path) != before[path]:
            if not run.path(path).exists():
                raise RuntimeError(f"{stage.name} didn't write {path}")
            files[path] = Made(by=stage.by(settings), source=plan[path], sha256=file_hash(run.path(path)))
    run.save_record(stage.product, Record(files=files))
    return todo
