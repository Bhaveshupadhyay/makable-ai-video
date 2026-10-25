"""The intro: Gemini Omni Flash films you saying the hook, from a photo of you.

About $0.10 a second at 720p (about $1 a clip). Through Agent Platform (Vertex AI) it's paid from
Google Cloud credits (the Free Trial's, Google AI Pro's) with no prepaid balance; the Gemini API
(AI Studio) only takes those credits while a prepaid balance is above $0. The voice in the clip is
Omni's; `voice.py` turns it into yours.
"""

import base64
import mimetypes
from pathlib import Path
from typing import Any

from .script import Script

VIDEO_MODEL = "gemini-omni-1.1-flash"  # generally available in the Gemini API
VERTEX_VIDEO_MODEL = "gemini-omni-1.1-flash-preview"  # still a preview on Agent Platform


def video_model(client: Any) -> str:
    """Omni's id on the client's backend: Agent Platform (`enterprise=True`) or the Gemini API."""
    return VERTEX_VIDEO_MODEL if client.vertexai else VIDEO_MODEL


def intro_prompt(script: Script) -> str:
    return (
        "Vertical selfie-style video of the person in the photo talking straight to the camera. "
        f"{script.intro_setting} "
        f'They say: "{script.intro_line}" '
        "Natural, friendly delivery. Quiet room, no music. No captions or text on screen."
    )


def film_intro(client: Any, script: Script, face: Path, out: Path, *, model: str | None = None) -> Path:
    """Generates the intro clip (9:16, 720p, with Omni's own voice) and saves it to `out`.

    Args:
        client: A `google.genai.Client` on a project with billing (Omni has no free tier), either
            `genai.Client(enterprise=True, project=..., location="global")` or a Gemini API key's.
        script: The script; its `intro_line` and `intro_setting` make the prompt.
        face: A photo of you, face clearly visible.
        out: Where to save the MP4.
        model: The Omni model; by default the one for the client's backend (`video_model`).

    Raises:
        RuntimeError: Omni returned no video, e.g. when its safety filters refused the photo or prompt.
    """
    interaction = client.interactions.create(
        model=model or video_model(client),
        input=[
            {
                "type": "image",
                "data": base64.b64encode(face.read_bytes()).decode(),
                "mime_type": mimetypes.guess_type(face.name)[0] or "image/jpeg",
            },
            {"type": "text", "text": intro_prompt(script)},
        ],
        response_format={"type": "video", "aspect_ratio": "9:16", "resolution": "720p"},
        timeout=600,
    )
    video = interaction.output_video
    if video is None or not video.data:
        raise RuntimeError(f"Omni returned no video (status {interaction.status}): {interaction.errors}")
    data = video.data
    out.write_bytes(data if isinstance(data, bytes) else base64.b64decode(data))
    return out
