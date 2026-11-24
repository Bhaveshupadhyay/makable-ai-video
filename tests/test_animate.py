"""An animated Short's footage: its characters drawn (cast), each shot's still (stills), and each still animated
(animate), with the image model and the video model faked."""

import dataclasses
import json
from pathlib import Path

import pytest

from shorts.animators import ANIMATORS, clip_seconds
from shorts.media import duration
from shorts.orchestrator import run_all, run_stage, status
from shorts.run import FINAL, Run, Settings
from shorts.script import Character, Scene, Script, Shot
from shorts.stages import STAGES, producer
from shorts.stages.animate import choose, compare, more_takes, prompts
from shorts.stages.assemble import Assemble
from shorts.stages.base import CURRENT, EDITED, STALE, states
from shorts.stages.bring_in import bring_in

from .conftest import needs_ffmpeg, speech, video

STYLE = "Stylized 3D CGI, glossy, cyan gradient background"


def storyboard() -> Script:
    def scene(number: int, still: str, *, characters: tuple[str, ...] = ("man",), follows: bool = False) -> Scene:
        shot = Shot(still=still, motion=f"motion {number}", characters=list(characters), follows=follows)
        return Scene(text=f"Shot {number} is said here.", footage=f"shot-{number:02d}", shot=shot)

    return Script(
        style=STYLE,
        characters=[Character(name="man", look="a bald cartoon man in a blue t-shirt")],
        scenes=[
            scene(1, "The man under a palm"),
            scene(2, "A coconut falling", characters=()),
            scene(3, "The man looks up", follows=True),
        ],
        title="Coconuts",
        description="D",
    )


@pytest.fixture
def drawn(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str]]]:
    """The image model, faked: each drawing's prompt and references' names, in order."""
    from PIL import Image

    calls: list[tuple[str, list[str]]] = []

    def draw(
        client: object, prompt: str, references: list[Path], out: Path, *, model: str, aspect: str = "9:16"
    ) -> Path:
        calls.append((prompt, [path.name for path in references]))
        Image.new("RGB", (90, 160), (len(calls) * 40 % 256, 100, 150)).save(out, format="PNG")
        return out

    monkeypatch.setattr("shorts.images.client", lambda: object())
    monkeypatch.setattr("shorts.images.draw", draw)
    return calls


@pytest.fixture
def animated_by(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int, str]]:
    """Omni, faked: each clip's still, seconds and model."""
    calls: list[tuple[str, int, str]] = []

    def animate(still: Path, end: Path | None, prompt: str, seconds: int, out: Path, model: str) -> Path:
        calls.append((still.name, seconds, model))
        return video(out, seconds)

    monkeypatch.setitem(ANIMATORS, "omni", dataclasses.replace(ANIMATORS["omni"], animate=animate))
    return calls


@pytest.fixture
def animated(tmp_path: Path) -> Run:
    run = Run(tmp_path / "runs" / "coconut")
    settings = Settings(kind="animated", intro="none", outro="none", narrator="import", size=(180, 320), captions=False)
    run.save_settings(settings.model_copy(update={"cast_takes": 2}))
    (tmp_path / "script.json").write_text(storyboard().model_dump_json())
    bring_in(run, "script", [tmp_path / "script.json"])
    return run


def test_the_cast_is_drawn_in_takes_and_the_first_is_used_until_you_choose(animated: Run, drawn: list) -> None:
    run_stage(animated, "cast")
    assert len(drawn) == 2  # two takes of the man's sheet
    assert drawn[0][0].startswith(f"{STYLE}. Character sheet of a bald cartoon man in a blue t-shirt")
    assert animated.path("cast/man.png").read_bytes() == animated.path("cast/man-take-1.png").read_bytes()

    choose(animated, "man", "2")
    assert animated.path("cast/man.png").read_bytes() == animated.path("cast/man-take-2.png").read_bytes()
    assert states(animated, "cast", STAGES["cast"].plan(animated)) == {"cast/man.png": EDITED}  # locked: kept


def test_a_mascot_you_keep_is_used_as_it_is(animated: Run, drawn: list, shorts_home: Path) -> None:
    mascot = shorts_home / "me" / "characters" / "man.png"
    mascot.parent.mkdir(parents=True)
    mascot.write_bytes(b"a sheet")
    run_stage(animated, "cast")
    assert drawn == []
    assert animated.path("cast/man.png").read_bytes() == b"a sheet"


def test_each_still_is_drawn_from_its_characters_the_first_still_and_the_shot_it_follows(
    animated: Run, drawn: list
) -> None:
    run_stage(animated, "cast")
    drawn.clear()
    run_stage(animated, "stills")
    assert [references for _, references in drawn] == [
        ["man.png"],
        ["shot-01.png"],  # no one in it: only the first still, for the style
        ["man.png", "shot-01.png", "shot-02.png"],  # it follows on from shot 2
    ]
    first = drawn[0][0]
    assert first.startswith(f"{STYLE}. Image 1 is the character sheet of man.")
    assert "The picture: The man under a palm." in first
    assert "No text, letters, captions, logos or watermarks" in first
    assert animated.path("stills/sheet.png").exists()


