"""The narration spoken through the voice API, in the voice of the avatar in the intro: take-voice, then speak with
narrator "modal" or "elevenlabs", against services/voice's API in this process (with a stand-in for the model), and
the keys each takes from the environment."""

from pathlib import Path

import pytest

pytest.importorskip("httpx")
pytest.importorskip("fastapi")
pytest.importorskip("multipart")

from fastapi.testclient import TestClient  # noqa: E402

from services.voice.api import FolderVoices, create_app  # noqa: E402
from shorts.media import duration  # noqa: E402
from shorts.orchestrator import run_all, run_stage, status  # noqa: E402
from shorts.run import AVATAR_VOICE, FINAL, Run, narration_file  # noqa: E402
from shorts.speech_api import ELEVENLABS, SpeechAPI, SpeechAPIError  # noqa: E402
from shorts.stages.base import CURRENT, STALE, NotReady  # noqa: E402
from shorts.stages.bring_in import bring_in  # noqa: E402

from .conftest import needs_ffmpeg, script, video  # noqa: E402
from .test_voice_api import KEY, Tone  # noqa: E402


@pytest.fixture
def voices(tmp_path: Path) -> Path:
    return tmp_path / "voices"


@pytest.fixture
def tone(monkeypatch: pytest.MonkeyPatch, voices: Path) -> Tone:
    """The API, with a stand-in model for each narrator's, as the environment's: `tone.narrators` are those asked
    for."""
    tone = Tone()
    speakers = {"omnivoice": tone, "eleven_multilingual_v2": tone}
    server = TestClient(create_app(FolderVoices(voices), speakers, key=KEY), base_url="http://voice")

    def from_environment(cls, narrator: str = "modal") -> SpeechAPI:
        tone.narrators.append(narrator)
        return SpeechAPI("http://voice", KEY, client=server)

    tone.narrators = []
    monkeypatch.setattr(SpeechAPI, "from_environment", classmethod(from_environment))
    return tone


@pytest.fixture
def avatar_run(run: Run, tmp_path: Path) -> Run:
    """A run with its footage, a script with an outro, and Omni's clips brought in, narrated by the API in the
    intro's voice."""
    written = script((0, 4), (6, 9))
    written.scenes[1].text = "And this scene says a few more words."
    written.outro_line = "Try it today."
    (tmp_path / "script.json").write_text(written.model_dump_json())
    settings = {"narrator": "modal", "narration_voice": "intro", "narrator_options": {"speed": 1.1}}
    run.save_settings(run.settings().model_copy(update=settings))
    bring_in(run, "footage", [video(tmp_path / "recording.mp4", 12)], name="demo")
    bring_in(run, "script", [tmp_path / "script.json"])
    bring_in(run, "intro", [video(tmp_path / "intro.mp4", 3, tone=330)])
    bring_in(run, "outro", [video(tmp_path / "outro.mp4", 2, tone=550)])
    return run


@needs_ffmpeg
def test_the_narration_is_spoken_in_the_avatars_voice(avatar_run: Run, tone: Tone, voices: Path) -> None:
    run = avatar_run
    entries = {entry.product: entry for entry in status(run)}
    assert entries["narration"].waiting == "waiting for the avatar-voice"

    run_stage(run, "take-voice")
    assert duration(run.path(AVATAR_VOICE)) == pytest.approx(3, abs=0.1)  # the intro's sound
    assert run_stage(run, "speak") == [narration_file(0), narration_file(1)]
    # The stand-in speaks a tenth of a second a word: "Scene 1 says this." and the eight words of scene 2.
    assert duration(run.path(narration_file(0))) == pytest.approx(0.4, abs=0.06)
    assert duration(run.path(narration_file(1))) == pytest.approx(0.8, abs=0.06)
    assert [asked[3:] for asked in tone.asked] == [("en", {"speed": 1.1})] * 2
    assert tone.narrators == ["modal"]
    assert list(voices.iterdir()) == []  # the voice is deleted once the scenes are spoken

    # Editing a scene's text speaks only it again.
    edited = run.script()
    edited.scenes[0].text = "Scene one, said another way."
    run.path("script.json").write_text(edited.model_dump_json())
    assert {entry.product: entry for entry in status(run)}["narration"].files == {
        narration_file(0): STALE,
        narration_file(1): CURRENT,
    }
    assert run_stage(run, "speak") == [narration_file(0)]
    assert len(tone.asked) == 3

    assert run_all(run)  # assemble, in a process of its own: the narration is up to date
    expected = 3 + (0.5 + 0.35) + (0.8 + 0.35 + 1) + 2  # the intro, the scenes and their pauses, the outro
    assert duration(run.path(FINAL)) == pytest.approx(expected, abs=0.1)


@needs_ffmpeg
def test_without_the_api_speak_says_what_to_set(avatar_run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHORTS_SPEECH_URL", raising=False)
    run_stage(avatar_run, "take-voice")
    with pytest.raises(NotReady, match="Set SHORTS_SPEECH_URL and SHORTS_SPEECH_KEY"):
        run_stage(avatar_run, "speak")


@needs_ffmpeg
def test_a_voice_the_api_couldnt_delete_is_a_warning(
    avatar_run: Run, tone: Tone, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    from shorts.speech_api import SpeechAPIError

    def unreachable(self, voice_id: str) -> None:
        raise SpeechAPIError(f"DELETE /v1/voices/{voice_id}: ConnectError, after 4 tries")

    monkeypatch.setattr(SpeechAPI, "delete_voice", unreachable)
    run_stage(avatar_run, "take-voice")
    assert run_stage(avatar_run, "speak") == [narration_file(0), narration_file(1)]  # the scenes are made
    assert "Warning: the voice is still in the API" in capsys.readouterr().out


@needs_ffmpeg
def test_elevenlabs_speaks_with_its_own_model(avatar_run: Run, tone: Tone) -> None:
    avatar_run.save_settings(
        avatar_run.settings().model_copy(update={"narrator": "elevenlabs", "narrator_options": {}})
    )
    run_stage(avatar_run, "take-voice")
    assert run_stage(avatar_run, "speak") == [narration_file(0), narration_file(1)]
    assert tone.narrators == ["elevenlabs"]
    assert avatar_run.record("narration").files[narration_file(0)].by == "speak (eleven_multilingual_v2)"


def test_each_narrators_api_takes_its_own_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("ELEVENLABS_API_KEY", "SHORTS_SPEECH_URL", "SHORTS_SPEECH_KEY"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(SpeechAPIError, match="Set ELEVENLABS_API_KEY"):
        SpeechAPI.from_environment("elevenlabs")
    with pytest.raises(SpeechAPIError, match="deploy-voice"):
        SpeechAPI.from_environment("modal")

    monkeypatch.setenv("ELEVENLABS_API_KEY", "eleven")
    monkeypatch.setenv("SHORTS_SPEECH_URL", "https://me--makable-voice-web.modal.run/")
    monkeypatch.setenv("SHORTS_SPEECH_KEY", "mine")
    elevenlabs, mine = SpeechAPI.from_environment("elevenlabs"), SpeechAPI.from_environment("modal")
    assert (elevenlabs.url, elevenlabs.http.headers["xi-api-key"]) == (ELEVENLABS, "eleven")
    assert (mine.url, mine.http.headers["xi-api-key"]) == ("https://me--makable-voice-web.modal.run", "mine")
