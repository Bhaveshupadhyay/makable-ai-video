"""Contact sheets of a recording's frames, to see what's on screen when."""

from pathlib import Path

from PIL import Image

from shorts.sheet import contact_sheet, times_every

from .conftest import needs_ffmpeg, video


@needs_ffmpeg
def test_a_frame_every_few_seconds_and_the_last_one(tmp_path: Path) -> None:
    assert times_every(video(tmp_path / "a.mp4", 7), 2.5) == [0.0, 2.5, 5.0, 6.9]
    assert times_every(video(tmp_path / "b.mp4", 5.5), 2.5) == [0.0, 2.5, 5.0]


@needs_ffmpeg
def test_frames_go_in_rows(tmp_path: Path) -> None:
    recording = video(tmp_path / "recording.mp4", 4)  # 180x320
    sheet = contact_sheet(recording, [0, 1, 2, 3], tmp_path / "sheet.png", width=90, columns=3)
    assert Image.open(sheet).size == (90 * 3, 160 * 2)
