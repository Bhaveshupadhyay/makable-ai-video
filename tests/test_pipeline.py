"""Bringing files in, and the orchestrator making the video from them, a stage per process."""

import json
from pathlib import Path

import pytest

from shorts.media import duration
from shorts.orchestrator import run_all, status
from shorts.run import FINAL, Run, narration_file
from shorts.stages.base import CURRENT, STALE
from shorts.stages.bring_in import bring_in, in_order, without_copies

from .conftest import needs_ffmpeg, script, speech, video


def test_narration_goes_in_the_order_browsers_number_downloads() -> None:
    names = ["download (10).wav", "download (2).wav", "download.wav", "download (1).wav"]
    assert [path.name for path in in_order([Path(name) for name in names])] == [
        "download.wav",
        "download (1).wav",
        "download (2).wav",
        "download (10).wav",
    ]


def test_a_file_downloaded_twice_is_left_out(tmp_path: Path) -> None:
    files = []
    for name, data in [("a.wav", b"1"), ("b.wav", b"2"), ("c.wav", b"2")]:
        files.append(tmp_path / name)
        files[-1].write_bytes(data)
    assert [path.name for path in without_copies(files)] == ["a.wav", "b.wav"]


@needs_ffmpeg
def test_narration_needs_one_file_a_scene(run: Run, tmp_path: Path) -> None:
    (tmp_path / "script.json").write_text(script((0, 2), (2, 4)).model_dump_json())
    bring_in(run, "script", [tmp_path / "script.json"])
    with pytest.raises(ValueError, match="2 scenes, but there are 1"):
        bring_in(run, "narration", [speech(tmp_path / "one.wav", 1)])


@needs_ffmpeg
def test_the_video_from_files_made_elsewhere(run: Run, tmp_path: Path) -> None:
    recording = video(tmp_path / "recording.mp4", 12)
    (tmp_path / "recording.steps.json").write_text("[]")
    (tmp_path / "script.json").write_text(script((0, 4), (6, 9)).model_dump_json())
    bring_in(run, "footage", [recording], name="demo")
    bring_in(run, "script", [tmp_path / "script.json"])
    bring_in(run, "voiced-intro", [video(tmp_path / "intro.mp4", 3, tone=330)])
    clips = [speech(tmp_path / "download.wav", 1.5), speech(tmp_path / "download (1).wav", 2.5, 550)]
    bring_in(run, "narration", list(reversed(clips)))  # put back in order by their numbers

    entries = {entry.product: entry for entry in status(run)}
    assert not entries["intro"].needed  # the voiced intro came in: Omni's clip isn't needed
    assert entries["video"].summary() == "2 missing"

    assert run_all(run)
    assert run.path("footage/demo.steps.json").exists()
    # The intro, then each scene as long as its narration and a pause (and a second more after the last).
    assert duration(run.path(FINAL)) == pytest.approx(3 + (1.5 + 0.35) + (2.5 + 0.35 + 1), abs=0.05)
    assert json.loads(run.path("metadata.json").read_text())["title"] == "A title"

    # Editing a scene's text makes its narration out of date, and only its: the pipeline asks for it again.
    edited = script((0, 4), (6, 9))
    edited.scenes[1].text = "Something else."
    run.path("script.json").write_text(edited.model_dump_json())
    entries = {entry.product: entry for entry in status(run)}
    assert entries["narration"].files == {narration_file(0): CURRENT, narration_file(1): STALE}
    assert not run_all(run)
