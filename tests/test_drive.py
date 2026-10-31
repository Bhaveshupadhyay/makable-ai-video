import argparse
import asyncio
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from shorts import browse as recorder
from shorts import drive
from shorts.__main__ import ACTIONS
from shorts.__main__ import drive as command
from shorts.browse import save_steps
from shorts.orchestrator import PACKAGE_ROOT
from shorts.run import Run, footage_file, steps_file
from shorts.stages.base import NotReady

from .conftest import needs_ffmpeg, video


def test_each_command_asks_for_one_of_browser_uses_actions() -> None:
    def asked(step: str, **args) -> tuple[str, dict]:
        return ACTIONS[step](argparse.Namespace(**args))

    assert asked("click", number=12) == ("click", {"index": 12})
    assert asked("type", number=5, text="A bakery", add=False) == (
        "input",
        {"index": 5, "text": "A bakery", "clear": True},
    )
    assert asked("scroll", direction="up", pages=0.5, number=None) == ("scroll", {"down": False, "pages": 0.5})
    assert asked("scroll", direction="down", pages=1.0, number=7) == (
        "scroll",
        {"down": True, "pages": 1.0, "index": 7},
    )
    assert asked("tab", tab="4666") == ("switch", {"tab_id": "4666"})
    assert asked("act", action_name="go_back", params="{}") == ("go_back", {})


def test_a_click_or_a_type_can_ask_for_the_spotlight(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, dict]] = []
    monkeypatch.setattr(drive, "send", lambda run, name, step, **args: sent.append((step, args)) or "Did it")
    command(run, argparse.Namespace(step="click", name="demo", number=4, goal="Open the menu", spotlight=True))
    command(run, argparse.Namespace(step="keys", name="demo", keys="Enter", goal=None))
    assert sent == [
        ("act", {"action": "click", "params": {"index": 4}, "goal": "Open the menu", "spotlight": True}),
        ("act", {"action": "send_keys", "params": {"keys": "Enter"}}),
    ]

    asked = {}

    async def act(action: dict, browser_session, spotlight: bool = False) -> SimpleNamespace:
        asked.update(action=action, spotlight=spotlight)
        return SimpleNamespace(error=None, extracted_content="Clicked", long_term_memory=None)

    monkeypatch.setattr(drive, "SETTLE", 0)
    driver = drive.Driver(run, "demo", "https://makable.tech")
    driver.browser = SimpleNamespace(
        session=SimpleNamespace(get_current_page_url=lambda: asyncio.sleep(0, "https://makable.tech/"))
    )
    driver.tools, driver.action, driver.look = SimpleNamespace(act=act), dict, lambda: asyncio.sleep(0, "The page")
    assert asyncio.run(driver.handle("act", sent[0][1])) == (True, "Clicked\n\nThe page")
    assert asked == {"action": {"click": {"index": 4}}, "spotlight": True}