def test_only_a_still_whose_prompt_or_references_changed_is_drawn_again(animated: Run, drawn: list) -> None:
    run_stage(animated, "cast")
    run_stage(animated, "stills")
    script = animated.script()
    script.scenes[1].shot.still = "Two coconuts falling"  # shot 3 follows shot 2, so it's drawn again too
    animated.path("script.json").write_text(script.model_dump_json())
    assert states(animated, "stills", STAGES["stills"].plan(animated)) == {
        "stills/shot-01.png": CURRENT,
        "stills/shot-02.png": STALE,
        "stills/shot-03.png": STALE,
    }


def test_a_clip_is_as_long_as_its_shot_needs() -> None:
    assert [clip_seconds(seconds) for seconds in (2.0, 4.0, 4.3, 5.95, 6.5, 9.0)] == [4, 4, 6, 6, 8, 8]


@needs_ffmpeg
def test_animating_is_paid_so_run_stops_before_it(
    animated: Run, drawn: list, animated_by: list, tmp_path: Path
) -> None:
    run_stage(animated, "cast")
    run_stage(animated, "stills")
    narration = [speech(tmp_path / f"{n}.wav", seconds, 300 + 100 * n) for n, seconds in ((1, 5), (2, 3), (3, 4))]
    bring_in(animated, "narration", narration)
    assert [entry.product for entry in status(animated) if entry.needed] == ["script", "cast", "stills", "narration", "footage", "video"]  # fmt: skip

    assert not run_all(animated)  # without --paid
    assert animated_by == []
    assert producer(animated, "footage").cost.startswith("$0.07 a second")

    run_stage(animated, "animate")
    # As long as each shot's narration and a pause: 5.35 s, 3.35 s, and 4.35 s and a second more, the last
    assert animated_by == [("shot-01.png", 6, "gemini-omni-1.2-flash"), ("shot-02.png", 4, "gemini-omni-1.2-flash"),
                           ("shot-03.png", 6, "gemini-omni-1.2-flash")]  # fmt: skip
    assert duration(animated.path("footage/shot-01.mp4")) == pytest.approx(6, abs=0.1)
    assert json.loads(animated.path("picks.json").read_text()) == dict.fromkeys(
        ["shot-01", "shot-02", "shot-03"], "omni-1.2"
    )

    # More takes, to compare, and one chosen: assemble makes the video from it.
    more_takes(animated, ["omni-1.1"])
    assert animated_by[-1] == ("shot-03.png", 6, "gemini-omni-1.1-flash-preview")
    assert compare(animated).exists()
    choose(animated, "shot-02", "omni-1.1")
    assert json.loads(animated.path("picks.json").read_text())["shot-02"] == "omni-1.1"
    assert run_all(animated)  # nothing paid is due: the chosen clip is kept as it is
    assert len(animated_by) == 6
    assert duration(animated.path(FINAL)) == pytest.approx(5.35 + 3.35 + 5.35, abs=0.1)
    assert [part.footage.name for part in Assemble().parts(animated, animated.settings(), animated.script(), tmp_path)] == [
        "shot-01.mp4", "shot-02.mp4", "shot-03.mp4"
    ]  # fmt: skip


@needs_ffmpeg
def test_a_take_that_isnt_one_is_refused_before_anything_is_paid(
    animated: Run, drawn: list, animated_by: list, tmp_path: Path
) -> None:
    run_stage(animated, "cast")
    run_stage(animated, "stills")
    bring_in(animated, "narration", [speech(tmp_path / f"{n}.wav", 2, 300 + 100 * n) for n in (1, 2, 3)])
    with pytest.raises(ValueError, match="omni has no version '9'"):
        more_takes(animated, ["omni-1.1", "omni-9"])
    assert animated_by == []


def test_you_can_animate_the_stills_yourself_and_bring_the_clips_in(animated: Run, drawn: list) -> None:
    animated.save_settings(
        animated.settings().model_copy(update={"animator": "import", "narrator": "none", "captions": True})
    )
    assert producer(animated, "footage").name == "record"
    run_stage(animated, "cast")
    run_stage(animated, "stills")
    lines = prompts(animated)
    assert len(lines) == 3
    assert lines[0].startswith("shot-01 (4 s): ")
    assert "What happens: motion 1" in lines[0]


def test_google_is_asked_again_when_its_busy() -> None:
    from shorts.images import patiently

    class Busy(Exception):
        code = 429

    answers = iter([Busy(), Busy(), "an image"])

    def ask() -> str:
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    assert patiently(ask, waits=(0, 0, 0)) == "an image"

    def always_busy() -> str:
        raise Busy()

    with pytest.raises(Busy):
        patiently(always_busy, waits=(0,))
