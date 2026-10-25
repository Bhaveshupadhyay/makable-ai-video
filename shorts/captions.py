"""Captions: a few words at a time, spread across each spoken part, drawn with Pillow.

Drawn as images rather than with ffmpeg's subtitles filter, because not every ffmpeg build has
libass (Homebrew's doesn't). The pictures become one video stream through an ffconcat list.
"""

import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = (1080, 1920)  # the frame the captions are drawn for, by default
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf"
CENTER_Y = 0.62  # above the title and buttons Shorts and Reels draw over the bottom


@dataclass
class Caption:
    text: str
    start: float
    end: float


def chunk_words(text: str, max_words: int = 3, max_chars: int = 16) -> list[str]:
    """Splits text into short chunks, ending one at every punctuation mark."""
    chunks: list[str] = []
    current: list[str] = []
    for word in text.split():
        if current and (len(current) == max_words or len(" ".join([*current, word])) > max_chars):
            chunks.append(" ".join(current))
            current = []
        current.append(word)
        if re.search(r"[.!?,;:]$", word):
            chunks.append(" ".join(current))
            current = []
    if current:
        chunks.append(" ".join(current))
    return chunks


def timed(text: str, start: float, end: float) -> list[Caption]:
    """Spreads the chunks of `text` over [start, end], each for a time in proportion to its length."""
    chunks = chunk_words(text)
    weights = [len(chunk) + 3 for chunk in chunks]
    captions = []
    at = start
    for chunk, weight in zip(chunks, weights, strict=True):
        length = (end - start) * weight / sum(weights)
        captions.append(Caption(chunk, at, at + length))
        at += length
    return captions


def load_font(cache: Path, size: int = 88) -> ImageFont.FreeTypeFont:
    """Montserrat ExtraBold, downloaded once into `cache`."""
    path = cache / "Montserrat.ttf"
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(FONT_URL, path)
    font = ImageFont.truetype(str(path), size)
    font.set_variation_by_axes([800])
    return font


def draw(text: str, font: ImageFont.FreeTypeFont, size: tuple[int, int] = SIZE) -> Image.Image:
    """One caption: white with a black outline, wrapped to the frame, on a transparent frame."""
    width, height = size
    image = Image.new("RGBA", size)
    pen = ImageDraw.Draw(image)
    lines: list[str] = []
    for word in text.split():
        if lines and pen.textlength(f"{lines[-1]} {word}", font=font) <= width - 160:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    pen.multiline_text(
        (width / 2, height * CENTER_Y),
        "\n".join(lines),
        font=font,
        anchor="mm",
        align="center",
        spacing=14,
        fill="white",
        stroke_width=9,
        stroke_fill="black",
    )
    return image


def render(captions: list[Caption], workdir: Path, font: ImageFont.FreeTypeFont, size: tuple[int, int] = SIZE) -> Path:
    """Draws each caption and returns an ffconcat list that shows each one for its time.

    Read it with `-f concat -i <list>`; gaps between captions show a blank frame.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    blank = workdir / "blank.png"
    Image.new("RGBA", size).save(blank)
    entries = ["ffconcat version 1.0"]
    at = 0.0
    for index, caption in enumerate(captions):
        if caption.start > at + 0.001:
            entries += [f"file {blank.name}", f"duration {caption.start - at:.3f}"]
        image = workdir / f"{index:03d}.png"
        draw(caption.text, font, size).save(image)
        entries += [f"file {image.name}", f"duration {caption.end - caption.start:.3f}"]
        at = caption.end
    entries.append(f"file {blank.name}")  # the last entry's duration is ignored
    listing = workdir / "captions.ffconcat"
    listing.write_text("\n".join(entries) + "\n")
    return listing
