"""Checking a script against the recordings it's said over, before the video is made from it."""

from pathlib import Path

import pytest

from shorts.run import Run
from shorts.script import Scene, Script, check, speed
from shorts.stages.bring_in import bring_in

from .conftest import needs_ffmpeg, video

INTRO = "Watch me build a whole bakery website from one sentence, and change it with another, in a minute."
WORDS = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen"


def scene(start: float | None, end: float | None, *, words: int = 15, footage: str = "demo") -> Scene:
    return Scene(text=" ".join(WORDS.split()[:words]), footage=footage, start=start, end=end)


def written(*scenes: Scene, outro: str = "Try makable today, it's free.") -> Script:
    return Script(intro_line=INTRO, intro_setting="A kitchen.", scenes=list(scenes), title="T", description="D",
                  outro_line=outro)  # fmt: skip


def test_a_script_that_fits_its_recording() -> None:
    script = written(scene(0, 6), scene(6, 12), scene(12, 18))
    errors, warnings = check(script, {"demo": 20.0}, timed={"demo"})
    assert errors == []
    assert warnings == []


def test_what_the_video_cant_be_made_from() -> None:
    script = written(
        scene(0, 6),
        scene(5, 10),  # overlaps the first
        scene(18, 25),  # runs past the recording's end
        scene(12, 12.5),  # too short
        scene(None, None),  # no stretch, though the recording has steps
        scene(0, 4, footage="other"),  # not a recording the run has
    )
    errors, _ = check(script, {"demo": 20.0}, timed={"demo"})
    assert errors == [
        "Scenes 1 and 2 overlap in 'demo': the stretches never do",
        "Scene 3's stretch (18-25 s) isn't all in 'demo' (0-20.0 s)",
        "Scene 4's stretch (12-12.5 s) is shorter than 1 s",
        "Scene 5 has no start and end, though 'demo' has steps",
        "Scene 6 is said over 'other', which isn't one of demo",
    ]


def test_what_may_not_look_or_sound_right() -> None:
    script = written(scene(0, 20, words=3), scene(20, 21.5, words=15), outro=" ".join(["word"] * 25))
    script.intro_line = "Too short."
    script.title = "x" * 80
    script.scenes[0].text += " #ad 🎉"
    _, warnings = check(script, {"demo": 30.0})
    assert "The intro line has 2 words: 14 to 20 fit Omni's 10-second clip" in warnings
    assert "The outro line has 25 words: keep it to 20 or fewer" in warnings
    assert "The script has 2 scenes: 3 to 8 tell a minute's story" in warnings
    assert any(w.startswith("Scene 1's stretch would play at about") and "say more" in w for w in warnings)
    assert any(w.startswith("Scene 2's stretch would play at about 0.2x") for w in warnings)
    assert "The title has 80 characters: YouTube shows fewer than 70" in warnings
    assert "Something that's said has an emoji or a hashtag, which the narrator can't say" in warnings


def test_a_stretch_plays_as_long_as_its_narration() -> None:
    assert speed(scene(0, 6.35, words=15)) == pytest.approx(1.0)  # 15 words: 6 s, and a 0.35 s pause
    assert speed(scene(None, None)) is None


def test_without_footage_the_recordings_arent_checked() -> None:
    errors, _ = check(written(scene(0, 6, footage="anything")), {})
    assert errors == []


@needs_ffmpeg
def test_a_script_the_video_cant_be_made_from_isnt_brought_in(run: Run, tmp_path: Path) -> None:
    bring_in(run, "footage", [video(tmp_path / "recording.mp4", 10)], name="demo")
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(written(scene(0, 6)).model_dump_json())
    bad.write_text(written(scene(0, 6), scene(4, 9)).model_dump_json())
    bring_in(run, "script", [good])
    with pytest.raises(ValueError, match="Scenes 1 and 2 overlap"):
        bring_in(run, "script", [bad])
    assert len(run.script().scenes) == 1  # the one there is kept
