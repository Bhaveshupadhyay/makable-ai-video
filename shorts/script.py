"""The script: what's said and shown (script.json), as Claude writes it (the make-video skill), and the check it
passes before the video is made from it.

How to write one is in .claude/skills/make-video/references/script.md: these are the format and the numbers the
check holds it to.
"""

import re
from collections.abc import Collection
from typing import Any

from pydantic import BaseModel

from .compose import GAP

WORDS_PER_SECOND = 2.5  # how fast the narration is spoken, near enough
NARRATION = 50  # seconds of narrated recording, between the intro and the outro
LANGUAGES = ("en", "hi")  # what a script can be written and spoken in
TONES = ("friendly", "hype")  # how it sounds: like a person talking, or excited, like a Short


class Scene(BaseModel):
    text: str  # what the narrator says over its stretch of a recording: one or two short sentences
    footage: str  # the recording's name in run.json
    # Where in the recording the scene is, in seconds. Without them, the recording plays on from where the scene
    # before on it stopped.
    start: float | None = None
    end: float | None = None


class Script(BaseModel):
    intro_line: str  # what the avatar says to the camera, 14 to 20 words
    intro_setting: str  # the intro's shot in one sentence: place, light, framing
    scenes: list[Scene]
    title: str
    description: str
    # The outro: the avatar again, after the recording. Its line is needed unless run.json's outro is "none";
    # without a setting, it's filmed in the intro's, so the two look like one shoot.
    outro_line: str = ""
    outro_setting: str = ""
    language: str = "en"  # what it's written in (one of LANGUAGES), so it's spoken in it


def recording_length(steps: list[dict[str, Any]]) -> float:
    """How long a recording is, in seconds: until its last step ends."""
    return max((step["end"] for step in steps), default=0.0)


# What `check` holds a script to, beyond what its fields require.
INTRO_WORDS = (14, 20)  # the intro line, to fit Omni's 10-second clip
OUTRO_WORDS = 20  # at most, for the outro's clip
SCENES = (3, 8)
SPEEDS = (0.6, 2.5)  # how much slower or faster than real time a stretch can play and still look right
SHORTEST = 1.0  # seconds: the shortest stretch of a recording a scene can be said over
SAID = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]|#\w")  # emoji and hashtags, which aren't said


def words(text: str) -> int:
    return len(text.split())


def speed(scene: Scene) -> float | None:
    """How fast a scene's stretch will play once its narration is spoken, near enough (1: real time), or None
    for a scene without one. `assemble` plays it for as long as the narration and a pause."""
    if scene.start is None or scene.end is None:
        return None
    return (scene.end - scene.start) / (words(scene.text) / WORDS_PER_SECOND + GAP)


def check(
    script: Script, lengths: dict[str, float | None], timed: Collection[str] = (), *, outro: bool = False
) -> tuple[list[str], list[str]]:
    """What's wrong with a script, checked against the recordings it's said over: errors (the video can't be
    made from it as it is) and warnings (it can, but it may not look or sound right).

    Args:
        script: The script.
        lengths: Each recording the run has, by name, and how long it is in seconds (None: not known yet).
            With none, the scenes' recordings aren't checked.
        timed: The recordings that have steps: a scene said over one of them says where (`start`, `end`).
        outro: Whether the video has an outro (run.json's outro isn't "none"), which needs a line.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not script.intro_line.strip():
        errors.append("The intro line is empty")
    elif not INTRO_WORDS[0] <= words(script.intro_line) <= INTRO_WORDS[1]:
        warnings.append(f"The intro line has {words(script.intro_line)} words: 14 to 20 fit Omni's 10-second clip")
    if outro and not script.outro_line.strip():
        errors.append('The outro line is empty, and run.json wants an outro (or set its outro to "none")')
    if words(script.outro_line) > OUTRO_WORDS:
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
        rate = speed(scene)
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
    seconds = sum(words(scene.text) for scene in script.scenes) / WORDS_PER_SECOND
    if abs(seconds - target) > 0.25 * target:
        warnings.append(f"The narration is about {seconds:.0f} s long: aim for about {target:.0f} s")
    if len(script.title) >= 70:
        warnings.append(f"The title has {len(script.title)} characters: YouTube shows fewer than 70")
    said = [script.intro_line, script.outro_line, *(scene.text for scene in script.scenes)]
    if any(SAID.search(text) for text in said):
        warnings.append("Something that's said has an emoji or a hashtag, which the narrator can't say")
    return errors, warnings
