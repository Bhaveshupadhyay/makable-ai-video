"""Small wrappers around ffmpeg and ffprobe."""

import json
import re
import subprocess
from pathlib import Path


def ffmpeg(*args: str | Path) -> None:
    """Runs ffmpeg (overwriting outputs) and raises with its error text if it fails."""
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *map(str, args)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()}")


def duration(path: Path) -> float:
    """Returns a media file's length in seconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def frame_size(path: Path) -> tuple[int, int]:
    """Returns a video's width and height."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    stream = json.loads(result.stdout)["streams"][0]
    return stream["width"], stream["height"]


def still(path: Path, at: float, out: Path) -> Path:
    """Saves the frame `at` seconds into a video as an image (a PNG, say): the last one, if it's past the end."""
    at = max(0.0, min(at, duration(path) - 0.1))
    ffmpeg("-ss", f"{at:.3f}", "-i", path, "-frames:v", "1", "-update", "1", out)
    return out


def has_sound(path: Path) -> bool:
    """Whether a media file has an audio stream."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(json.loads(result.stdout).get("streams"))


def changes(path: Path, fps: int, pixel: int = 8, area: float = 0.15) -> list[float]:
    """Returns when a video's picture changes (seconds into it): each frame in which more than `area` % of
    the pixels got more than `pixel` (of 255) lighter or darker since the frame before."""
    # The changed pixels, averaged over a 45x80 grid (16x16-pixel cells of a 720x1280 frame): ffmpeg does
    # it 8x faster than signalstats. accurate_rnd, or a cell with nothing changed comes out 1, not 0.
    cells = 45 * 80
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-an",
            "-vf",
            f"format=gray,tblend=all_mode=difference,lutyuv=y='if(gt(val,{pixel}),255,0)',"
            "scale=45:80:flags=area+accurate_rnd",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode().strip()}")
    grids = result.stdout
    return [
        (i // cells + 1) / fps  # tblend's frame n is how frame n + 1 differs from frame n
        for i in range(0, len(grids), cells)
        if sum(grids[i : i + cells]) / (255 * cells) * 100 > area
    ]


def speech_span(path: Path, noise_db: int = -35, min_silence: float = 0.25) -> tuple[float, float]:
    """Returns when the speech in an audio file starts and ends, skipping silence at either end."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            f"silencedetect=noise={noise_db}dB:d={min_silence}",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    total = duration(path)
    starts = [float(s) for s in re.findall(r"silence_start: (-?[\d.]+)", result.stderr)]
    ends = [float(s) for s in re.findall(r"silence_end: (-?[\d.]+)", result.stderr)]
    silences = list(zip(starts, ends + [total] * (len(starts) - len(ends)), strict=False))
    begin = silences[0][1] if silences and silences[0][0] <= 0.05 else 0.0
    end = silences[-1][0] if silences and silences[-1][1] >= total - 0.05 else total
    return (begin, end) if end > begin else (0.0, total)
