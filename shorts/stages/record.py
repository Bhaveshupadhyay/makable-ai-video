"""record: the footage. Each recording named in run.json is copied in, with its steps if browser-use made it
(`python -m shorts browse` records one and names it there).
"""

import shutil

from .. import COMMAND
from ..run import Run, file_hash, fingerprint, footage_file, steps_file, writing
from .base import NotReady, Stage


class RecordFootage(Stage):
    name = "record"
    product = "footage"
    where = "anywhere"  # no packages of its own

    def plan(self, run: Run) -> dict[str, str]:
        settings = run.settings()
        if not settings.footage:
            raise NotReady(
                f"run.json names no footage: {COMMAND} drive RUN start --url URL, or new RUN --footage NAME=FILE"
            )
        plan = {}
        for name, source in settings.footage.items():
            video = run.resolve(source)
            if not video.exists():
                raise NotReady(f"the footage {name!r} is {video}, which isn't there")
            plan[footage_file(name)] = fingerprint("copy", file_hash(video))
            steps = video.with_suffix(".steps.json")  # where browse.record_task saves them
            if steps.exists():
                plan[steps_file(name)] = fingerprint("copy", file_hash(steps))
        return plan

    def make(self, run: Run, paths: list[str]) -> None:
        for name, source in run.settings().footage.items():
            video = run.resolve(source)
            for path, original in ((footage_file(name), video), (steps_file(name), video.with_suffix(".steps.json"))):
                if path in paths:
                    print(f"Copying {original} to {path}")
                    with writing(run.path(path)) as out:
                        shutil.copyfile(original, out)
