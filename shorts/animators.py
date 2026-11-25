"""Who animates an animated Short's stills into its footage: run.json's `animator` names one.

    omni     Gemini Omni, on Agent Platform (Vertex AI) in your Google Cloud project: the still as its first frame,
             and the shot's motion as the prompt. $0.07 a second of video. animator_model picks its version.
    h3       MiniMax H3 on your own Modal GPU (services/video, at VIDEO_API_URL with VIDEO_API_KEY): the still as
             its first frame (and the end still as its last), the motion as the prompt, and sound effects for what
             happens, with no speech or music. 3 to 10 s clips, about 2.5 ¢ a second of GPU time.
             animator_model picks its resolution: 480 (the default), or 720, sharper and slower.
    import   you animate each still yourself (the Gemini website, for free) and bring each clip in:
             python -m shorts import RUN footage --name shot-01 clip.mp4

Another service (fal.ai's Kling or Seedance, say) is one more `Animator` here. A take is an animator and its version,
named like "omni-1.2": `python -m shorts animate RUN --with omni-1.1,omni-1.2` animates every shot with each, to
compare them and choose.
"""

import base64
import json
import math
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

# Omni's versions, by the short names takes use
OMNI_MODELS = {"1.1": "gemini-omni-1.1-flash-preview", "1.2": "gemini-omni-1.2-flash"}
OMNI_PER_SECOND = 0.07  # dollars
CLIP_SECONDS = (4, 6, 8)  # Omni's clip lengths: the shortest that covers its shot is asked for
# H3's: it makes up to 15 s, but short clips are quicker and drift less, so a long line is better split into shots
H3_SECONDS = (3.0, 4.5, 5.0, 6.5, 8.0, 10.0)
H3_PRICES = {"480p": 0.019}  # a 4.5 s clip at 480p: about 77 s of GPU time
H3_PER_SECOND = 0.025  # dollars of GPU time a second of 720p video: an H100 (about $4 an hour) takes ~100 s for 4.5 s
H3_SOUND = (
    "Only the sound effects of what happens on screen, crisp and close, and quiet ambience. No speech, no voices, no "
    "narration, no singing"
)
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
    lengths: tuple[float, ...]  # the clip lengths it makes, in seconds, shortest first
    sound: bool  # whether its clips carry sound effects worth keeping, under the narration
    # (still, end still or None, motion prompt, seconds, out, model) -> out
    animate: Callable[[Path, Path | None, str, float, Path, str], Path]
    prices: dict[str, float] = field(default_factory=dict)  # by model, where it isn't per_second

    def price(self, model: str) -> float:
        """Dollars a second of video, with `model`."""
        return self.prices.get(model, self.per_second)


def clip_seconds(shown: float, lengths: tuple[float, ...] = CLIP_SECONDS) -> float:
    """The shortest of `lengths` that covers a shot on screen for `shown` seconds: the longest there is, if none does
    (the clip is then slowed to fit, by assemble). Omni's whole-second lengths are asked for in whole seconds."""
    if all(float(length).is_integer() for length in lengths):
        shown = math.ceil(shown - 0.05)
    return next((seconds for seconds in lengths if seconds >= shown - 0.05), lengths[-1])


def motion_prompt(style: str, motion: str) -> str:
    return f"{MOTION_RULES} Style: {style}. What happens: {motion}"


def _omni(still: Path, end: Path | None, prompt: str, seconds: float, out: Path, model: str) -> Path:
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


H3_RESOLUTIONS = {"720": "720p", "480": "480p"}


def _h3(still: Path, end: Path | None, prompt: str, seconds: float, out: Path, model: str) -> Path:
    """Animates `still` on your own video API (services/video): H3 with the PDMD 4-step LoRA, at `model`'s
    resolution, 9:16, with sound effects only."""
    import httpx

    url, key = os.environ.get("VIDEO_API_URL", "").rstrip("/"), os.environ.get("VIDEO_API_KEY", "")
    if not url or not key:
        raise ValueError(
            "Set VIDEO_API_URL and VIDEO_API_KEY: your video API's address and key (services/video/README.md deploys "
            "it to your Modal account)"
        )
    if urlsplit(url).scheme != "https" and urlsplit(url).hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError(
            f"VIDEO_API_URL must be https:// (or on this machine), so the key isn't sent in the open: {url}"
        )
    request = {
        "prompt": prompt,
        "sound": H3_SOUND,
        "model": "pdmd",
        "resolution": model,
        "aspect": "9:16",
        "duration": seconds,
    }
    files = [("start_image", (still.name, still.read_bytes(), "image/png"))]
    if end is not None:
        files.append(("end_image", (end.name, end.read_bytes(), "image/png")))
    headers = {"Authorization": f"Bearer {key}"}
    with httpx.Client(base_url=url, headers=headers, timeout=120, follow_redirects=True) as api:
        answer = api.post("/v1/videos", data={"request": json.dumps(request)}, files=files)
        answer.raise_for_status()
        job = answer.json()["id"]
        while True:  # a new GPU loads the model first, about a minute; a warm one makes a clip in under a minute
            time.sleep(5)
            state = api.get(f"/v1/videos/{job}").raise_for_status().json()
            if state["status"] == "succeeded":
                break
            if state["status"] in ("failed", "cancelled"):
                raise RuntimeError(f"H3 {state['status']}: {state.get('error') or job}")
        with api.stream("GET", f"/v1/videos/{job}/content") as video, out.open("wb") as file:
            video.raise_for_status()
            for chunk in video.iter_bytes():
                file.write(chunk)
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
        CLIP_SECONDS,
        False,  # the motion prompt asks for no sound, so its clips are heard as silence
        _omni,
    ),
    "h3": Animator(
        "h3",
        ("httpx",),
        "VIDEO_API_URL and VIDEO_API_KEY: your video API on Modal (services/video/README.md)",
        H3_PER_SECOND,
        True,  # first and last frames
        H3_RESOLUTIONS,
        "480",  # 720 is sharper, at about a third more GPU time
        H3_SECONDS,
        True,
        _h3,
        H3_PRICES,
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
