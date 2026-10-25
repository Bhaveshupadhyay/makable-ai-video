"""The script: an LLM turns what changed, or what a recording shows, into what's said and shown."""

from typing import Any

from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema

TEXT_MODEL = "gemini-3.8-flash"  # free tier in the Gemini API; on Agent Platform, a fraction of a cent a script
WORDS_PER_SECOND = 2.5  # how fast the narration is spoken, near enough
NARRATION = 50  # seconds of narrated recording after the 10-second intro
# The languages a script can be in, by the code Chatterbox speaks them with, and how they're written.
LANGUAGES = {
    "en": "English",
    "hi": (
        "everyday spoken Hindi, in Devanagari, the way a friendly Indian tech YouTuber talks. The English words "
        "Indians say anyway (website, preview, button, menu) stay English, written in Devanagari (वेबसाइट, प्रीव्यू). "
        "Write {product_name} in Latin letters"
    ),
}
# How the narrator sounds, by name. "hype" is the excited style of Shorts like FactoHolic's: a creator showing a
# friend something they just found, fast, with exclamations and a turn before the best part.
TONES = {
    "friendly": "Write like a person talking: short sentences, plain words",
    "hype": (
        "Write like a creator excitedly showing a friend something they just found: short, punchy sentences, plain "
        "words, an exclamation mark where something good happens, words that pull the viewer in (look, just, wait) "
        'and, before the best part, a turn like "wait, that\'s not even the best part"'
    ),
}

SYSTEM = """You write scripts for 1-minute vertical videos (YouTube Shorts, Instagram Reels) about {product}.

The video has two parts:
1. A 10-second intro: the presenter talks to the camera. `intro_line` is what they say: one hook of 14 to 20 words that makes people want to see the change. `intro_setting` describes the shot in one sentence (place, light, framing), not the person.
2. A narrated screen recording: 4 to 6 `scenes`, 110 to 130 words in all. Each scene is one or two short sentences, said over one recording named in `footage`. Use only the recording names you're given.

{tone}. No hashtags or emojis in anything that's said. End by asking people to try {product_name}.
Also write a YouTube `title` (under 70 characters) and a short `description` (2 or 3 sentences).
Write everything that's said, the `title` and the `description` in {language}."""

STEPS_SYSTEM = """You write scripts for 1-minute vertical videos (YouTube Shorts, Instagram Reels) about {product}.

The video has two parts:
1. A 10-second intro: the presenter talks to the camera. `intro_line` is what they say: one hook of 14 to 20 words that makes people want to see what happens. `intro_setting` describes the shot in one sentence (place, light, framing), not the person.
2. A narrated screen recording: 3 to 8 `scenes`, about {words} words in all. You're given what happens in each recording, step by step, with when (seconds into it). Each scene is said over one stretch of one recording: `footage` names the recording, `start` and `end` (seconds) are where the stretch begins and ends. The narration is spoken at about {rate:g} words a second, so give each scene about {rate:g} words for each second of its stretch (6 seconds: about {six} words), and pick stretches that add up to about {seconds} seconds.

Tell the story in order. The stretches play one after another and never overlap, so leave out what doesn't move the story along: retries, error messages, a name that was already taken, moments where nothing new happens. Say what's on screen while it's on screen.

A program used the site to make the recording, and the steps are in its words ("Click element [471]", "Wait 30 seconds"). Never mention it, its waits or its retries: narrate as if you were showing the viewer. A step that only waits shows what the page did meanwhile (progress, a preview loading), cut down to the moments it changed. Typed text appears on screen as it's typed. You can use facts from the program's final report, such as how long the build took or what the finished page has, but claim nothing the steps and the report don't back up: not "instantly" for something that took 30 seconds.

{tone}. No hashtags or emojis in anything that's said. End by asking people to try {product_name}.
Also write a YouTube `title` (under 70 characters) and a short `description` (2 or 3 sentences).
Write everything that's said, the `title` and the `description` in {language}."""


class Scene(BaseModel):
    text: str = Field(description="What the narrator says over this recording: one or two short sentences.")
    footage: str = Field(description="The name of the recording shown while it's said.")
    # Where in the recording the scene is, in seconds, for a script written from steps. Without them, the
    # recording plays on from where the scene before on it stopped. Not asked for by `write_script`.
    start: SkipJsonSchema[float | None] = None
    end: SkipJsonSchema[float | None] = None


class Script(BaseModel):
    intro_line: str = Field(description="What the presenter says to the camera, 14 to 20 words.")
    intro_setting: str = Field(description="The intro shot in one sentence: place, light, framing.")
    scenes: list[Scene]
    title: str
    description: str
    language: SkipJsonSchema[str] = "en"  # what it's written in (a code in LANGUAGES), so it's spoken in it


class _TimedScene(Scene):
    text: str = Field(description="What the narrator says over this stretch of the recording.")
    start: float = Field(description="Where the stretch begins, in seconds into the recording.")
    end: float = Field(description="Where the stretch ends, in seconds into the recording.")


class _TimedScript(Script):
    scenes: list[_TimedScene]


def _ask(client: Any, model: str, system: str, contents: str, schema: type[BaseModel]) -> Script:
    """Asks the model for a script, as JSON matching `schema`."""
    from google.genai import types

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )
    return Script.model_validate_json(response.text)


