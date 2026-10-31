"""Small wrappers around ffmpeg: imageio-ffmpeg's, which comes with the pipeline's packages, so nobody installs one.

Its builds have no ffprobe, so a file's length and streams are read from what ffmpeg prints about it.
"""

import re
import subprocess
from functools import cache
from pathlib import Path


@cache
def executable() -> str:
    """The ffmpeg to run: imageio-ffmpeg's (or the one IMAGEIO_FFMPEG_EXE names), else the one on PATH."""
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
    except ImportError:  # an environment of your own, without it
        return "ffmpeg"
    return get_ffmpeg_exe()


def ffmpeg(*args: str | Path) -> None:
    """Runs ffmpeg (overwriting outputs) and raises with its error text if it fails."""
    command = [executable(), "-hide_banner", "-loglevel", "error", "-y", *map(str, args)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()}")


def _about(path: Path) -> str:
    """What ffmpeg prints about a media file: its length, and a line for each stream."""
    # With no output, ffmpeg prints the input's details and exits with an error, whatever the file
    result = subprocess.run([executable(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    if "Input #0" not in result.stderr:
        raise RuntimeError(f"ffmpeg can't read {path}: {result.stderr.strip()}")
    return result.stderr


def duration(path: Path) -> float:
    """Returns a media file's length in seconds, to the hundredth (as ffmpeg prints it)."""
    found = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", _about(path))
    if not found:
        raise RuntimeError(f"{path} has no length")
    hours, minutes, seconds = found.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def frame_size(path: Path) -> tuple[int, int]:
    """Returns a video's width and height: its first video stream's."""
    # Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(progressive), 720x1280 [SAR 1:1 …
    found = re.search(r"Stream #[^\n]*?: Video: [^\n]*?, (\d+)x(\d+)", _about(path))
    if not found:
        raise RuntimeError(f"{path} has no video")
    return int(found[1]), int(found[2])


def still(path: Path, at: float, out: Path) -> Path:
    """Saves the frame `at` seconds into a video as an image (a PNG, say): the last one, if it's past the end."""
    at = max(0.0, min(at, duration(path) - 0.1))
    ffmpeg("-ss", f"{at:.3f}", "-i", path, "-frames:v", "1", "-update", "1", out)
    return out


def has_sound(path: Path) -> bool:
    """Whether a media file has an audio stream."""
    return re.search(r"Stream #[^\n]*?: Audio: ", _about(path)) is not None


def changes(path: Path, fps: int, pixel: int = 8, area: float = 0.15) -> list[float]:
    """Returns when a video's picture changes (seconds into it): each frame in which more than `area` % of
    the pixels got more than `pixel` (of 255) lighter or darker since the frame before."""
    # The changed pixels, averaged over a 45x80 grid (16x16-pixel cells of a 720x1280 frame): ffmpeg does
    # it 8x faster than signalstats. accurate_rnd, or a cell with nothing changed comes out 1, not 0.
    cells = 45 * 80
    result = subprocess.run(
        [
            executable(),
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
            executable(),
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
