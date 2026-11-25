"""An animated Short's footage: its characters drawn (cast), each shot's still (stills), and each still animated
(animate), with the image model and the video model faked."""

import dataclasses
import json
from pathlib import Path

import pytest

from shorts.animators import ANIMATORS, H3_SECONDS, clip_seconds
from shorts.media import duration
from shorts.orchestrator import run_all, run_stage, status
from shorts.run import FINAL, Run, Settings
from shorts.script import Character, Scene, Script, Shot
from shorts.stages import STAGES, producer
from shorts.stages.animate import choose, compare, image_prompts, more_takes, prompts
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
    assert states(animated, "cast", STAGES["cast"].plan(animated)) == {
        "cast/man.png": EDITED,  # locked: kept
        "cast/man-take-1.png": CURRENT,
        "cast/man-take-2.png": CURRENT,
    }

    # A take more, and only it is drawn.
    animated.save_settings(animated.settings().model_copy(update={"cast_takes": 3}))
    drawn.clear()
    run_stage(animated, "cast")
    assert len(drawn) == 1
    assert animated.path("cast/man-take-3.png").exists()
    assert animated.path("cast/man.png").read_bytes() == animated.path("cast/man-take-2.png").read_bytes()


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
    plan = STAGES["stills"].plan(animated)
    assert set(states(animated, "stills", plan).values()) == {CURRENT}  # noted as drawn: nothing's drawn twice
    first = drawn[0][0]
    assert first.startswith(f"{STYLE}. Image 1 is the character sheet of man.")
    assert "The picture: The man under a palm." in first
    assert "No text, letters, captions, logos or watermarks" in first
    from PIL import Image

    assert Image.open(animated.path("stills/sheet.png")).size == (3 * 270, 480)  # every still, side by side


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
        "stills/sheet.png": STALE,
    }
    drawn.clear()
    run_stage(animated, "stills")
    assert [prompt.split("The picture: ")[1].split(".")[0] for prompt, _ in drawn] == [
        "Two coconuts falling",
        "The man looks up",
    ]


def test_a_still_drawn_from_an_edited_still_is_drawn_again(animated: Run, drawn: list) -> None:
    from PIL import Image

    run_stage(animated, "cast")
    run_stage(animated, "stills")
    Image.new("RGB", (90, 160), "white").save(animated.path("stills/shot-01.png"))  # edited by hand
    assert states(animated, "stills", STAGES["stills"].plan(animated)) == {
        "stills/shot-01.png": EDITED,  # kept as it is
        "stills/shot-02.png": STALE,  # both are drawn from it
        "stills/shot-03.png": STALE,
        "stills/sheet.png": STALE,
    }
    drawn.clear()
    run_stage(animated, "stills")
    assert len(drawn) == 2
    assert set(states(animated, "stills", STAGES["stills"].plan(animated)).values()) <= {CURRENT, EDITED}


def test_drawing_costs_cents_so_run_draws_nothing_on_its_own(animated: Run, drawn: list) -> None:
    assert not run_all(animated)
    assert drawn == []
    assert "3 ¢ an image" in producer(animated, "cast").cost


def test_a_clip_is_as_long_as_its_shot_needs() -> None:
    assert [clip_seconds(seconds) for seconds in (2.0, 4.0, 4.3, 5.95, 6.5, 9.0)] == [4, 4, 6, 6, 8, 8]
    # H3 makes clips in half seconds, so a short shot asks for a short clip: quicker, and less drift
    assert ANIMATORS["h3"].price("480p") < ANIMATORS["h3"].price("720p") == ANIMATORS["h3"].per_second
    shown = (2.0, 3.0, 3.35, 4.6, 5.35, 7.0, 12.0)
    assert [clip_seconds(seconds, H3_SECONDS) for seconds in shown] == [3, 3, 4.5, 5, 6.5, 8, 10]


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
    from shorts.media import frame_size

    assert frame_size(compare(animated)) == (2 * 360, 640 + 40)  # a column a take, under their names
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


