"""Recording footage from a task: browser-use's model, picked by name, and the recording brought into the run."""

import asyncio
import json
import re
import shutil
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from shorts import browse as recorder
from shorts.__main__ import load_env
from shorts.browse import Cursor, Step, chat_model, save_steps
from shorts.media import duration
from shorts.run import Run, footage_file, steps_file
from shorts.stages.browse import browse, outcome

from .conftest import needs_ffmpeg, video


@pytest.fixture
def browser_use(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """A stand-in for browser-use: its chat classes keep what they were made with."""
    module = ModuleType("browser_use")
    for name in ("ChatGoogle", "ChatAnthropic", "ChatOpenAI"):
        setattr(module, name, type(name, (), {"__init__": lambda self, **options: setattr(self, "options", options)}))
    monkeypatch.setitem(sys.modules, "browser_use", module)
    for key in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL", "GOOGLE_CLOUD_PROJECT"):
        monkeypatch.delenv(key, raising=False)
    return module


def test_a_model_by_provider_and_name(browser_use: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    gemini = chat_model("google:gemini-3.6-flash")
    assert type(gemini).__name__ == "ChatGoogle"
    assert gemini.options == {
        "model": "gemini-3.6-flash",
        "api_key": "g",
        "http_options": {"timeout": 120000},
        "max_retries": 2,
    }

    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    claude = chat_model("anthropic:claude-sonnet-5-5", timeout=60, retries=3)
    assert claude.options == {"model": "claude-sonnet-5-5", "api_key": "a", "timeout": 60, "max_retries": 3}

    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    assert chat_model("openai:some/model").options["base_url"] == "https://openrouter.ai/api/v1"

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "p")
    vertex = chat_model("vertex:gemini-3.6-flash").options
    assert (vertex["vertexai"], vertex["project"], vertex["location"]) == (True, "p", "global")


def test_what_a_model_name_needs(browser_use: ModuleType) -> None:
    with pytest.raises(ValueError, match="provider:model, with provider one of google, vertex, anthropic, openai"):
        chat_model("gemini-3.6-flash")
    with pytest.raises(ValueError, match="Set GEMINI_API_KEY"):
        chat_model("google:gemini-3.6-flash")


def test_env_file_fills_in_what_the_environment_doesnt_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHORTS_A", "from the environment")
    monkeypatch.delenv("SHORTS_B", raising=False)
    monkeypatch.delenv("SHORTS_C", raising=False)
    (tmp_path / ".env").write_text(
        "# a comment\nSHORTS_A=from the file\nexport SHORTS_B='quoted'\nSHORTS_C=\nnot a line\n"
    )
    load_env(tmp_path / ".env")
    import os

    assert (os.environ["SHORTS_A"], os.environ["SHORTS_B"], os.environ["SHORTS_C"]) == (
        "from the environment",
        "quoted",
        "",
    )


def step(goal: str, start: float, end: float, action: dict, did: str = "") -> Step:
    return Step(goal=goal, actions=[action], did=[did], url="https://makable.tech", start=start, end=end)


def test_whether_the_agent_did_its_task() -> None:
    steps = [
        step("Click", 0, 1, {"click": {"index": 4}}),
        step("Done", 1, 1.1, {"done": {"success": True}}, "All worked."),
    ]
    assert outcome(steps) == (True, "All worked.")
    assert outcome(steps[:1]) == (None, "")


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


@needs_ffmpeg
def test_the_tight_recording_comes_in_as_footage(run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = {}

    async def record_task(task, out, llm, **options):
        asked.update(task=task, llm=llm, **options)
        steps = [
            step("Click New site", 0.5, 2, {"click": {"index": 1}}),
            step("Done", 2, 2.1, {"done": {"success": True}}),
        ]
        save_steps(video(out, 3), steps)
        return out, steps

    def cut_pauses(recording, steps, out):
        shutil.copyfile(recording, out)
        save_steps(out, steps)
        return out, steps

    monkeypatch.setattr(recorder, "record_task", record_task)
    monkeypatch.setattr(recorder, "cut_pauses", cut_pauses)
    monkeypatch.setattr(recorder, "chat_model", lambda spec: f"model {spec}")

    url = "https://app.example.com"
    tight = browse(run, "demo", "Make a site.", url=url, model="anthropic:claude", fallback=None, max_steps=9)
    assert tight == run.path("recordings/demo-tight.mp4")
    assert (asked["task"], asked["llm"], asked["fallback"], asked["max_steps"]) == (
        "Make a site.",
        "model anthropic:claude",
        None,
        9,
    )
    assert run.settings().footage == {"demo": "recordings/demo-tight.mp4"}
    assert run.path(footage_file("demo")).exists() and run.path(steps_file("demo")).exists()
    kept = json.loads(run.path("recordings/demo.browse.json").read_text())
    assert (kept["task"], kept["url"], kept["model"], kept["signed_in"], kept["window"]) == (
        "Make a site.",
        url,
        "anthropic:claude",
        False,
        "720x1280",
    )
    assert (asked["url"], asked["size"], asked["profile"]) == (url, (720, 1280), None)


def test_browse_goes_to_its_own_python_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from shorts.__main__ import browse_elsewhere
    from shorts.stages.base import NotReady

    monkeypatch.setenv("SHORTS_BROWSE_PYTHON", sys.executable)
    monkeypatch.setenv("SHORTS_BROWSE_SENT", "1")  # as that Python's command finds it
    with pytest.raises(NotReady, match="hasn't browser-use either"):
        browse_elsewhere()


@needs_ffmpeg
def test_a_fallback_without_its_key_isnt_used(
    run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    async def record_task(task, out, llm, **options):
        assert options["fallback"] is None
        steps = [step("Done", 0, 1, {"done": {"success": True}})]
        save_steps(video(out, 2), steps)
        return out, steps

    def chat(spec: str) -> str:
        if spec.startswith("google:"):
            raise ValueError("Set GEMINI_API_KEY: the model's key (in .env, or the environment)")
        return f"model {spec}"

    monkeypatch.setattr(recorder, "record_task", record_task)
    monkeypatch.setattr(recorder, "cut_pauses", lambda recording, steps, out: (shutil.copyfile(recording, out), steps))
    monkeypatch.setattr(recorder, "chat_model", chat)
    url, fallback = "https://app.example.com", "google:gemini-3-flash-preview"
    browse(run, "demo", "Make a site.", url=url, model="anthropic:claude", fallback=fallback)
    assert "Warning: no fallback model (Set GEMINI_API_KEY" in capsys.readouterr().out
    assert json.loads(run.path("recordings/demo.browse.json").read_text())["fallback"] is None
