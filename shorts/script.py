"""The script: what's said and shown (script.json), as Claude writes it (the make-video skill), and the check it
passes before the video is made from it.

How to write one is in skills/make-video/references/script.md: these are the format and the numbers the
check holds it to.
"""

import re
from collections.abc import Collection
from typing import Any

from pydantic import BaseModel

from .compose import GAP

WORDS_PER_SECOND = 2.5  # how fast the narration is spoken, near enough, and the captions read without it
NARRATION = 50  # seconds of narrated recording, between the intro and the outro
LANGUAGES = ("en", "hi")  # what a script can be written and spoken in
TONES = ("friendly", "hype")  # how it sounds: like a person talking, or excited, like a Short


class Scene(BaseModel):
    # What the narrator says over its stretch of a recording, one or two short sentences: or in a video without a
    # voice, what the captions say
    text: str
    footage: str  # the recording's name in run.json
    # Where in the recording the scene is, in seconds. Without them, the recording plays on from where the scene
    # before on it stopped.
    start: float | None = None
    end: float | None = None


class Script(BaseModel):
    intro_line: str  # what the avatar says to the camera, 14 to 20 words: or what a title card says, in fewer
    intro_setting: str  # the intro's shot in one sentence: place, light, framing ("" for a card)
    scenes: list[Scene]
    title: str
    description: str
    # The outro: the avatar again, after the recording, or an end card. Its line is needed unless run.json's outro
    # is "none"; without a setting, it's filmed in the intro's, so the two look like one shoot.
    outro_line: str = ""
    outro_setting: str = ""
    language: str = "en"  # what it's written in (one of LANGUAGES), so it's spoken in it


def recording_length(steps: list[dict[str, Any]]) -> float:
    """How long a recording is, in seconds: until its last step ends."""
    return max((step["end"] for step in steps), default=0.0)


# What `check` holds a script to, beyond what its fields require.
INTRO_WORDS = (14, 20)  # the intro line, to fit Omni's 10-second clip
OUTRO_WORDS = 20  # at most, for the outro's clip
CARD_WORDS = 12  # at most, for a title card or an end card to read at a glance
SCENES = (3, 8)
SPEEDS = (0.6, 2.5)  # how much slower or faster than real time a stretch can play and still look right
SHORTEST = 1.0  # seconds: the shortest stretch of a recording a scene can be said over
SAID = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]|#\w")  # emoji and hashtags, which aren't said


def words(text: str) -> int:
    return len(text.split())


def on_screen(scene: Scene, silent: bool = False) -> float:
    """How long a scene lasts, in seconds, near enough: as long as its narration and a pause. In a video without a
    voice (`silent`), its stretch plays at its own speed, or slower if its words take longer to read."""
    said = words(scene.text) / WORDS_PER_SECOND + GAP
    if silent and scene.start is not None and scene.end is not None:
        return max(scene.end - scene.start, said)
    return said


def speed(scene: Scene, silent: bool = False) -> float | None:
    """How fast a scene's stretch will play, near enough (1: real time), or None for a scene without one.
    `assemble` plays it for as long as the narration and a pause (`on_screen`)."""
    if scene.start is None or scene.end is None:
        return None
    return (scene.end - scene.start) / on_screen(scene, silent)


