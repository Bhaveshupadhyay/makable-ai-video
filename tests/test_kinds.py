"""The kinds of video: with an avatar of you, or without one (a title card and an end card), narrated by an API in a
cloned voice, by Kokoro on this machine, or with no voice at all."""

import json
import sys
import types
from pathlib import Path

import pytest

from shorts.home import choose
from shorts.media import duration
from shorts.orchestrator import elsewhere, run_all, run_stage, status
from shorts.run import CARD_NARRATION, FINAL, METADATA, Run, Settings, narrated, narration_file
from shorts.script import CARD_WORDS, Scene, Script, check, on_screen, speed
from shorts.stages.base import CURRENT, STALE, NotReady
from shorts.stages.bring_in import bring_in
from shorts.voice import KokoroVoice, espeak_data

from .conftest import needs_ffmpeg, script, speech, video

TITLE = "One sentence in, a whole website out."
SIGN_OFF = "Try it free."


def cards(*stretches: tuple[float, float]) -> Script:
    """A script for a video without an avatar: lines for the cards, and no settings to film them in."""
    written = script(*stretches)
    written.intro_line, written.intro_setting, written.outro_line = TITLE, "", SIGN_OFF
    return written


@pytest.fixture
def card_run(run: Run, tmp_path: Path) -> Run:
    """A run without an avatar, with its footage and a script for cards."""
    run.save_settings(run.settings().model_copy(update={"intro": "card", "outro": "card"}))
    bring_in(run, "footage", [video(tmp_path / "recording.mp4", 12)], name="demo")
    (tmp_path / "script.json").write_text(cards((0, 4), (6, 9)).model_dump_json())
    bring_in(run, "script", [tmp_path / "script.json"])
    return run


def test_without_an_avatar_a_new_run_has_cards_and_your_voice_for_an_api(tmp_path: Path) -> None:
    choose(filmer="none", narrator="kokoro", kokoro_voice="am_michael")
    settings = Run(tmp_path / "first").settings()
    assert (settings.intro, settings.outro, settings.narrator, settings.kokoro_voice) == (
        "card",
        "card",
        "kokoro",
        "am_michael",
    )
    choose(narrator="elevenlabs")  # an API clones a voice: with no avatar to take it from, yours
    assert Run(tmp_path / "second").settings().narration_voice == "sample"
    choose(filmer="omni")
    assert Run(tmp_path / "third").settings().narration_voice == "intro"


def test_what_the_narrator_says_over_the_cards() -> None:
    written = cards((0, 4), (6, 9))
    lines = narrated(written, Settings(intro="card", outro="card"))
    assert lines == [
        (CARD_NARRATION["intro"], TITLE),
        (narration_file(0), "Scene 1 says this."),
        (narration_file(1), "Scene 2 says this."),
        (CARD_NARRATION["outro"], SIGN_OFF),
    ]
    assert [path for path, _ in narrated(written, Settings())] == [narration_file(0), narration_file(1)]
    assert [path for path, _ in narrated(written, Settings(intro="card", outro="none"))][-1] == narration_file(1)


def test_a_cards_line_is_short_and_a_silent_scene_plays_at_its_own_speed() -> None:
    long = " ".join(["word"] * (CARD_WORDS + 1))
    written = cards((0, 10))
    written.intro_line = written.outro_line = long
    _, warnings = check(written, {}, cards=("intro", "outro"), outro=True)
    assert any("The title card's line" in warning for warning in warnings)
    assert any("The end card's line" in warning for warning in warnings)
    assert not any("Omni" in warning for warning in warnings)

    # 4 words over 10 seconds: narrated, they'd race through it; read, the stretch plays as it is.
    short = Scene(text="Click the big button", footage="demo", start=0, end=10)
    assert speed(short) > 2.5 and speed(short, silent=True) == 1.0
    wordy = Scene(text=" ".join(["word"] * 20), footage="demo", start=0, end=2)
    assert on_screen(wordy, silent=True) == pytest.approx(20 / 2.5 + 0.35)  # slowed down, to be read
    _, warnings = check(Script(**{**written.model_dump(), "scenes": [short]}), {"demo": 10.0}, silent=True)
    assert not any("would play at" in warning for warning in warnings)


@needs_ffmpeg
def test_a_video_with_cards_and_no_voice(card_run: Run) -> None:
    card_run.save_settings(card_run.settings().model_copy(update={"narrator": "none"}))
    entries = {entry.product: entry for entry in status(card_run)}
    for product in ("intro", "outro", "avatar-voice", "narration"):
        assert not entries[product].needed, product
    assert run_stage(card_run, "film-intro") == []  # nothing to film: assemble draws the card

    assert run_all(card_run)
    # The title card for as long as it takes to read, each stretch at its own speed (the last held a second more),
    # and the end card: each at least 2 s.
    title = max(2.0, len(TITLE.split()) / 2.5 + 0.35)
    assert duration(card_run.path(FINAL)) == pytest.approx(title + 4 + (3 + 1) + 2.0, abs=0.1)
    assert json.loads(card_run.path(METADATA).read_text())["containsSyntheticMedia"] is False


