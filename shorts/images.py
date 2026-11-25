"""The images an animated Short is drawn from: a character sheet for each character (`cast`), and a still for each
shot (`stills`), drawn by an image model on Agent Platform (Vertex AI), in the Google Cloud project Omni uses.

    gemini-nano-banana-2.1   Nano Banana 2.1: about $0.034 an image. Up to 4 character references, 14 in all.
    gemini-3-pro-image       Nano Banana Pro: about $0.134 an image, with better faces.

Every prompt starts with the script's style, and every still is drawn with the sheets of the characters in it as
references, so a character looks the same in every shot. The first still goes in as a style reference for the rest,
and a shot that follows on in the same place gets the shot before it too, for the room, the light and the props.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .script import Character, Script, Shot

BUSY_WAITS = (15, 30, 60, 120)  # seconds to wait before asking again, when Google says it's busy (429)

IMAGE_MODELS = {
    "gemini-nano-banana-2.1": 0.034,  # dollars an image, near enough
    "gemini-3-pro-image": 0.134,
}
NO_TEXT = "No text, letters, captions, logos or watermarks anywhere in the image."


@dataclass(frozen=True)
class Reference:
    """An image a drawing is made from, and what the prompt calls it."""

    path: Path
    what: str  # "the character sheet of man", "the first shot, for its style"


def sheet_prompt(style: str, character: Character) -> str:
    """What a character sheet is drawn from: the character, three times, in the Short's style."""
    return (
        f"{style}. Character sheet of {character.look}: the same character three times side by side, front view, "
        "three-quarter view and side view, full body, neutral standing pose, on a plain light background, evenly "
        f"lit. {NO_TEXT}"
    )


def still_prompt(style: str, shot: Shot, references: list[Reference], *, end: bool = False) -> str:
    """What a shot's still is drawn from: the style, what the references are, and what it shows (or for `end`, what
    its last frame shows)."""
    shown = shot.end_still if end else shot.still
    given = " ".join(f"Image {number} is {reference.what}." for number, reference in enumerate(references, 1))
    keep = (
        " Keep every character exactly as their character sheet draws them: face, body, clothes and colours."
        if any(reference.what.startswith("the character sheet") for reference in references)
        else ""
    )
    return f"{style}. {given}{keep} The picture: {shown}. Vertical 9:16 frame. {NO_TEXT}".replace("  ", " ")


def still_references(script: Script, index: int, sheets: dict[str, Path], stills: dict[int, Path]) -> list[Reference]:
    """The images scene `index`'s still is drawn from (counting from 0): the sheets of its characters, the first
    still (for the style), and the still before it if the shot follows on from it. `sheets` are by character name,
    and `stills` the stills drawn so far, by scene index."""
    shot = script.scenes[index].shot
    assert shot is not None
    references = [Reference(sheets[name], f"the character sheet of {name}") for name in shot.characters]
    if index > 0 and 0 in stills:
        references.append(Reference(stills[0], "the first shot of this video: match its style, light and colours"))
    if index > 1 and shot.follows and index - 1 in stills:
        references.append(
            Reference(
                stills[index - 1], "the shot just before this one, in the same place: keep the place, light and props"
            )
        )
    return references


def patiently[T](ask: Callable[[], T], waits: tuple[float, ...] = BUSY_WAITS) -> T:
    """`ask()`, asked again after a wait each time Google answers 429 (its shared quota is busy), up to len(waits)
    times."""
    for wait in (*waits, None):
        try:
            return ask()
        except Exception as error:
            if wait is None or getattr(error, "code", None) != 429:
                raise
            print(f"  Google is busy (429): asking again in {wait:g} s", flush=True)
            time.sleep(wait)
    raise AssertionError("unreachable")


def client() -> Any:
    """Gemini's client, on Agent Platform, as Omni's is (`filmers.omni_client`)."""
    from .filmers import omni_client

    return omni_client()


def draw(client: Any, prompt: str, references: list[Path], out: Path, *, model: str, aspect: str = "9:16") -> Path:
    """Draws an image from `prompt` and `references` (in order), and saves it to `out` as a PNG.

    Raises:
        RuntimeError: the model returned no image, e.g. when its safety filters refused the prompt.
    """
    from google.genai import types

    parts: list[Any] = [
        types.Part.from_bytes(data=data, mime_type="image/jpeg" if data[:3] == b"\xff\xd8\xff" else "image/png")
        for data in (path.read_bytes() for path in references)
    ]
    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"], image_config=types.ImageConfig(aspect_ratio=aspect)
    )
    answer = patiently(lambda: client.models.generate_content(model=model, contents=[*parts, prompt], config=config))
    for part in answer.candidates[0].content.parts if answer.candidates else []:
        if part.inline_data and part.inline_data.data:
            out.write_bytes(part.inline_data.data)
            return out
    reason = answer.candidates[0].finish_reason if answer.candidates else answer.prompt_feedback
    raise RuntimeError(f"{model} drew no image ({reason})")