class Answering:
    """A driver without Chrome: it says what it was asked."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, dict]] = []

    async def open(self) -> None:
        pass

    async def handle(self, command: str, args: dict) -> tuple[bool, str]:
        self.asked.append((command, args))
        if command == "act" and args["action"] == "click" and args["params"]["index"] == 99:
            return False, "No element 99"
        return True, f"Did {command}"


def serving(driver: Answering, where: Path, **options) -> threading.Thread:
    thread = threading.Thread(target=lambda: asyncio.run(drive.serve(driver, where, **options)))
    thread.start()
    deadline = time.time() + 10
    while not where.exists():
        assert time.time() < deadline, "the driver never listened"
        time.sleep(0.05)
    return thread


def test_a_driver_answers_its_commands_one_at_a_time_until_its_stopped(run: Run) -> None:
    driver, where = Answering(), drive.driving_file(run, "demo")
    where.parent.mkdir(parents=True)
    thread = serving(driver, where)

    assert drive.send(run, "demo", "look") == "Did look"
    assert drive.send(run, "demo", "act", action="click", params={"index": 4}, goal="Open the menu") == "Did act"
    with pytest.raises(NotReady, match="No element 99"):  # an action that failed: the command fails
        drive.send(run, "demo", "act", action="click", params={"index": 99})
    with pytest.raises(NotReady, match="nothing's recording 'other'"):
        drive.send(run, "other", "look")

    assert drive.send(run, "demo", "stop", report="All shown.", success=True) == "Did stop"
    thread.join(10)
    assert not thread.is_alive() and not where.exists()
    assert driver.asked[1] == ("act", {"action": "click", "params": {"index": 4}, "goal": "Open the menu"})
    assert driver.asked[-1] == ("stop", {"report": "All shown.", "success": True})


def test_a_driver_wants_its_token(run: Run) -> None:
    where = drive.driving_file(run, "demo")
    where.parent.mkdir(parents=True)
    thread = serving(Answering(), where)
    address = json.loads(where.read_text())
    where.write_text(json.dumps({**address, "token": "guessed"}))
    with pytest.raises(NotReady, match="Wrong token"):
        drive.send(run, "demo", "look")
    where.write_text(json.dumps(address))
    drive.send(run, "demo", "stop")
    thread.join(10)


def test_a_driver_sent_nothing_stops_by_itself(run: Run) -> None:
    driver, where = Answering(), drive.driving_file(run, "demo")
    where.parent.mkdir(parents=True)
    serving(driver, where, idle=0.2).join(10)
    assert driver.asked == [("stop", {"report": "Stopped by itself: no command for 0 minutes.", "success": False})]
    assert not where.exists()


def test_start_says_why_the_driver_didnt_start(run: Run, tmp_path: Path) -> None:
    environment = {**os.environ, "PYTHONPATH": str(PACKAGE_ROOT), "SHORTS_HOME": str(tmp_path / "home")}
    # Signed in to a site nobody's signed in to, the driver stops before it opens Chrome.
    with pytest.raises(NotReady, match="the driver stopped before Chrome opened(.|\n)*shorts signin --url"):
        drive.start(run, "demo", "https://app.example.com", True, (720, 1280), sys.executable, environment)
    assert not drive.driving_file(run, "demo").exists()


@needs_ffmpeg
def test_stop_brings_the_recording_in_with_its_steps(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    origin = 1000.0
    browser = SimpleNamespace(
        session=SimpleNamespace(get_current_page_url=lambda: asyncio.sleep(0, "https://makable.tech/")),
        since=lambda at: round(at - origin, 2),
        clicks=lambda start, end: [[round(at - origin, 2), 10, 20] for at in (1002.5,) if start <= at <= end],
        typing=lambda start, end: [],
    )

    async def close_browser(browser, out: Path) -> Path:
        out.parent.mkdir(parents=True, exist_ok=True)
        return video(out, 6)

    def cut_pauses(recording: Path, steps: list, out: Path):
        shutil.copyfile(recording, out)
        save_steps(out, steps)
        return out, steps

    monkeypatch.setattr(recorder, "close_browser", close_browser)
    monkeypatch.setattr(recorder, "cut_pauses", cut_pauses)
    driver = drive.Driver(run, "demo", "https://makable.tech", signed_in=True)
    driver.browser = browser
    driver.notes = [
        drive.Note("Open the menu", [{"click": {"index": 4}}], ["Clicked"], "https://makable.tech/", 1002.0, 1003.0),
        drive.Note(
            "Wait for it", [{"wait": {"seconds": 30}}], ["Waited 30 s"], "https://makable.tech/", 1003.0, 1033.0
        ),
    ]
    said = asyncio.run(driver.stop("It showed the site.", True))

    assert said.startswith("3 steps") and "in as the footage 'demo'" in said
    assert run.settings().footage == {"demo": "recordings/demo-tight.mp4"}
    steps = json.loads(run.path(steps_file("demo")).read_text())
    assert [(step["goal"], step["start"], step["end"], step["clicks"]) for step in steps[:2]] == [
        ("Open the menu", 2.0, 3.0, [[2.5, 10, 20]]),
        ("Wait for it", 3.0, 33.0, []),
    ]
    assert run.path(footage_file("demo")).exists()
    assert (steps[-1]["actions"], steps[-1]["did"]) == (
        [{"done": {"text": "It showed the site.", "success": True}}],
        ["It showed the site."],
    )
    record = json.loads(run.path("recordings/demo.browse.json").read_text())
    assert (record["driver"], record["signed_in"]) == ("python -m shorts drive", True)


def test_a_hold_is_kept_whole_and_a_wait_only_where_the_page_changes() -> None:
    def kept(action: dict) -> bool:
        step = recorder.Step(goal="", actions=[action], did=[""], url="", start=0, end=3)
        return not recorder._waits(step)

    assert kept({"hold": {"seconds": 3}})
    assert not kept({"wait": {"seconds": 30, "until": "Live preview"}})
