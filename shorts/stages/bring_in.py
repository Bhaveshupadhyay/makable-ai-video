"""import: files made elsewhere, brought in under their names in the contract, in place of a stage's.

    python -m shorts import RUN footage --name makable recordings/makable-tight.mp4   (and its .steps.json)
    python -m shorts import RUN script drafts/script.json                 the script Claude wrote
    python -m shorts import RUN intro gemini_generated_video.mp4          Omni's clip, filmed elsewhere
    python -m shorts import RUN outro gemini_generated_outro.mp4          and the outro's
    python -m shorts import RUN narration download*.wav                   one audio file per scene

The script is always brought in. Bringing in another product sets run.json so that it's yours from then on
(`narrator: "import"`, say), and the pipeline asks for it again instead of making it. Imported narration is out of date when its scene's text
changes, as speech for it would be.

Narration files are put in order by the numbers in their names (download.wav, download (1).wav, ...,
download (10).wav, as browsers name repeated downloads), or kept as given with `as_given`. A file that's the
same as one before it, downloaded twice, is left out.

A script is checked against the run's footage first (`check_script`), and refused if the video can't be made
from it.
"""

import hashlib
import json
import re
import shutil
from pathlib import Path

from ..media import duration, ffmpeg
from ..run import (
    FILMED_INTRO,
    FILMED_OUTRO,
    SCRIPT,
    Run,
    Settings,
    fingerprint,
    footage_file,
    narration_file,
    steps_file,
    writing,
)
from ..script import Script, check, recording_length
from .base import NotReady, Stage, execute, read_script
from .record import RecordFootage

SINGLE = {"script": SCRIPT, "intro": FILMED_INTRO, "outro": FILMED_OUTRO}
SETTING = {"intro": "intro", "outro": "outro", "narration": "narrator"}  # what run.json calls each product's maker
PRODUCTS = ("footage", *SINGLE, "narration")


def in_order(files: list[Path]) -> list[Path]:
    """By the numbers in their names: download.wav, download (1).wav, ..., download (10).wav."""

    def key(path: Path) -> list[int | str]:
        return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.stem)]

    return sorted(files, key=key)


def without_copies(files: list[Path]) -> list[Path]:
    """`files` without any that's the same as one before it."""
    kept: list[Path] = []
    seen: dict[bytes, Path] = {}
    for path in files:
        first = seen.setdefault(hashlib.sha256(path.read_bytes()).digest(), path)
        if first is path:
            kept.append(path)
        else:
            print(f"Leaving out {path.name}: it's the same as {first.name}")
    return kept


class Import(Stage):
    """A product you bring in: `plan` says what the files should be, and `make` copies `files` in."""

    name = "import"

    def __init__(self, product: str, files: list[Path] | None = None) -> None:
        self.product = product
        self.files = files

    def requires(self, settings: Settings) -> tuple[str, ...]:
        return ("script",) if self.product == "narration" else ()  # one file for each of its scenes

    def plan(self, run: Run) -> dict[str, str]:
        if self.product == "narration":
            return {
                narration_file(index): fingerprint("import", scene.text)
                for index, scene in enumerate(read_script(run).scenes)
            }
        return {SINGLE[self.product]: fingerprint("import")}

    def make(self, run: Run, paths: list[str]) -> None:
        if self.files is None:
            raise NotReady(f"bring it in: python -m shorts import {run.folder} {self.product} FILE ...")
        sources = dict(zip(self.plan(run), self.files, strict=True))
        for path in paths:
            print(f"{sources[path]} -> {path}")
            with writing(run.path(path)) as out:
                if self.product == "narration":
                    ffmpeg("-i", sources[path], "-vn", "-c:a", "pcm_s16le", out)  # any audio file, as WAV
                else:
                    shutil.copyfile(sources[path], out)


def footage_lengths(run: Run) -> tuple[dict[str, float | None], set[str]]:
    """Each recording in run.json, by name, with how long it is (None: not known yet), and those with steps.

    Footage that isn't copied in yet is measured where it'll be copied from.
    """
    lengths: dict[str, float | None] = {}
    timed: set[str] = set()
    for name, source in run.settings().footage.items():
        video, steps = run.path(footage_file(name)), run.path(steps_file(name))
        if not video.exists():
            video = run.resolve(source)
            steps = video.with_suffix(".steps.json")  # where browse.record_task saves them
        if steps.exists():
            timed.add(name)
        if video.exists():
            lengths[name] = duration(video)
        else:
            lengths[name] = recording_length(json.loads(steps.read_text())) if steps.exists() else None
    return lengths, timed


def check_script(run: Run, script: Script) -> tuple[list[str], list[str]]:
    """`script.check` against the run's footage: errors (the video can't be made from it) and warnings."""
    return check(script, *footage_lengths(run))


def bring_in(run: Run, product: str, files: list[Path], *, name: str | None = None, as_given: bool = False) -> None:
    """Brings `files` in as `product` (see the module's docstring), and makes run.json say they're yours."""
    if product not in PRODUCTS:
        raise ValueError(f"No product {product!r}: one of {', '.join(PRODUCTS)}")
    files = [Path(file).expanduser() for file in files]
    for file in files:
        if not file.is_file():
            raise FileNotFoundError(file)
    settings = run.settings()
    if product == "footage":
        if name is None or len(files) != 1:
            raise ValueError("Bring footage in one recording at a time, with its name: --name NAME FILE")
        settings.footage[name] = run.relative(files[0])
        run.save_settings(settings)
        execute(run, RecordFootage())
        return
    if product == "narration":
        files = without_copies(files if as_given else in_order(files))
        scenes = read_script(run).scenes
        if len(files) != len(scenes):
            raise ValueError(f"The script has {len(scenes)} scenes, but there are {len(files)} audio files")
        for index, (scene, file) in enumerate(zip(scenes, files, strict=True), 1):
            print(f"Scene {index}: {file.name}: {scene.text}")
    elif len(files) != 1:
        raise ValueError(f"Bring in one file as the {product}")
    if product == "script":  # checked before it replaces the one there
        errors, warnings = check_script(run, Script.model_validate_json(files[0].read_text()))
        for warning in warnings:
            print(f"Warning: {warning}")
        if errors:
            raise ValueError("the script can't be used as it is:\n" + "\n".join(f"  {error}" for error in errors))
    if product in SETTING:
        setattr(settings, SETTING[product], "import")
        run.save_settings(settings)
    execute(run, Import(product, files), force=True)
