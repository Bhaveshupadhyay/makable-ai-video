"""The intro and the outro: Gemini Omni Flash films you saying the hook, and the sign-off, from a photo of you.

About $0.10 a second at 720p (about $1 a clip), on Agent Platform (Vertex AI) in your own Google
Cloud project: paid from its billing account, or its credits (the Free Trial's, Google AI Pro's).
The voice in the clip is Omni's: the video uses it as it is, or `voice.py` turns it into yours.
"""

import base64
import mimetypes
from pathlib import Path
from typing import Any

from .script import Script

VIDEO_MODEL = "gemini-omni-1.1-flash-preview"  # Omni, on Agent Platform: still a preview there


def avatar_prompt(line: str, setting: str) -> str:
    """What Omni is asked to film: you, in `setting`, saying `line`."""
    return (
        "Vertical selfie-style video of the person in the photo talking straight to the camera. "
        f"{setting} "
        f'They say: "{line}" '
        "Natural, friendly delivery. Quiet room, no music. No captions or text on screen."
    )


def intro_prompt(script: Script) -> str:
    return avatar_prompt(script.intro_line, script.intro_setting)


def outro_prompt(script: Script) -> str:
    """The outro, in the intro's setting unless the script gives it one: the two look like one shoot."""
    return avatar_prompt(script.outro_line, script.outro_setting or script.intro_setting)


def film(client: Any, prompt: str, face: Path, out: Path, *, model: str = VIDEO_MODEL) -> Path:
    """Generates a clip of you (9:16, 720p, with Omni's own voice) and saves it to `out`.

    Args:
        client: A `google.genai.Client` on Agent Platform, in a project with billing (Omni has no free tier):
            `genai.Client(enterprise=True, project=..., location="global")` (`filmers.omni_client`).
        prompt: What to film: `intro_prompt(script)` or `outro_prompt(script)`.
        face: A photo of you, face clearly visible.
        out: Where to save the MP4.
        model: The Omni model.

    Raises:
        RuntimeError: Omni returned no video, e.g. when its safety filters refused the photo or prompt.
    """
    interaction = client.interactions.create(
        model=model,
        input=[
            {
                "type": "image",
                "data": base64.b64encode(face.read_bytes()).decode(),
                "mime_type": mimetypes.guess_type(face.name)[0] or "image/jpeg",
            },
            {"type": "text", "text": prompt},
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
