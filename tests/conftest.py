"""Small media made with ffmpeg, and run folders to put them in."""

import shutil
import subprocess
from pathlib import Path

import pytest

from shorts.run import Run, Settings
from shorts.script import Scene, Script

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


def make(out: Path, *sources: str, seconds: float) -> Path:
    """A file made from ffmpeg's test sources (lavfi), such as "testsrc2=s=180x320:r=30"."""
    inputs = [arg for source in sources for arg in ("-f", "lavfi", "-i", source)]
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *inputs, "-t", str(seconds), "-pix_fmt", "yuv420p", str(out)],
        check=True,
    )
    return out


def video(out: Path, seconds: float, *, size: str = "180x320", tone: int | None = None) -> Path:
    sources = [f"testsrc2=s={size}:r=30"] + ([f"sine=f={tone}"] if tone else [])
    return make(out, *sources, seconds=seconds)


def speech(out: Path, seconds: float, tone: int = 440) -> Path:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=f={tone}:d={seconds}", str(out)], check=True
    )
    return out


def script(*stretches: tuple[float, float], footage: str = "demo") -> Script:
    scenes = [
        Scene(text=f"Scene {n} says this.", footage=footage, start=a, end=b) for n, (a, b) in enumerate(stretches, 1)
    ]
    return Script(intro_line="Hi there.", intro_setting="A room.", scenes=scenes, title="A title", description="Words.")


@pytest.fixture
def run(tmp_path: Path) -> Run:
    run = Run(tmp_path / "runs" / "demo")
    run.save_settings(Settings(size=(180, 320), captions=False))
    return run