def check(
    script: Script,
    lengths: dict[str, float | None],
    timed: Collection[str] = (),
    *,
    outro: bool = False,
    cards: Collection[str] = (),
    silent: bool = False,
) -> tuple[list[str], list[str]]:
    """What's wrong with a script, checked against the recordings it's said over: errors (the video can't be
    made from it as it is) and warnings (it can, but it may not look or sound right).

    Args:
        script: The script.
        lengths: Each recording the run has, by name, and how long it is in seconds (None: not known yet).
            With none, the scenes' recordings aren't checked.
        timed: The recordings that have steps: a scene said over one of them says where (`start`, `end`).
        outro: Whether the video has an outro (run.json's outro isn't "none"), which needs a line.
        cards: Which of "intro" and "outro" are cards, not clips (a video without an avatar).
        silent: Whether the video has no voice: its scenes are read, in the captions, not heard.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not script.intro_line.strip():
        errors.append("The intro line is empty")
    elif "intro" in cards:
        if words(script.intro_line) > CARD_WORDS:
            warnings.append(f"The title card's line has {words(script.intro_line)} words: keep it to {CARD_WORDS}")
    elif not INTRO_WORDS[0] <= words(script.intro_line) <= INTRO_WORDS[1]:
        warnings.append(f"The intro line has {words(script.intro_line)} words: 14 to 20 fit Omni's 10-second clip")
    if outro and not script.outro_line.strip():
        errors.append('The outro line is empty, and run.json wants an outro (or set its outro to "none")')
    if "outro" in cards and words(script.outro_line) > CARD_WORDS:
        warnings.append(f"The end card's line has {words(script.outro_line)} words: keep it to {CARD_WORDS}")
    elif words(script.outro_line) > OUTRO_WORDS:
        warnings.append(f"The outro line has {words(script.outro_line)} words: keep it to {OUTRO_WORDS} or fewer")
    if not SCENES[0] <= len(script.scenes) <= SCENES[1]:
        warnings.append(f"The script has {len(script.scenes)} scenes: {SCENES[0]} to {SCENES[1]} tell a minute's story")

    stretches: dict[str, list[tuple[float, float, int]]] = {}  # each recording's stretches so far, and their scenes
    for number, scene in enumerate(script.scenes, 1):
        if lengths and scene.footage not in lengths:
            errors.append(f"Scene {number} is said over {scene.footage!r}, which isn't one of {', '.join(lengths)}")
            continue
        if scene.start is None or scene.end is None:
            if scene.footage in timed:
                errors.append(f"Scene {number} has no start and end, though {scene.footage!r} has steps")
            continue
        stretch, length = f"{scene.start:g}-{scene.end:g} s", lengths.get(scene.footage)
        if scene.end - scene.start < SHORTEST:
            errors.append(f"Scene {number}'s stretch ({stretch}) is shorter than {SHORTEST:g} s")
        elif scene.start < 0 or (length is not None and scene.end > length + 0.05):
            bounds = f" (0-{length:.1f} s)" if length is not None else ""
            errors.append(f"Scene {number}'s stretch ({stretch}) isn't all in {scene.footage!r}{bounds}")
        rate = speed(scene, silent)
        if rate is not None and not SPEEDS[0] <= rate <= SPEEDS[1]:
            fix = "say more over it, or take a shorter stretch" if rate > SPEEDS[1] else "say less, or take more"
            warnings.append(f"Scene {number}'s stretch would play at about {rate:.1f}x: {fix}")
        before = stretches.setdefault(scene.footage, [])
        for start, end, other in before:
            if scene.start < end - 0.05 and start < scene.end - 0.05:
                errors.append(f"Scenes {other} and {number} overlap in {scene.footage!r}: the stretches never do")
        if before and scene.start < before[-1][0]:
            warnings.append(f"Scene {number} goes back to before scene {before[-1][2]} in {scene.footage!r}")
        before.append((scene.start, scene.end, number))

    known = [length for length in lengths.values() if length is not None]
    target = min(NARRATION, sum(known)) if known else NARRATION
    if silent:
        seconds = sum(on_screen(scene, silent) for scene in script.scenes)
        long = f"The scenes last about {seconds:.0f} s"
    else:
        seconds = sum(words(scene.text) for scene in script.scenes) / WORDS_PER_SECOND
        long = f"The narration is about {seconds:.0f} s long"
    if abs(seconds - target) > 0.25 * target:
        warnings.append(f"{long}: aim for about {target:.0f} s")
    if len(script.title) >= 70:
        warnings.append(f"The title has {len(script.title)} characters: YouTube shows fewer than 70")
    said = [script.intro_line, script.outro_line, *(scene.text for scene in script.scenes)]
    if any(SAID.search(text) for text in said):
        cant = "the captions can't show" if silent else "the narrator can't say"
        warnings.append(f"Something that's said has an emoji or a hashtag, which {cant}")
    if silent and any(not scene.text.strip() for scene in script.scenes):
        warnings.append("A scene has no text: without a voice, the captions are all that says what's happening")
    return errors, warnings
