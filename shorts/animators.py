"""Who animates an animated Short's stills into its footage: run.json's `animator` names one.

    omni     Gemini Omni, on Agent Platform (Vertex AI) in your Google Cloud project: the still as its first frame,
             and the shot's motion as the prompt. $0.07 a second of video. animator_model picks its version.
    import   you animate each still yourself (the Gemini website, for free) and bring each clip in:
             python -m shorts import RUN footage --name shot-01 clip.mp4

Another service (fal.ai's Kling or Seedance, say) is one more `Animator` here. A take is an animator and its version,
named like "omni-1.2": `python -m shorts animate RUN --with omni-1.1,omni-1.2` animates every shot with each, to
compare them and choose.
"""

import base64
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Omni's versions, by the short names takes use
OMNI_MODELS = {"1.1": "gemini-omni-1.1-flash-preview", "1.2": "gemini-omni-1.2-flash"}
OMNI_PER_SECOND = 0.07  # dollars
CLIP_SECONDS = (4, 6, 8)  # the lengths a clip is asked for: the shortest that covers its shot
MOTION_RULES = (
    "Animate this exact image as the first frame: keep every character's face, body, clothes and colours, and the "
    "place, exactly as drawn. No text on screen, no music, no speech."
)


@dataclass(frozen=True)
class Animator:
    """A video model that animates a still, with a motion prompt, into a vertical clip."""

    name: str
    packages: tuple[str, ...]  # the modules it imports
    where: str  # what a machine needs to animate with it
    per_second: float  # dollars a second of video
    end_frame: bool  # whether it takes a last frame too (a shot's end_still)
    versions: dict[str, str]  # its models, by short name
    default: str  # the short name of the version it uses unless run.json's animator_model says another
    # (still, end still or None, motion prompt, seconds, out, model) -> out
    animate: Callable[[Path, Path | None, str, int, Path, str], Path]


def clip_seconds(shown: float) -> int:
    """The shortest clip that covers a shot on screen for `shown` seconds: the longest there is, if none does (the
    clip is then slowed to fit, by assemble)."""
    return next((seconds for seconds in CLIP_SECONDS if seconds >= math.ceil(shown - 0.05)), CLIP_SECONDS[-1])


def motion_prompt(style: str, motion: str) -> str:
    return f"{MOTION_RULES} Style: {style}. What happens: {motion}"


def _omni(still: Path, end: Path | None, prompt: str, seconds: int, out: Path, model: str) -> Path:
    from google.auth.exceptions import DefaultCredentialsError

    from .filmers import omni_client
    from .images import patiently

    google = omni_client()
    try:
        interaction = patiently(
            lambda: google.interactions.create(
                model=model,
                input=[
                    {"type": "image", "data": base64.b64encode(still.read_bytes()).decode(), "mime_type": "image/png"},
                    {"type": "text", "text": prompt},
                ],
                response_format={
                    "type": "video",
                    "aspect_ratio": "9:16",
                    "resolution": "720p",
                    "duration": f"{seconds}s",
                },
                timeout=900,
            )
        )
    except DefaultCredentialsError as error:  # the client signs in when it first asks for something
        raise ValueError("Sign in to Google Cloud once, for Omni: gcloud auth application-default login") from error
    video: Any = interaction.output_video
    if video is None or not video.data:
        raise RuntimeError(f"Omni returned no video (status {interaction.status}): {interaction.errors}")
    out.write_bytes(video.data if isinstance(video.data, bytes) else base64.b64decode(video.data))
    return out


ANIMATORS: dict[str, Animator] = {
    "omni": Animator(
        "omni",
        ("google.genai",),
        "pip install 'makable-shorts[gemini]', with GOOGLE_CLOUD_PROJECT and Google Cloud's sign-in (see the README)",
        OMNI_PER_SECOND,
        False,  # Phase 0 (2026-11-24): its API takes images, but no first or last frame
        OMNI_MODELS,
        "1.2",
        _omni,
    ),
}


def take(name: str) -> tuple[Animator, str]:
    """A take's animator and model, from its name: "omni" (its default version), "omni-1.1".

    Raises:
        ValueError: no such animator, or version.
    """
    animator_name, _, version = name.partition("-")
    animator = ANIMATORS.get(animator_name)
    if animator is None:
        raise ValueError(f"No animator {animator_name!r}: one of {', '.join(ANIMATORS)}")
    version = version or animator.default
    if version not in animator.versions:
        raise ValueError(f"{animator.name} has no version {version!r}: one of {', '.join(animator.versions)}")
    return animator, animator.versions[version]


def take_name(animator: str, model: str | None) -> str:
    """The take run.json's animator and animator_model make: "omni-1.2"."""
    found = ANIMATORS[animator]
    if model is None:
        return f"{animator}-{found.default}"
    version = next((short for short, full in found.versions.items() if model in (short, full)), None)
    if version is None:
        raise ValueError(
            f"{animator} has no model {model!r}: one of {', '.join([*found.versions, *found.versions.values()])}"
        )
    return f"{animator}-{version}"
