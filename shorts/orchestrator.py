"""The orchestrator: what's made, what's next, and each stage run in a process of its own.

It knows the stages only by what they make and read (`shorts.stages`), and never imports their packages. A
stage it runs is `python -m shorts <stage> RUN`, in the Python set for its packages (SHORTS_<EXTRA>_PYTHON, such
as SHORTS_VOICE_PYTHON=~/chatterbox-env/bin/python), or this one. What it can't run here (a stage whose
packages this machine doesn't have, a paid one, what you bring in) it names, with where it runs, and stops.
"""

import os
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .run import FINAL, PRODUCTS, Run
from .stages import STAGES, Import, NotReady, Stage, execute, producer, states
from .stages.base import MISSING, TO_MAKE

PACKAGE_ROOT = Path(__file__).resolve().parent.parent  # the folder with shorts/ in it, for other Pythons


@dataclass
class Status:
    """Where a product is."""

    product: str
    stage: Stage  # what makes it
    files: dict[str, str] = field(default_factory=dict)  # each planned file's state
    waiting: str = ""  # why it can't be made yet
    needed: bool = True  # whether the video is made from it, with the run's settings

    @property
    def todo(self) -> list[str]:
        return [path for path, state in self.files.items() if state in TO_MAKE]

    @property
    def ready(self) -> bool:
        return not self.needed or (not self.waiting and not self.todo)

    def summary(self) -> str:
        if not self.needed:
            return "not needed, with these settings"
        if self.waiting:
            return self.waiting
        if not self.files:
            return "nothing to make"
        counts = Counter(self.files.values())
        if len(self.files) == 1:
            return next(iter(counts))
        return ", ".join(f"{count} {state}" for state, count in counts.items())


def status(run: Run) -> list[Status]:
    """Every product's status, in the order they're made."""
    settings = run.settings()
    stages = {product: producer(run, product) for product in PRODUCTS}
    needed: set[str] = set()
    wanted = ["video"]
    while wanted:  # what the video is made from, and what that's made from
        product = wanted.pop()
        if product not in needed:
            needed.add(product)
            wanted += stages[product].requires(settings)
    result: list[Status] = []
    ready: dict[str, bool] = {}
    for product in PRODUCTS:
        stage = stages[product]
        if product not in needed:
            result.append(Status(product, stage, needed=False))
            ready[product] = True
            continue
        try:
            entry = Status(product, stage, states(run, product, stage.plan(run)))
        except NotReady as reason:
            entry = Status(product, stage, waiting=str(reason))
        unready = [need for need in stage.requires(settings) if not ready[need]]
        if unready:  # before anything it'd say itself: it may only be missing what they make
            entry.waiting = f"waiting for the {', '.join(unready)}"
        ready[product] = entry.ready
        result.append(entry)
    return result


def advice(run: Run, entry: Status) -> str:
    """The command that makes a product."""
    if isinstance(entry.stage, Import):
        return f"bring it in: python -m shorts import {run.folder} {entry.product} FILE ..."
    command = f"python -m shorts {entry.stage.name} {run.folder}"
    return f"{command} ({entry.stage.cost}; or run --paid)" if entry.stage.cost else command


def python_for(stage: Stage) -> str:
    """The Python that runs a stage: SHORTS_<EXTRA>_PYTHON if it's set, or this one."""
    return os.environ.get(f"SHORTS_{stage.extra.upper()}_PYTHON", "") or sys.executable


def missing_packages(python: str, packages: list[str]) -> list[str]:
    """Which of `packages` a Python can't import."""
    if not packages:
        return []
    check = "import importlib.util, sys; print(*(m for m in sys.argv[1:] if importlib.util.find_spec(m) is None))"
    result = subprocess.run([python, "-c", check, *packages], capture_output=True, text=True)
    return result.stdout.split() if result.returncode == 0 else packages


def run_all(run: Run, *, paid: bool = False) -> bool:
    """Makes what's missing or out of date, in order, each stage in a process of its own, until the video is up
    to date (True) or a stage can't run here (False, saying where it runs)."""
    tried: set[str] = set()
    while True:
        entry = next((entry for entry in status(run) if not entry.ready), None)
        if entry is None:
            print(f"{run.path(FINAL)} is up to date")
            return True
        stage = entry.stage
        if entry.waiting:
            print(f"The {entry.product}: {entry.waiting}")
            return False
        if isinstance(stage, Import) or (stage.cost and not paid):
            print(f"The {entry.product}: {entry.summary()}. Next: {advice(run, entry)}")
            return False
        if stage.name in tried:
            print(f"{stage.name} ran, but the {entry.product} is still {entry.summary()}")
            return False
        python = python_for(stage)
        missing = missing_packages(python, stage.packages(run.settings()))
        if missing:
            print(f"The {entry.product}: {entry.summary()}. Next: {advice(run, entry)}")
            print(f"  It needs {', '.join(missing)}, which {python} doesn't have: {stage.where}")
            return False
        print(f"== {stage.name}: the {entry.product}, {entry.summary()}", flush=True)
        paths = [str(PACKAGE_ROOT), *filter(None, [os.environ.get("PYTHONPATH")])]
        environment = {**os.environ, "PYTHONPATH": os.pathsep.join(paths)}
        if subprocess.run([python, "-m", "shorts", stage.name, str(run.folder)], env=environment).returncode:
            print(f"{stage.name} failed")
            return False
        tried.add(stage.name)


def run_stage(run: Run, name: str, *, force: bool = False) -> list[str]:
    """Runs one stage here, in this process: what `python -m shorts <stage> RUN` does."""
    stage = STAGES[name]
    if producer(run, stage.product).name != stage.name:
        print(f"The {stage.product} is yours, brought in (run.json says so): {name} leaves it as it is")
        return []
    entries = {entry.product: entry for entry in status(run)}
    for need in stage.requires(run.settings()):
        entry = entries[need]
        if (entry.waiting and not entry.files) or MISSING in entry.files.values():
            raise NotReady(f"{name} needs the {need}, which isn't made ({entry.summary()}): {advice(run, entry)}")
        if not entry.ready:
            print(f"Going on with the {need} as it is, though it's {entry.summary()}")
    return execute(run, stage, force=force)
