"""Contact sheets: a recording's frames at given times, each labelled with its time, in one picture.

The steps say what browser-use did, not what's on screen: a preview may still be loading, or show only the top
of a page. A sheet shows what a viewer sees when, to check a recording and pick each scene's stretch. Needs
ffmpeg, and Pillow for the labels (ffmpeg's drawtext isn't in every build).
"""

import tempfile
from pathlib import Path

from .media import duration, ffmpeg


def times_every(video: Path, every: float) -> list[float]:
    """Times from the start of `video` to its end, `every` seconds apart, and its last moment."""
    length = duration(video)
    times = [round(index * every, 2) for index in range(int(length / every) + 1)]
    return times + [round(max(length - 0.1, 0.0), 2)] if length - times[-1] > every / 2 else times


def contact_sheet(video: Path, times: list[float], out: Path, *, width: int = 240, columns: int = 10) -> Path:
    """Saves the frames of `video` at `times` (seconds), labelled with them, `columns` to a row, as one PNG."""
    from PIL import Image, ImageDraw

    frames = []
    with tempfile.TemporaryDirectory() as work:
        for index, at in enumerate(times):
            frame = Path(work) / f"{index}.png"
            ffmpeg("-ss", f"{at:.3f}", "-i", video, "-frames:v", "1", "-vf", f"scale={width}:-2", frame)
            image = Image.open(frame).convert("RGB")
            ImageDraw.Draw(image).rectangle((0, 0, 64, 20), fill="white")
            ImageDraw.Draw(image).text((5, 4), f"{at:g} s", fill="red")
            frames.append(image)
    rows = -(-len(frames) // columns)
    height = max(frame.height for frame in frames)
    sheet = Image.new("RGB", (width * min(columns, len(frames)), height * rows), "black")
    for index, frame in enumerate(frames):
        sheet.paste(frame, ((index % columns) * width, (index // columns) * height))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out
