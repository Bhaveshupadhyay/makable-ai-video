"""browse: footage recorded from a task in plain words. browser-use's agent does the task in Chrome while the screen
is recorded (`shorts.browse`). The model's pauses are cut out, and the tight recording comes into the run as footage,
with its steps, for the script to be written from.

    python -m shorts browse RUN --url https://app.example.com --name demo --task task.md [--signed-in]
        [--window 720x1280] [--max-steps 60] [--model google:gemini-3.6-flash]
        [--fallback google:gemini-3-flash-preview]

With --signed-in, it records in the profile `python -m shorts signin` signed in to the site (`shorts.signin`).

It writes RUN/recordings/<name>.mp4 (the run in real time), <name>-tight.mp4 (without the pauses, the footage),
each with its .steps.json, and <name>.browse.json (the task, the page and the models, to record it again).

It's not a stage the orchestrator runs: the agent may not finish its task, or show something else, so whoever asked
for the recording (the make-video skill) looks at it, and may record it again with a better task. browser-use pins
its own packages, so it runs in an environment of its own: `python -m shorts browse` goes to SHORTS_BROWSE_PYTHON's
when this one hasn't browser-use.
"""

import asyncio
import json
from pathlib import Path

from ..run import Run
from .bring_in import bring_in


def outcome(steps: list) -> tuple[bool | None, str]:
    """Whether the agent said it did the task, and its final report (None and "" if it never finished)."""
    for step in reversed(steps):
        for action, did in zip(step.actions, step.did, strict=False):
            if "done" in action:
                return action["done"].get("success"), did or ""
    return None, ""


def browse(
    run: Run,
    name: str,
    task: str,
    *,
    url: str,
    signed_in: bool = False,
    window: tuple[int, int] = (720, 1280),
    max_steps: int = 60,
    model: str,
    fallback: str | None = None,
) -> Path:
    """Records `task` as the footage `name` (see the module's docstring), and returns the tight recording."""
    from ..browse import chat_model, cut_pauses, record_task
    from ..signin import recording_profile

    profile = recording_profile(url) if signed_in else None

    llm, backup = chat_model(model), None
    if fallback:
        try:
            backup = chat_model(fallback)
        except ValueError as error:
            print(f"Warning: no fallback model ({error}): recording with {model} alone")
            fallback = None
    folder = run.path("recordings")
    folder.mkdir(parents=True, exist_ok=True)
    print(f"Recording {name!r} from {url}{' signed in' if signed_in else ''}, with {model} (fallback: {fallback})")
    video, steps = asyncio.run(
        record_task(
            task,
            folder / f"{name}.mp4",
            llm,
            fallback=backup,
            url=url,
            size=window,
            profile=profile,
            max_steps=max_steps,
        )
    )
    tight, tight_steps = cut_pauses(video, steps, folder / f"{name}-tight.mp4")
    asked = {"task": task, "url": url, "signed_in": signed_in, "window": "x".join(map(str, window))}
    asked |= {"max_steps": max_steps, "model": model}
    (folder / f"{name}.browse.json").write_text(json.dumps({**asked, "fallback": fallback}, indent=2) + "\n")
    bring_in(run, "footage", [tight], name=name)

    success, report = outcome(tight_steps)
    said = {True: "it says it did the task", False: "it says it couldn't", None: "it ran out of steps"}[success]
    print(f"{len(tight_steps)} steps, {tight_steps[-1].end if tight_steps else 0:.1f} s: {said}")
    print(report)
    return tight