@needs_ffmpeg
def test_cards_said_by_a_narrator_brought_in(card_run: Run, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="a title card, 2 scenes and an end card, but there are 2 audio files"):
        bring_in(card_run, "narration", [speech(tmp_path / f"{n}.wav", 1, 300 + 100 * n) for n in range(2)])
    said = [speech(tmp_path / "1.wav", 1.5), speech(tmp_path / "2.wav", 1, 500), speech(tmp_path / "3.wav", 2, 600)]
    bring_in(card_run, "narration", [*said, speech(tmp_path / "4.wav", 0.5, 700)])
    assert card_run.path(CARD_NARRATION["intro"]).exists() and card_run.path(CARD_NARRATION["outro"]).exists()

    assert run_all(card_run)
    # Each card for as long as its narration and a pause, and each scene too (the last a second more).
    seconds = (1.5 + 0.35) + (1 + 0.35) + (2 + 0.35 + 1) + (0.5 + 0.35)
    assert duration(card_run.path(FINAL)) == pytest.approx(seconds, abs=0.1)
    assert json.loads(card_run.path(METADATA).read_text())["containsSyntheticMedia"] is True  # it may be a clone


@needs_ffmpeg
def test_kokoro_speaks_the_cards_and_the_scenes(card_run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    heard: list[tuple[str, str]] = []

    def say(voice: KokoroVoice, text: str, out: Path) -> Path:
        heard.append((voice.voice, voice.spoken(text)))
        return speech(out, 1)

    monkeypatch.setattr(KokoroVoice, "say", say)
    settings = {"narrator": "kokoro", "pronounce": {"website": "web site"}}
    card_run.save_settings(card_run.settings().model_copy(update=settings))
    assert {entry.product: entry for entry in status(card_run)}["avatar-voice"].needed is False
    run_stage(card_run, "speak")
    assert heard == [
        ("af_heart", "One sentence in, a whole web site out."),
        ("af_heart", "Scene 1 says this."),
        ("af_heart", "Scene 2 says this."),
        ("af_heart", SIGN_OFF),
    ]
    assert run_all(card_run)
    assert json.loads(card_run.path(METADATA).read_text())["containsSyntheticMedia"] is False

    card_run.save_settings(card_run.settings().model_copy(update={"kokoro_voice": "am_michael"}))
    entries = {entry.product: entry for entry in status(card_run)}
    assert set(entries["narration"].files.values()) == {STALE}  # another voice: all of it again
    card_run.save_settings(card_run.settings().model_copy(update={"kokoro_voice": "hf_alpha"}))
    with pytest.raises(NotReady, match="Kokoro's voice 'hf_alpha' speaks hi, and the script is in en"):
        run_stage(card_run, "speak")
    card_run.save_settings(card_run.settings().model_copy(update={"kokoro_voice": None}))
    spoken = [path for path, _ in narrated(card_run.script(), card_run.settings())]
    assert {entry.product: entry for entry in status(card_run)}["narration"].files == dict.fromkeys(spoken, CURRENT)


@needs_ffmpeg
def test_an_api_needs_your_voice_when_theres_no_avatar(card_run: Run) -> None:
    card_run.save_settings(card_run.settings().model_copy(update={"narrator": "elevenlabs"}))
    assert {entry.product: entry for entry in status(card_run)}["avatar-voice"].needed is False
    with pytest.raises(NotReady, match="no avatar in this video to take its voice from"):
        run_stage(card_run, "speak")


def test_kokoro_speaks_in_its_voice_for_the_language(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    numpy = pytest.importorskip("numpy")
    soundfile = pytest.importorskip("soundfile")
    asked = []

    class KPipeline:
        def __init__(self, lang_code: str, repo_id: str) -> None:
            asked.append((lang_code, repo_id))

        def __call__(self, text: str, voice: str, **options: float):
            asked.append((text, voice, options))
            yield text, "", numpy.zeros(12000)
            yield text, "", numpy.zeros(12000)

    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace(KPipeline=KPipeline))
    monkeypatch.setattr("shorts.voice.espeak_data", lambda: None)
    voice = KokoroVoice(None, "hi", speed=1.1)
    voice.say("नमस्ते", tmp_path / "said.wav")
    assert asked == [("h", "hexgrad/Kokoro-82M"), ("नमस्ते", "hf_alpha", {"speed": 1.1})]
    assert soundfile.info(tmp_path / "said.wav").duration == pytest.approx(1.0)  # each part, one after the other


def test_espeak_finds_its_data_in_a_folder_too_deep_for_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data = tmp_path.joinpath(*["deeper"] * 20, "espeak-ng-data")
    data.mkdir(parents=True)
    (data / "phontab").write_text("phonemes")
    used = []
    monkeypatch.setitem(sys.modules, "espeakng_loader", types.SimpleNamespace(get_data_path=lambda: str(data)))
    wrapper = types.SimpleNamespace(EspeakWrapper=types.SimpleNamespace(set_data_path=used.append))
    monkeypatch.setitem(sys.modules, "phonemizer.backend.espeak.wrapper", wrapper)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    espeak_data()
    copy = tmp_path / "tmp" / "makable-shorts-espeak-ng-data"
    assert used == [str(copy)] and (copy / "phontab").read_text() == "phonemes"


def test_a_stage_runs_in_the_python_with_its_packages(card_run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    card_run.save_settings(card_run.settings().model_copy(update={"narrator": "kokoro"}))
    monkeypatch.setenv("SHORTS_KOKORO_PYTHON", "/kokoro/bin/python")
    monkeypatch.setattr("shorts.orchestrator.missing_packages", lambda python, packages: packages)
    assert elsewhere(card_run, "speak") == "/kokoro/bin/python"  # this Python hasn't Kokoro: its own has
    assert elsewhere(card_run, "assemble") is None  # SHORTS_ASSEMBLE_PYTHON isn't set: here
    monkeypatch.setattr("shorts.orchestrator.missing_packages", lambda python, packages: [])
    assert elsewhere(card_run, "speak") is None  # this one has Kokoro