def written_in(language: str, product_name: str) -> str:
    """How the prompt asks for `language` (a code in `LANGUAGES`)."""
    if language not in LANGUAGES:
        raise ValueError(f"No script language {language!r}: one of {', '.join(LANGUAGES)}")
    return LANGUAGES[language].format(product_name=product_name)


def in_tone(tone: str) -> str:
    """How the prompt asks for `tone` (a name in `TONES`)."""
    if tone not in TONES:
        raise ValueError(f"No tone {tone!r}: one of {', '.join(TONES)}")
    return TONES[tone]


def write_script(
    client: Any,
    changes: str,
    footage: list[str],
    *,
    language: str = "en",
    tone: str = "friendly",
    product: str = "makable, an AI website builder",
    model: str = TEXT_MODEL,
) -> Script:
    """Asks the model for the script, as JSON matching `Script`.

    Args:
        client: A `google.genai.Client`.
        changes: What changed: commit messages, release notes, or a few lines about the feature.
        footage: The names of the recordings the scenes can use.
        language: What it's written (and later spoken) in: a code in `LANGUAGES`, "en" or "hi".
        tone: How it sounds: a name in `TONES`, "friendly" or "hype" (excited, the way Shorts creators talk).
        product: The product, as the narrator would introduce it.
        model: The Gemini text model.
    """
    product_name = product.split(",")[0]
    script = _ask(
        client,
        model,
        SYSTEM.format(
            product=product,
            product_name=product_name,
            language=written_in(language, product_name),
            tone=in_tone(tone),
        ),
        f"What changed:\n{changes}\n\nRecordings you can use: {', '.join(footage)}",
        Script,
    )
    script.language = language
    for index, scene in enumerate(script.scenes):
        if scene.footage not in footage:
            scene.footage = footage[index % len(footage)]
    return script


def recording_length(steps: list[dict[str, Any]]) -> float:
    """How long a recording is, in seconds: until its last step ends."""
    return max((step["end"] for step in steps), default=0.0)


def timeline(name: str, steps: list[dict[str, Any]]) -> str:
    """A recording's steps for the prompt, one line each: when, what the step set out to do, and what it did."""
    lines = [f'Recording "{name}" ({recording_length(steps):.1f} s):']
    for step in steps:
        when = f"{step['start']:.1f}-{step['end']:.1f} s"
        kinds = {kind for action in step["actions"] for kind in action}
        if "done" in kinds:  # its account is the run's final report
            lines.append(f"{when}: the end. The program's final report:\n" + "\n".join(step["did"]))
            continue
        did = "; ".join(" ".join(item.split()) for item in step["did"] if item)
        waits = " (only the moments the page changed are kept)" if kinds == {"wait"} else ""
        lines.append(f"{when}: {step['goal']} Did: {did}{waits}")
    return "\n".join(lines)


def write_script_from_steps(
    client: Any,
    recordings: dict[str, list[dict[str, Any]]],
    *,
    changes: str = "",
    language: str = "en",
    tone: str = "friendly",
    product: str = "makable, an AI website builder",
    model: str = TEXT_MODEL,
) -> Script:
    """Asks the model for a script narrating recordings made by `browse.record_task`, from their steps.

    Each scene is said over a stretch of a recording (`start` to `end`), picked to tell the story and
    sized to the narration, so what's said matches what's on screen. Retries and errors are left out.

    Args:
        client: A `google.genai.Client`.
        recordings: Each recording's name and its steps, as saved in its `.steps.json` (`browse.load_steps`,
            or the JSON itself). Use the steps of the video that's shown: `cut_pauses`' for `-tight.mp4`.
        changes: What changed, if the video is about a change; the steps are enough otherwise.
        language: What it's written (and later spoken) in: a code in `LANGUAGES`, "en" or "hi".
        tone: How it sounds: a name in `TONES`, "friendly" or "hype" (excited, the way Shorts creators talk).
        product: The product, as the narrator would introduce it.
        model: The Gemini text model.
    """
    recordings = {
        name: [step if isinstance(step, dict) else vars(step) for step in steps] for name, steps in recordings.items()
    }
    lengths = {name: recording_length(steps) for name, steps in recordings.items()}
    seconds = round(min(NARRATION, sum(lengths.values())))
    product_name = product.split(",")[0]
    system = STEPS_SYSTEM.format(
        product=product,
        product_name=product_name,
        language=written_in(language, product_name),
        tone=in_tone(tone),
        words=round(seconds * WORDS_PER_SECOND),
        rate=WORDS_PER_SECOND,
        six=round(6 * WORDS_PER_SECOND),
        seconds=seconds,
    )
    contents = "\n\n".join(timeline(name, steps) for name, steps in recordings.items())
    if changes:
        contents = f"What changed:\n{changes}\n\n{contents}"
    script = _ask(client, model, system, contents, _TimedScript)
    script.language = language
    names = list(recordings)
    for index, scene in enumerate(script.scenes):
        if scene.footage not in recordings:
            scene.footage = names[index % len(names)]
        length = lengths[scene.footage]
        scene.start = min(max(scene.start or 0.0, 0.0), length)
        scene.end = min(max(scene.end or length, scene.start), length)
    return script