@needs_ffmpeg
def test_a_retry_pays_only_for_what_isnt_made(
    animated: Run, drawn: list, animated_by: list, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_stage(animated, "cast")
    run_stage(animated, "stills")
    bring_in(animated, "narration", [speech(tmp_path / f"{n}.wav", 2, 300 + 100 * n) for n in (1, 2, 3)])
    fake = ANIMATORS["omni"].animate

    def fails_on_shot_2(still: Path, end: Path | None, prompt: str, seconds: int, out: Path, model: str) -> Path:
        if still.name == "shot-02.png":
            raise RuntimeError("Omni fell over")
        return fake(still, end, prompt, seconds, out, model)

    monkeypatch.setitem(ANIMATORS, "omni", dataclasses.replace(ANIMATORS["omni"], animate=fails_on_shot_2))
    with pytest.raises(RuntimeError):
        run_stage(animated, "animate")
    monkeypatch.setitem(ANIMATORS, "omni", dataclasses.replace(ANIMATORS["omni"], animate=fake))
    run_stage(animated, "animate")
    assert [still for still, *_ in animated_by] == ["shot-01.png", "shot-02.png", "shot-03.png"]  # shot 1 once

    # Another take is made again for a shot whose still changed since, and only for it.
    more_takes(animated, ["omni-1.1"])
    from PIL import Image

    Image.new("RGB", (90, 160), "white").save(animated.path("stills/shot-03.png"))
    more_takes(animated, ["omni-1.1"])
    assert [still for still, *_ in animated_by[3:]] == ["shot-01.png", "shot-02.png", "shot-03.png", "shot-03.png"]


def test_a_character_is_kept_or_forgotten_by_name_equals() -> None:
    import argparse

    from shorts.__main__ import character_argument

    assert character_argument("man=sheet.png") == ("man", "sheet.png")
    assert character_argument("man=") == ("man", "")  # forgets it
    with pytest.raises(argparse.ArgumentTypeError):
        character_argument("man")  # not a way to forget it by mistake


def test_an_animated_short_needs_google_cloud_whoever_animates_it() -> None:
    from shorts.keys import needed

    assert "GOOGLE_CLOUD_PROJECT" in needed({"narrator": "kokoro", "animator": "import"})
    assert {"GOOGLE_CLOUD_PROJECT", "VIDEO_API_URL", "VIDEO_API_KEY"} <= set(needed({"animator": "h3"}))
    assert "GOOGLE_CLOUD_PROJECT" not in needed({"filmer": "none", "narrator": "kokoro"})


def test_a_character_sheet_needs_at_least_one_take() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(cast_takes=0)


@needs_ffmpeg
def test_h3_animates_in_short_clips_and_its_sound_effects_play_under_the_narration(
    animated: Run, drawn: list, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, float, str]] = []

    def animate(still: Path, end: Path | None, prompt: str, seconds: float, out: Path, model: str) -> Path:
        calls.append((still.name, seconds, model))
        return video(out, seconds, tone=1000)  # with its own sound

    monkeypatch.setitem(ANIMATORS, "h3", dataclasses.replace(ANIMATORS["h3"], animate=animate))
    animated.save_settings(animated.settings().model_copy(update={"animator": "h3", "effects": 0.35}))
    run_stage(animated, "cast")
    run_stage(animated, "stills")
    narration = [speech(tmp_path / f"{n}.wav", seconds, 300 + 100 * n) for n, seconds in ((1, 4), (2, 2), (3, 3))]
    bring_in(animated, "narration", narration)
    assert producer(animated, "footage").by(animated.settings()) == "animate (h3-480)"
    assert producer(animated, "footage").extra_for(animated.settings()) == "video"

    run_stage(animated, "animate")
    # 4.35 s, 2.35 s, and 3.35 s and a second more: the shortest of H3's lengths that covers each
    assert calls == [("shot-01.png", 4.5, "480p"), ("shot-02.png", 3, "480p"), ("shot-03.png", 4.5, "480p")]
    assert json.loads(animated.path("picks.json").read_text()) == dict.fromkeys(
        ["shot-01", "shot-02", "shot-03"], "h3-480"
    )
    parts = Assemble().parts(animated, animated.settings(), animated.script(), tmp_path)
    assert [part.effects for part in parts] == [0.35, 0.35, 0.35]
    run_stage(animated, "assemble")
    assert duration(animated.path(FINAL)) == pytest.approx(4.35 + 2.35 + 4.35, abs=0.1)

    # A clip brought in keeps quiet: it may have speech or music of its own.
    bring_in(animated, "footage", [video(tmp_path / "mine.mp4", 3, tone=500)], name="shot-02")
    parts = Assemble().parts(animated, animated.settings(), animated.script(), tmp_path)
    assert [part.effects for part in parts] == [0.35, 0.0, 0.35]

    # Unless you ask for them, the clips' own sound isn't heard: only the narration.
    animated.save_settings(animated.settings().model_copy(update={"effects": Settings().effects}))
    parts = Assemble().parts(animated, animated.settings(), animated.script(), tmp_path)
    assert [part.effects for part in parts] == [0.0, 0.0, 0.0]

    # The captions show a scene's caption, where it has one (Hinglish for a Hindi line), and its text otherwise.
    script = animated.script()
    script.scenes[0].caption = "Shot ek yahan bola jaata hai."
    parts = Assemble().parts(animated, animated.settings(), script, tmp_path)
    assert [part.text for part in parts] == [
        "Shot ek yahan bola jaata hai.",
        "Shot 2 is said here.",
        "Shot 3 is said here.",
    ]


