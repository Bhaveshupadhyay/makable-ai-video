"""Title cards and end cards, for a video without an avatar: a line of the script in big letters, over a still of the
recording, blurred and darkened, so the card looks like the product it's about. Drawn with Pillow, which is imported
only to draw one: assemble plans with LOOK on any machine.
"""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import ImageDraw, ImageFont

CENTER_Y = 0.45  # the line's middle, above the title and buttons Shorts and Reels draw over the bottom
FONT = 104  # pixels, in a frame 1080 wide: smaller if the line wouldn't fit
SMALLEST = 56
MARGIN = 0.1  # of the width, on either side of the line
TALLEST = 0.5  # of the height: the most the line takes
BLUR = 36  # the still's blur, in pixels of a frame 1080 wide
DARKER = 0.42  # how bright the still is kept
SHADOW = 10  # the blur of the line's shadow, in pixels of a frame 1080 wide
LOOK = (CENTER_Y, FONT, SMALLEST, MARGIN, TALLEST, BLUR, DARKER, SHADOW)  # for knowing when a card is out of date


def fitted(
    pen: "ImageDraw.ImageDraw", text: str, cache: Path, size: tuple[int, int]
) -> tuple["ImageFont.FreeTypeFont", str]:
    """The font, as big as it can be up to FONT, and the line wrapped in it, to fit the frame."""
    from .captions import load_font, wrap

    width, height = size
    points = round(FONT * width / 1080)
    while True:
        font = load_font(cache, points)
        lines = "\n".join(wrap(pen, text, font, width * (1 - 2 * MARGIN)))
        left, top, right, bottom = pen.multiline_textbbox((0, 0), lines, font=font, spacing=points // 4, align="center")
        if points <= SMALLEST or (right - left <= width * (1 - MARGIN) and bottom - top <= height * TALLEST):
            return font, lines
        points -= 6


def card(text: str, still: Path, out: Path, cache: Path, size: tuple[int, int]) -> Path:
    """Draws a card: `text` over the image `still`, which fills the frame, blurred and darkened. Saves it as a PNG.

    Args:
        text: The line.
        still: A frame of the recording.
        out: Where the card goes.
        cache: Where the font is downloaded to, once.
        size: The frame's width and height.
    """
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

    width, height = size
    scale = width / 1080
    picture = ImageOps.fit(Image.open(still).convert("RGB"), size)
    picture = picture.filter(ImageFilter.GaussianBlur(BLUR * scale))
    picture = ImageEnhance.Brightness(picture).enhance(DARKER).convert("RGBA")
    font, lines = fitted(ImageDraw.Draw(picture), text, cache, size)
    where = (width / 2, height * CENTER_Y)
    words = {"font": font, "anchor": "mm", "align": "center", "spacing": font.size // 4}
    shadow = Image.new("RGBA", size)
    ImageDraw.Draw(shadow).multiline_text((where[0], where[1] + 6 * scale), lines, fill=(0, 0, 0, 200), **words)
    picture.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(SHADOW * scale)))
    ImageDraw.Draw(picture).multiline_text(where, lines, fill="white", **words)
    picture.convert("RGB").save(out)
    return out
