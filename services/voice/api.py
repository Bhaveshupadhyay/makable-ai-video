"""The voice API: text to speech in a voice cloned from a sample, as a subset of ElevenLabs' API.

It has the same paths, header and formats as ElevenLabs, so the pipeline's client (`shorts.speech_api`) talks to it or to
ElevenLabs alike, and switching is a matter of the URL, the key and the model:

    GET    /health                           no key needed: {"status": "ok", "models": [...]}
    POST   /v1/voices/add                    multipart: name, files (the sample), transcript (what's said in it,
                                             ours: ElevenLabs ignores it), description, labels (JSON)
                                             -> {"voice_id": ..., "requires_verification": false}
    GET    /v1/voices/{voice_id}             the voice's name, labels and description
    DELETE /v1/voices/{voice_id}             {"status": "ok"}
    POST   /v1/text-to-speech/{voice_id}     JSON: text, model_id, language_code, voice_settings; ?output_format=
                                             mp3_44100_128 (the default), pcm_24000 or wav_24000 (any of RATES)

A voice speaks in its "language" label (as ElevenLabs takes labels), or a request's language_code.

Every request but /health carries the key in `xi-api-key`. Errors are ElevenLabs' shape: {"detail": {"status":
"voice_not_found", "message": "..."}}. A voice's id is a hash of its sample and transcript, so adding the same
sample again gives the same voice.

Nothing here imports Modal or a model: `app.py` serves it on Modal with the models on GPUs, and the tests serve it
with stand-ins. It needs FastAPI, python-multipart and ffmpeg.
"""

import hashlib
import hmac
import json
import logging
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Protocol

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel

MAX_TEXT = 5000  # characters a request can speak, as ElevenLabs' multilingual models
MAX_SAMPLE = 10 * 1024 * 1024  # bytes
RATES = (8000, 16000, 22050, 24000, 44100, 48000)
FORMAT = re.compile(r"(?P<kind>mp3)_(?P<rate>\d+)_(?P<kbps>\d+)|(?P<raw>pcm|wav)_(?P<raw_rate>\d+)")
VOICE_ID = re.compile(r"[0-9a-f]{20}")

log = logging.getLogger("voice")


class Speaker(Protocol):
    """A model that speaks text in the voice of a sample (a WAV file's bytes), and returns WAV bytes."""

    def say(
        self, text: str, sample: bytes, transcript: str | None, language: str, settings: dict[str, Any]
    ) -> bytes: ...


@dataclass
class Voice:
    voice_id: str
    name: str
    sample: bytes  # WAV
    transcript: str | None  # what's said in the sample: OmniVoice's reference text (None: Whisper hears it)
    labels: dict[str, str]
    description: str


class FolderVoices:
    """Voices kept in a folder: <id>/sample.wav and <id>/meta.json. `saved` runs after each change (on Modal, the
    Volume's commit, so a container started later sees it)."""

    def __init__(self, root: Path, saved: Callable[[], None] = lambda: None) -> None:
        self.root = Path(root)
        self.saved = saved

    def add(self, name: str, sample: bytes, transcript: str | None, labels: dict[str, str], description: str) -> str:
        voice_id = hashlib.sha256(sample + b"\0" + (transcript or "").encode()).hexdigest()[:20]
        folder = self.root / voice_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "sample.wav").write_bytes(sample)
        meta = {"name": name, "transcript": transcript, "labels": labels, "description": description}
        (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))
        self.saved()
        return voice_id

    def get(self, voice_id: str) -> Voice | None:
        folder = self.root / voice_id
        if not VOICE_ID.fullmatch(voice_id) or not (folder / "meta.json").exists():
            return None
        meta = json.loads((folder / "meta.json").read_text())
        sample = (folder / "sample.wav").read_bytes()
        return Voice(voice_id, meta["name"], sample, meta["transcript"], meta["labels"], meta["description"])

    def delete(self, voice_id: str) -> bool:
        if self.get(voice_id) is None:
            return False
        shutil.rmtree(self.root / voice_id)
        self.saved()
        return True


class Speech(BaseModel):
    """What to say (POST /v1/text-to-speech/{voice_id}), as ElevenLabs takes it; other fields are ignored."""

    text: str
    model_id: str = "omnivoice"
    language_code: str | None = None
    voice_settings: dict[str, float | bool | str] | None = None


def problem(code: int, status: str, message: str) -> HTTPException:
    return HTTPException(code, detail={"status": status, "message": message})


def ffmpeg(data: bytes, *args: str) -> bytes:
    """Runs ffmpeg on `data` (any audio) and returns what it writes, in the format `args` end with."""
    result = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", *args, "pipe:1"], input=data, capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors="replace").strip() or "ffmpeg failed")
    return result.stdout


