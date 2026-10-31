"""The video engine: stretches fitted to their parts, footage fitted to the frame."""

import subprocess
from pathlib import Path

import pytest

from shorts.compose import Part, compose, fills
from shorts.media import duration, executable, frame_size, has_sound

from .conftest import needs_ffmpeg, speech, video


def test_footage_fills_a_frame_of_its_shape_only() -> None:
    assert fills((720, 1280), (1080, 1920))
    assert not fills((1920, 1080), (1080, 1920))


def test_a_stretch_is_sped_up_to_fit_its_part() -> None:
    assert Part(Path("x.mp4"), length=2.0, start=4.0, end=7.0).speed == pytest.approx(1.5)
    assert Part(Path("x.mp4"), length=2.0).speed == 1.0


@needs_ffmpeg
def test_parts_one_after_another(tmp_path: Path) -> None:
    wide = video(tmp_path / "wide.mp4", 6, size="320x180")
    tall = video(tmp_path / "tall.mp4", 2, size="180x320", tone=440)
    parts = [
        Part(tall, 2.0, tall),  # its own sound
        Part(wide, 1.5, speech(tmp_path / "a.wav", 1.0), start=1.0, end=4.0),  # 3 s of it at 2x
        Part(tall, 3.0),  # silent, looping the 2-second clip
    ]
    out = compose(parts, tmp_path / "work", tmp_path / "out.mp4", size=(180, 320), captions=False)
    assert duration(out) == pytest.approx(6.5, abs=0.05)
    assert frame_size(out) == (180, 320)
    assert has_sound(out)


def black(out: Path, seconds: float, *, full_range: bool = False) -> Path:
    """Black footage: limited range, as filmed avatar clips are, or full range, as screen recordings often are."""
    form = ["-vf", "scale=out_range=pc", "-pix_fmt", "yuvj420p", "-color_range", "pc"] if full_range else []
    subprocess.run(
        [executable(), "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=180x320:r=30", "-t", str(seconds),
         *form, str(out)],
        check=True,
    )  # fmt: skip
    return out


def captioned(video: Path, at: float) -> bool:
    """Whether the frame at `at` seconds has a caption on it: white, on black footage."""
    frame = subprocess.run(
        [executable(), "-v", "error", "-ss", str(at), "-i", str(video), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True,
        check=True,
    ).stdout  # fmt: skip
    return sum(pixel > 200 for pixel in frame) > 50


@needs_ffmpeg
def test_captions_last_to_the_end_over_footage_of_any_colour_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The intro and outro (limited range) around the scenes' screen recording (full range): each is captioned."""
    pytest.importorskip("PIL", minversion="10.1")  # for ImageFont.load_default(size): Pillow's own font
    from PIL import ImageFont

    monkeypatch.setattr("shorts.captions.load_font", lambda cache: ImageFont.load_default(88))  # not downloaded
    avatar, screen = black(tmp_path / "avatar.mp4", 2), black(tmp_path / "screen.mp4", 2, full_range=True)
    parts = [Part(avatar, 2.0, text="Hi there."), Part(screen, 2.0, text="Look here."), Part(avatar, 2.0, text="Bye.")]
    out = compose(parts, tmp_path / "work", tmp_path / "out.mp4", size=(180, 320))
    assert [captioned(out, at) for at in (1.0, 3.0, 5.0)] == [True, True, True]
