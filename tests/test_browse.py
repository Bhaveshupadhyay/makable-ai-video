"""Recording Chrome: the pointer and the spotlight drawn into the page, and the pauses cut out afterwards."""

import asyncio
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from shorts import browse as recorder
from shorts.browse import Cursor, Step
from shorts.media import duration

from .conftest import needs_ffmpeg, video


def step(goal: str, start: float, end: float, action: dict, did: str = "") -> Step:
    return Step(goal=goal, actions=[action], did=[did], url="https://app.example.com", start=start, end=end)


def test_the_pointer_fades_out_a_moment_after_a_click() -> None:
    said: list[str] = []  # what the page was told to run

    async def send(params: dict, session_id: str | None = None) -> dict:
        said.append(params.get("expression", ""))
        return {}

    client = SimpleNamespace(
        send=SimpleNamespace(
            Page=SimpleNamespace(addScriptToEvaluateOnNewDocument=send), Runtime=SimpleNamespace(evaluate=send)
        )
    )
    tab = SimpleNamespace(session_id="tab", cdp_client=client)
    cursor = Cursor(
        SimpleNamespace(get_or_create_cdp_session=lambda: asyncio.sleep(0, tab)), (720, 1280), glide=0, hide=0.2
    )

    def hide_in(expression: str) -> str:  # the last argument, in ms
        return re.search(r"([-\w]+)\)$", expression)[1]

    async def steps() -> float:
        await cursor.move(10, 20, click=True)
        assert said[-1].startswith("window.__cursor?.click(10, 20, ") and 150 <= int(hide_in(said[-1])) <= 200
        start = time.time()
        await cursor.faded()  # until it's hidden and faded: 0.2 s, then 0.3 s
        waited = time.time() - start
        await cursor.show()  # on the next page, or after the next action: still hidden
        assert int(hide_in(said[-1])) <= -300
        await cursor.move(30, 40, click=False)  # moving brings it back, to stay
        await cursor.show()
        assert hide_in(said[-1]) == "null"
        return waited

    assert 0.4 <= asyncio.run(steps()) <= 0.6


def test_the_spotlight_lights_an_element_then_fades_and_goes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recorder, "LIT", 0)
    said: list[tuple[str, dict]] = []  # what Chrome was asked: the method, its parameters

    def method(name: str, answer: dict | None = None):
        async def send(params: dict, session_id: str | None = None) -> dict:
            said.append((name, params))
            return answer or {}

        return send

    async def resolve(params: dict, session_id: str | None = None) -> dict:
        said.append(("resolve", params))
        if params["backendNodeId"] == 0:
            raise RuntimeError("No node with given id found")
        return {"object": {"objectId": "a button" if params["backendNodeId"] == 7 else "the element"}}

    async def call(params: dict, session_id: str | None = None) -> dict:  # CURSOR_JS's answer: whether it's lit
        said.append(("call", params))
        return {"result": {"type": "boolean", "value": params["objectId"] != "a button"}}

    client = SimpleNamespace(
        send=SimpleNamespace(
            Page=SimpleNamespace(addScriptToEvaluateOnNewDocument=method("script")),
            Runtime=SimpleNamespace(evaluate=method("evaluate"), callFunctionOn=call),
            DOM=SimpleNamespace(resolveNode=resolve),
        )
    )
    tab = SimpleNamespace(session_id="tab", cdp_client=client)
    cursor = Cursor(SimpleNamespace(get_or_create_cdp_session=lambda: asyncio.sleep(0, tab)), (720, 1280), hide=None)

    async def steps() -> float:
        await cursor.unspot()  # not lit: nothing to do
        await cursor.faded()
        assert said == []
        await cursor.spotlight(0)  # an element that's gone: no spotlight, and no failing
        await cursor.spotlight(7)  # a button: never lit
        assert not cursor.lit
        await cursor.spotlight(42)
        assert cursor.lit and said[-2:] == [
            ("resolve", {"backendNodeId": 42}),
            (
                "call",
                {
                    "functionDeclaration": "function () { return window.__cursor?.spotlight(this) ?? false }",
                    "objectId": "the element",
                    "returnByValue": True,
                },
            ),
        ]
        await cursor.unspot()
        assert said[-1] == ("evaluate", {"expression": "window.__cursor?.unspot(300)"})
        start = time.time()
        await cursor.faded()  # until it's faded out, then it's taken away
        assert said[-1] == ("evaluate", {"expression": "window.__cursor?.unspot(0)"})
        return time.time() - start

    assert 0.25 <= asyncio.run(steps()) <= 0.4


