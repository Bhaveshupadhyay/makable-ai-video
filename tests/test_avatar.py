"""The avatar's clips: the intro and the outro Omni films, and the video ending on the outro."""

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from shorts.intro import film, intro_prompt, outro_prompt
from shorts.media import duration
from shorts.orchestrator import run_all, status
from shorts.run import FILMED_INTRO, FILMED_OUTRO, FINAL, Run
from shorts.stages.base import NotReady
from shorts.stages.bring_in import bring_in
from shorts.stages.film_intro import FilmIntro, FilmOutro

from .conftest import needs_ffmpeg, script, speech, video


class Omni:
    """A stand-in for google.genai's client: it films nothing, and returns `data` as the clip."""

    vertexai = False

    def __init__(self, data: bytes) -> None:
        self.asked: list[dict] = []
        self.interactions = SimpleNamespace(create=self.create)
        self.data = data

    def create(self, **request):
        self.asked.append(request)
        return SimpleNamespace(output_video=SimpleNamespace(data=base64.b64encode(self.data).decode()), status="ok")


def with_face(run: Run, tmp_path: Path) -> Run:
    face = tmp_path / "face.jpg"
    face.write_bytes(b"jpeg")
    run.save_settings(run.settings().model_copy(update={"face": run.relative(face), "outro": "omni"}))
    return run


def test_the_outro_is_filmed_in_the_intros_setting() -> None:
    written = script((0, 2))
    written.outro_line = "Try it today."
    assert outro_prompt(written) == intro_prompt(written).replace("Hi there.", "Try it today.")
    written.outro_setting = "A park."
    assert "A park." in outro_prompt(written) and "A room." not in outro_prompt(written)


def test_changing_the_outro_line_films_only_the_outro_again(run: Run, tmp_path: Path) -> None:
    with_face(run, tmp_path)
    written = script((0, 2))
    run.path("script.json").write_text(written.model_dump_json())
    with pytest.raises(NotReady, match="no outro line"):
        FilmOutro().plan(run)

    written.outro_line = "Try it today."
    run.path("script.json").write_text(written.model_dump_json())
    intro, outro = FilmIntro().plan(run), FilmOutro().plan(run)
    written.outro_line = "Go and try it."
    run.path("script.json").write_text(written.model_dump_json())
    assert FilmIntro().plan(run) == intro
    assert FilmOutro().plan(run)[FILMED_OUTRO] != outro[FILMED_OUTRO]


def test_omni_is_asked_for_a_vertical_clip_of_the_photo(tmp_path: Path) -> None:
    face = tmp_path / "face.jpg"
    face.write_bytes(b"jpeg")
    client = Omni(b"mp4 bytes")
    film(client, "a prompt", face, tmp_path / "clip.mp4")
    assert (tmp_path / "clip.mp4").read_bytes() == b"mp4 bytes"
    [request] = client.asked
    assert request["response_format"] == {"type": "video", "aspect_ratio": "9:16", "resolution": "720p"}
    assert [part["type"] for part in request["input"]] == ["image", "text"]
    assert request["input"][1]["text"] == "a prompt"


@needs_ffmpeg
def test_the_video_ends_on_the_outro(run: Run, tmp_path: Path) -> None:
    written = script((0, 4), (6, 9))
    written.outro_line = "Try it today."
    (tmp_path / "script.json").write_text(written.model_dump_json())
    run.save_settings(run.settings().model_copy(update={"intro_voice": "as-filmed"}))
    bring_in(run, "footage", [video(tmp_path / "recording.mp4", 12)], name="demo")
    bring_in(run, "script", [tmp_path / "script.json"])
    bring_in(run, "intro", [video(tmp_path / "intro.mp4", 3, tone=330)])
    bring_in(run, "outro", [video(tmp_path / "outro.mp4", 2, tone=550)])
    bring_in(run, "narration", [speech(tmp_path / "1.wav", 1.5), speech(tmp_path / "2.wav", 2.5, 550)])

    assert run.settings().outro == "import"
    assert run.path(FILMED_INTRO).exists() and run.path(FILMED_OUTRO).exists()
    assert "outro" in {entry.product for entry in status(run) if entry.needed}
    assert run_all(run)
    # The intro, each scene as long as its narration and a pause (a second more after the last), the outro.
    assert duration(run.path(FINAL)) == pytest.approx(3 + (1.5 + 0.35) + (2.5 + 0.35 + 1) + 2, abs=0.05)