def test_h3_sends_the_still_and_sound_effects_to_your_video_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from shorts.animators import H3_SOUND, _h3

    seen: list[httpx.Request] = []
    polls = iter(["queued", "running", "succeeded"])

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(202, json={"id": "vid_1", "status": "queued"})
        if request.url.path.endswith("/content"):
            return httpx.Response(200, content=b"an mp4")
        return httpx.Response(200, json={"id": "vid_1", "status": next(polls)})

    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real(transport=httpx.MockTransport(answer), **kwargs))
    monkeypatch.setattr("shorts.animators.time.sleep", lambda seconds: None)
    monkeypatch.setenv("VIDEO_API_URL", "https://video.example/")
    monkeypatch.setenv("VIDEO_API_KEY", "k")
    still = tmp_path / "shot-01.png"
    still.write_bytes(b"png")

    out = _h3(still, None, "He looks up", 4.5, tmp_path / "clip.mp4", "720p")
    assert out.read_bytes() == b"an mp4"
    sent = seen[0]
    assert sent.headers["authorization"] == "Bearer k"
    body = sent.content.decode(errors="replace")
    assert 'name="start_image"' in body and 'name="end_image"' not in body
    request = json.loads(body.split('name="request"')[1].split("\r\n\r\n", 1)[1].split("\r\n--", 1)[0])
    assert request == {"prompt": "He looks up", "sound": H3_SOUND, "model": "pdmd", "resolution": "720p",
                       "aspect": "9:16", "duration": 4.5}  # fmt: skip
    assert [request.url.path for request in seen[1:]] == ["/v1/videos/vid_1"] * 3 + ["/v1/videos/vid_1/content"]


def test_h3_needs_your_video_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from shorts.animators import _h3

    monkeypatch.delenv("VIDEO_API_URL", raising=False)
    with pytest.raises(ValueError, match="VIDEO_API_URL"):
        _h3(tmp_path / "s.png", None, "p", 3, tmp_path / "c.mp4", "720p")


def test_every_image_prompt_can_be_shown_before_anything_is_drawn(animated: Run, drawn: list) -> None:
    lines = image_prompts(animated)
    assert drawn == []
    assert len(lines) == 1 + 3  # the sheet, and a still a shot
    assert lines[0].startswith("cast/man.png:\n  " + STYLE + ". Character sheet of a bald cartoon man")
    assert lines[3].startswith("stills/shot-03.png (drawn from cast/man.png, stills/shot-01.png, stills/shot-02.png):")
    assert "The picture: The man looks up." in lines[3]