class Pointer:
    """A pointer that notes what it's asked to do, in order, with what the action did."""

    def __init__(self) -> None:
        self.did: list = []
        self.typing: list[tuple[float, float]] = []

    async def spotlight(self, node: int) -> None:
        self.did.append(("spotlight", node))

    async def move(self, x: float, y: float, *, click: bool) -> None:
        self.did.append(("move", x, y))

    async def unspot(self) -> None:
        self.did.append("unspot")

    async def show(self) -> None:
        pass

    async def faded(self) -> None:
        self.did.append("faded")


def test_the_spotlight_goes_as_a_click_clicks_and_once_typing_is_done(monkeypatch: pytest.MonkeyPatch) -> None:
    pointer = Pointer()

    class Tools:  # browser-use's, doing the action
        async def act(self, action, browser_session, **kwargs):
            pointer.did.append(f"{next(iter(action.model_dump()))}!")

    monkeypatch.setitem(sys.modules, "browser_use", SimpleNamespace(Tools=Tools))
    monkeypatch.setattr(recorder, "_target", lambda params, session: asyncio.sleep(0, (10, 20, 7)))
    tools = recorder.tools_with(pointer)

    def act(name: str, **options) -> list:
        pointer.did.clear()
        action = SimpleNamespace(model_dump=lambda **_: {name: {"index": 3}})
        asyncio.run(tools.act(action, browser_session=None, **options))
        return pointer.did

    lit, there = ("spotlight", 7), ("move", 10, 20)
    assert act("click", spotlight=True) == [lit, there, "unspot", "click!", "unspot", "faded"]
    assert act("input", spotlight=True) == [lit, there, "input!", "unspot", "faded"]
    assert act("click") == [there, "unspot", "click!", "unspot", "faded"]  # unspot: nothing to fade
    assert len(pointer.typing) == 1  # when the input typed, to play that fast


@needs_ffmpeg
def test_typing_plays_fast_only_while_it_types(tmp_path: Path) -> None:
    recording = video(tmp_path / "raw.mp4", 6)
    typed = step("Describe the site", 2.0, 5.0, {"input": {"index": 3, "text": "A bakery"}})
    steps = [step("Click", 1.0, 2.0, {"click": {"index": 4}}), typed]

    # The step says when it typed: only that plays fast. Kept: 0.4-5 s (each step from 0.6 s before it).
    typed.typing = [[3.0, 5.0]]
    out, timed = recorder.cut_pauses(recording, steps, tmp_path / "tight.mp4")
    assert [(step.start, step.end, step.typing) for step in timed] == [(0.6, 1.6, []), (1.6, 3.1, [[2.6, 3.1]])]
    assert abs(duration(out) - 3.1) < 0.05

    typed.typing = []  # it doesn't say: the whole step plays fast
    out, timed = recorder.cut_pauses(recording, steps, tmp_path / "tight.mp4")
    assert (timed[1].start, timed[1].end) == (1.6, 2.35)


def test_a_browser_command_goes_to_its_own_python_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from shorts.__main__ import browse_elsewhere
    from shorts.stages.base import NotReady

    monkeypatch.setenv("SHORTS_BROWSE_PYTHON", sys.executable)
    monkeypatch.setenv("SHORTS_BROWSE_SENT", "1")  # as that Python's command finds it
    with pytest.raises(NotReady, match="hasn't browser-use either"):
        browse_elsewhere()
