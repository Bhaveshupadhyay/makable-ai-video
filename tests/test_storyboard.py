"""An animated Short's storyboard: its style, its characters and each scene's shot, and the rules it's held to."""

from pathlib import Path

import pytest

from shorts.media import duration
from shorts.run import FINAL, Run, Settings
from shorts.script import Character, Scene, Script, Shot, check
from shorts.stages.assemble import Assemble
from shorts.stages.bring_in import bring_in, check_script

from .conftest import needs_ffmpeg, speech, video

LINE = "one two three four five six seven eight nine ten eleven twelve thirteen"  # 13 words: about 5.6 s on screen
STYLE = "Stylized 3D medical-explainer CGI, glossy, soft studio light, cyan-to-white gradient background"


def shot(number: int, *, words: int = 13, characters: tuple[str, ...] = ("man",), **change: str) -> Scene:
    picture = {"still": "The man sits under a tall palm, eyes closed", "motion": "Camera tilts up the trunk"}
    return Scene(
        text=" ".join((LINE.split() * 3)[:words]),
        footage=f"shot-{number:02d}",
        shot=Shot(**(picture | change), characters=list(characters)),
    )


def storyboard(*scenes: Scene) -> Script:
    scenes = scenes or tuple(shot(number) for number in range(1, 6))
    return Script(
        style=STYLE,
        characters=[Character(name="man", look="bald cartoon man, plain blue t-shirt, grey shorts")],
        scenes=list(scenes),
        title="Can a coconut break your skull?",
        description="D",
    )


def checked(script: Script) -> tuple[list[str], list[str]]:
    return check(script, {}, kind="animated")


def test_a_storyboard_that_fits() -> None:
    assert checked(storyboard()) == ([], [])


def test_it_opens_on_its_first_shot_so_it_has_no_intro_line() -> None:
    script = storyboard()
    script.intro_line = "Hello there."
    _, warnings = checked(script)
    assert warnings == ["The intro line isn't used: an animated Short opens on its first shot, so the hook is its text"]


def test_what_a_storyboard_cant_be_made_from() -> None:
    script = storyboard(
        shot(1),
        shot(2, characters=("man", "doctor")),  # no such character
        shot(3, still="A coconut with the brand logo on it"),
        shot(4, motion=""),
        Scene(text=LINE, footage="shot-05"),  # no shot
        shot(4),  # the same clip as scene 4
    )
    script.style = ""
    errors, _ = checked(script)
    assert errors == [
        'The storyboard has no style: one sentence on how every image looks ("Stylized 3D CGI, ...")',
        "Scene 2's shot has 'doctor', who isn't one of the characters (man)",
        "Scene 4's shot needs both a still and a motion",
        "Scene 5 has no shot: what it shows (still) and how it moves (motion)",
        "Scenes 4 and 6 are both 'shot-04': each shot is its own clip",
        "Scene 3's still mentions 'brand': describe only pictures. The models are already told to show no text, "
        "captions or logos, and draw them wrong if asked",
    ]


def test_text_in_a_character_or_the_style_is_refused_too() -> None:
    script = storyboard()
    script.characters[0].look += ", a t-shirt with text on it"
    script.style += ", with captions"
    errors, _ = checked(script)
    assert [error.split(":")[0] for error in errors] == [
        "The style mentions 'captions'",
        "The character 'man' mentions 'text'",
    ]


def test_each_shot_fits_a_clip_and_the_short_its_length() -> None:
    script = storyboard(shot(1, words=3), shot(2, words=13), shot(3, words=25))
    _, warnings = checked(script)
    assert warnings == [
        "The script has 3 shots: 4 to 6 tell a 30-second story",
        "The narration is about 16 s long: aim for about 30 s",
        "Scene 1's shot is about 1.5 s: 4 to 8 s fits the clips a video model makes (say more over it, or join it to "
        "the next)",
        "Scene 3's shot is about 10.3 s: 4 to 8 s fits the clips a video model makes (say less, or split it)",
    ]


def test_a_demo_isnt_held_to_the_storyboard() -> None:
    script = storyboard()
    script.style = ""
    errors, _ = check(script, {})
    assert errors == ["The intro line is empty"]  # a demo's own rule, and none of the storyboard's


@pytest.fixture
def animated(run: Run) -> Run:
    run.save_settings(Settings(kind="animated", intro="none", outro="none", size=(180, 320), captions=False))
    return run


def test_an_animated_runs_script_isnt_checked_against_recordings(animated: Run, tmp_path: Path) -> None:
    # A recording the shots aren't said over: a demo's script would be refused for it
    animated.save_settings(
        animated.settings().model_copy(update={"footage": {"demo": str(video(tmp_path / "r.mp4", 2))}})
    )
    assert check_script(animated, storyboard()) == ([], [])


@needs_ffmpeg
def test_an_animated_short_opens_on_its_first_shot(animated: Run, tmp_path: Path) -> None:
    script = storyboard(shot(1), shot(2))
    (tmp_path / "script.json").write_text(script.model_dump_json())
    bring_in(animated, "script", [tmp_path / "script.json"])
    for number in (1, 2):
        bring_in(animated, "footage", [video(tmp_path / f"clip-{number}.mp4", 6)], name=f"shot-{number:02d}")
    bring_in(animated, "narration", [speech(tmp_path / "1.wav", 5), speech(tmp_path / "2.wav", 4, 550)])

    assert [part.text for part in Assemble().parts(animated, animated.settings(), animated.script(), tmp_path)] == [
        script.scenes[0].text,
        script.scenes[1].text,
    ]
    Assemble().make(animated, [FINAL])
    assert duration(animated.path(FINAL)) == pytest.approx((5 + 0.35) + (4 + 0.35 + 1), abs=0.05)


def test_names_name_files_so_they_never_leave_the_run_folder() -> None:
    script = storyboard(shot(1, characters=("../../poster",)), shot(2), shot(3), shot(4))
    script.characters[0].name = "../../poster"
    script.scenes[1].footage = "../outside"
    errors, _ = checked(script)
    assert "The character '../../poster' needs a name of letters, digits, - and _: it names files" in errors
    assert "Scene 2's footage '../outside' needs a name of letters, digits, - and _ (shot-01)" in errors


def test_saying_not_to_show_text_is_fine() -> None:
    script = storyboard()
    script.style += ", no text or logos anywhere"
    script.scenes[0].shot.still += ", without captions"
    assert checked(script) == ([], [])
    script.scenes[1].shot.still = "No blood. A sign with text on it"  # a new sentence asks for it
    assert checked(script)[0][0].startswith("Scene 2's still mentions 'text'")


def test_the_hook_named_is_what_the_video_opens_with() -> None:
    script = storyboard()
    script.hooks = {"H1": script.scenes[0].text, "H2": "Something else entirely."}
    script.hook = "H1"
    assert checked(script) == ([], [])
    script.hook = "H2"
    assert checked(script)[0] == [
        "The hook 'H2' isn't what the video opens with: make it the first scene's text, or name another"
    ]
    script.hook = "H9"
    assert checked(script)[0] == ["The hook 'H9' isn't one of the hooks (H1, H2)"]


def test_a_demo_without_an_intro_needs_no_intro_line() -> None:
    script = storyboard()
    assert "The intro line is empty" not in check(script, {}, intro=False)[0]
