"""record: the footage. A file named in run.json is copied in (with its steps, if browser-use made it), and a
page's URL is recorded by Playwright, scrolling down it in a 720x1280 window.

browser-use's recordings come from `record_with_browser_use.ipynb` (its packages clash with the voices'): name
the file it made in run.json, and this copies it with its .steps.json.
"""

import shutil

from ..run import Run, Settings, file_hash, fingerprint, footage_file, steps_file, writing
from .base import NotReady, Stage


def is_url(source: str) -> bool:
    return "://" in source


class RecordFootage(Stage):
    name = "record"
    product = "footage"
    extra = "record"
    where = "pip install 'makable-shorts[record]' && playwright install chromium (or makable_shorts.ipynb in Colab)"

    def packages(self, settings: Settings) -> list[str]:
        return ["playwright"] if any(is_url(source) for source in settings.footage.values()) else []

    def plan(self, run: Run) -> dict[str, str]:
        settings = run.settings()
        if not settings.footage:
            raise NotReady("run.json names no footage: python -m shorts new RUN --footage NAME=FILE_OR_URL")
        plan = {}
        for name, source in settings.footage.items():
            if is_url(source):
                plan[footage_file(name)] = fingerprint("record", source)
                continue
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
            if is_url(source):
                if footage_file(name) in paths:
                    import asyncio

                    from ..footage import record_page

                    print(f"Recording {source}")
                    with writing(run.path(footage_file(name))) as out:
                        asyncio.run(record_page(source, out))
                continue
            video = run.resolve(source)
            for path, original in ((footage_file(name), video), (steps_file(name), video.with_suffix(".steps.json"))):
                if path in paths:
                    print(f"Copying {original} to {path}")
                    with writing(run.path(path)) as out:
                        shutil.copyfile(original, out)
