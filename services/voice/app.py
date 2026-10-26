"""The voice API on Modal: `api.create_app` in a small CPU container, and each model on a GPU of its own.

OmniVoice and Chatterbox can't share an environment (Chatterbox pins an older transformers), so each has its own
image and its own container, which loads the model once and speaks scene after scene. A GPU container stops
`IDLE` seconds after its last scene, so it costs nothing between videos, and there's at most one of each, so a
burst of requests waits instead of starting more GPUs. Models download into a Volume the first time, so
later containers start without downloading again.

Set up once (`pip install modal`, then `modal setup` to sign in):

    modal secret create makable-voice VOICE_API_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
    modal deploy -m services.voice.app        # from the repo's root; prints the API's URL

`modal serve -m services.voice.app` serves your working copy at a temporary URL while you work on it. The pipeline
calls the API with SHORTS_SPEECH_URL (the URL) and SHORTS_SPEECH_KEY (the key).
"""

import os
import tempfile
from pathlib import Path

import modal

GPU = "T4"  # enough for both models; "L4" is faster and costs more
IDLE = 120  # seconds a GPU container waits for the next request before it stops
MODELS = "/models"  # Hugging Face's cache, on the Volume
VOICES = "/voices"

app = modal.App("makable-voice")
models = modal.Volume.from_name("makable-voice-models", create_if_missing=True)
voices = modal.Volume.from_name("makable-voices", create_if_missing=True)


def image(*packages: str, torch: tuple[str, ...] = ()) -> modal.Image:
    """Debian with ffmpeg, these packages (torch's first, from its CUDA index), and this code (models.py)."""
    base = modal.Image.debian_slim(python_version="3.12").apt_install("ffmpeg")
    if torch:
        base = base.uv_pip_install(*torch, index_url="https://download.pytorch.org/whl/cu126")
    return base.uv_pip_install(*packages).env({"HF_HOME": MODELS}).add_local_python_source("services")


# OmniVoice uses transformers' internals: the transformers of its release, not whatever came out since.
omnivoice_image = image(
    "omnivoice==0.2.1", "transformers==5.14.1", "soundfile", torch=("torch==2.8.0", "torchaudio==2.8.0")
)
chatterbox_image = image("chatterbox-tts")
web_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .uv_pip_install("fastapi[standard]", "python-multipart")
    .add_local_python_source("services")
)
gpu = {"gpu": GPU, "volumes": {MODELS: models}, "scaledown_window": IDLE, "max_containers": 1, "timeout": 600}


def speak_with(say, sample: bytes) -> bytes:
    """Writes the sample to a file for a model to read, has `say(reference, out)` speak into a file, returns it."""
    with tempfile.TemporaryDirectory() as work:
        reference, out = Path(work) / "sample.wav", Path(work) / "speech.wav"
        reference.write_bytes(sample)
        say(reference, out)
        return out.read_bytes()


@app.cls(image=omnivoice_image, **gpu)
class OmniVoiceSpeaker:
    @modal.enter()
    def load(self) -> None:
        from services.voice.models import OmniVoiceModel

        self.model = OmniVoiceModel("cuda")
        models.commit()  # what it downloaded, for the containers after it

    @modal.method()
    def say(self, text: str, sample: bytes, transcript: str | None, language: str, settings: dict) -> bytes:
        return speak_with(
            lambda reference, out: self.model.say(text, reference, transcript, language, settings, out), sample
        )


@app.cls(image=chatterbox_image, **gpu)
class ChatterboxSpeaker:
    @modal.enter()
    def load(self) -> None:
        from services.voice.models import ChatterboxModel

        self.model = ChatterboxModel("cuda")
        self.model.model(multilingual=False)  # English now; the multilingual model loads for the first other language
        models.commit()

    @modal.method()
    def say(self, text: str, sample: bytes, transcript: str | None, language: str, settings: dict) -> bytes:
        return speak_with(
            lambda reference, out: self.model.say(text, reference, transcript, language, settings, out), sample
        )


class Remote:
    """A speaker in its own GPU container, called as if it were here."""

    def __init__(self, speaker) -> None:
        self.speaker = speaker

    def say(self, text: str, sample: bytes, transcript: str | None, language: str, settings: dict) -> bytes:
        return self.speaker.say.remote(text, sample, transcript, language, settings)


@app.function(
    image=web_image,
    volumes={VOICES: voices},
    secrets=[modal.Secret.from_name("makable-voice")],
    max_containers=1,  # the voices it adds are in its Volume at once, for the next request
    scaledown_window=300,
)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def web():
    from services.voice.api import FolderVoices, create_app

    speakers = {"omnivoice": Remote(OmniVoiceSpeaker()), "chatterbox": Remote(ChatterboxSpeaker())}
    return create_app(FolderVoices(Path(VOICES), saved=voices.commit), speakers, key=os.environ["VOICE_API_KEY"])
