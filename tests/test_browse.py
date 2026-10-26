"""Recording footage from a task: browser-use's model, picked by name, and the recording brought into the run."""

import json
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

from shorts import browse as recorder
from shorts.__main__ import load_env
from shorts.browse import Step, chat_model, save_steps
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

    tight = browse(run, "demo", "Make a site.", model="anthropic:claude", fallback=None, max_steps=9)
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
    assert (kept["task"], kept["model"], kept["signed_in"]) == ("Make a site.", "anthropic:claude", False)


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
    browse(run, "demo", "Make a site.", model="anthropic:claude", fallback="google:gemini-3-flash-preview")
    assert "Warning: no fallback model (Set GEMINI_API_KEY" in capsys.readouterr().out
    assert json.loads(run.path("recordings/demo.browse.json").read_text())["fallback"] is None
