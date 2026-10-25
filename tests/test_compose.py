"""The video engine: stretches fitted to their parts, footage fitted to the frame."""

import subprocess
from pathlib import Path

import pytest

from shorts.compose import Part, compose, fills
from shorts.media import duration, frame_size

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
    streams = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert sorted(streams) == ["audio", "video"]