def output(output_format: str) -> tuple[list[str], str]:
    """ffmpeg's options for ElevenLabs' `output_format`, mp3_<rate>_<kbps>, pcm_<rate> (16-bit mono) or
    wav_<rate>, and its media type."""
    match = FORMAT.fullmatch(output_format)
    rate = match and int(match["rate"] or match["raw_rate"])
    if not match or rate not in RATES:
        raise problem(422, "invalid_output_format", f"{output_format!r}: mp3_44100_128, pcm_24000, wav_24000, ...")
    mono = ["-ac", "1", "-ar", str(rate)]
    if match["kind"] == "mp3":
        return [*mono, "-b:a", f"{match['kbps']}k", "-f", "mp3"], "audio/mpeg"
    if match["raw"] == "pcm":
        return [*mono, "-f", "s16le"], "audio/pcm"
    return [*mono, "-f", "wav"], "audio/wav"


def create_app(voices: FolderVoices, speakers: Mapping[str, Speaker], key: str) -> FastAPI:
    """The API, with these voices, these speakers by model id ("omnivoice", "chatterbox") and this key."""
    if not key:
        raise ValueError("The API needs a key: set VOICE_API_KEY")
    app = FastAPI(title="makable voice", docs_url=None, redoc_url=None, openapi_url=None)

    def authorized(xi_api_key: Annotated[str | None, Header()] = None) -> None:
        if xi_api_key is None or not hmac.compare_digest(xi_api_key.encode(), key.encode()):
            raise problem(401, "invalid_api_key", "Send the API's key in the xi-api-key header")

    def voice(voice_id: str) -> Voice:
        found = voices.get(voice_id)
        if found is None:
            raise problem(404, "voice_not_found", f"No voice {voice_id!r}")
        return found

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "models": sorted(speakers)}

    @app.post("/v1/voices/add", dependencies=[Depends(authorized)])
    async def add_voice(
        name: Annotated[str, Form()],
        files: Annotated[list[UploadFile], File()],
        transcript: Annotated[str, Form()] = "",
        labels: Annotated[str, Form()] = "{}",
        description: Annotated[str, Form()] = "",
    ) -> dict[str, Any]:
        sample = await files[0].read(MAX_SAMPLE + 1)  # one sample: OmniVoice and Chatterbox take one
        if len(sample) > MAX_SAMPLE:
            raise problem(422, "sample_too_large", f"The sample is over {MAX_SAMPLE // 1024 // 1024} MB")
        try:
            tags = json.loads(labels or "{}")
            if not isinstance(tags, dict):
                raise ValueError
        except ValueError:
            raise problem(422, "invalid_labels", 'labels is a JSON object, such as {"language": "en"}') from None
        try:
            wav = ffmpeg(sample, "-ac", "1", "-f", "wav")
        except ValueError as error:
            raise problem(422, "invalid_audio", f"The sample isn't audio ffmpeg can read: {error}") from None
        voice_id = voices.add(
            name, wav, transcript.strip() or None, {str(k): str(v) for k, v in tags.items()}, description
        )
        log.info("Added voice %s (%s)", voice_id, name)
        return {"voice_id": voice_id, "requires_verification": False}

    @app.get("/v1/voices/{voice_id}", dependencies=[Depends(authorized)])
    def get_voice(voice_id: str) -> dict[str, Any]:
        found = voice(voice_id)
        return {
            "voice_id": found.voice_id,
            "name": found.name,
            "transcript": found.transcript,
            "labels": found.labels,
            "description": found.description,
        }

    @app.delete("/v1/voices/{voice_id}", dependencies=[Depends(authorized)])
    def delete_voice(voice_id: str) -> dict[str, str]:
        if not voices.delete(voice_id):
            raise problem(404, "voice_not_found", f"No voice {voice_id!r}")
        return {"status": "ok"}

    @app.post("/v1/text-to-speech/{voice_id}", dependencies=[Depends(authorized)])
    def text_to_speech(
        voice_id: str, speech: Speech, output_format: Annotated[str, Query()] = "mp3_44100_128"
    ) -> Response:
        found = voice(voice_id)
        if speech.model_id not in speakers:
            raise problem(
                422, "invalid_model_id", f"No model {speech.model_id!r}: one of {', '.join(sorted(speakers))}"
            )
        if not speech.text.strip() or len(speech.text) > MAX_TEXT:
            raise problem(422, "invalid_text", f"Send 1 to {MAX_TEXT} characters of text")
        options, media_type = output(output_format)  # before speaking: a GPU's time isn't spent on a bad request
        try:
            language = speech.language_code or found.labels.get("language") or "en"
            wav = speakers[speech.model_id].say(
                speech.text, found.sample, found.transcript, language, speech.voice_settings or {}
            )
        except Exception as error:
            log.exception("%s couldn't speak", speech.model_id)
            raise problem(500, "speech_failed", f"{speech.model_id} couldn't speak: {error}") from None
        return Response(ffmpeg(wav, *options), media_type=media_type)

    return app
