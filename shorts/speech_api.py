"""A client for text to speech in a cloned voice, over ElevenLabs' API or anything with its shape: our voice API on
Modal (`services/voice`), or ElevenLabs itself.

Which one is the machine's business, not the video's, so it comes from the environment: SHORTS_SPEECH_URL (our API's
URL, or https://api.elevenlabs.io) and SHORTS_SPEECH_KEY (sent as `xi-api-key`). The model is the video's: run.json's
`narrator_model` ("omnivoice" on ours, "eleven_multilingual_v2" on ElevenLabs).

Requests that fail on the way (a timeout, 429, a 5xx) are tried again, waiting longer each time. Needs httpx.
"""

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

FORMAT = "mp3_44100_128"  # what both APIs send by default
RETRIED = {408, 409, 425, 429, 500, 502, 503, 504}
REDIRECTS = 5


class SpeechAPIError(RuntimeError):
    """The API refused a request, or couldn't be reached after a few tries."""


class SpeechAPI:
    """One API, at `url`, with `key`: voices cloned from samples, and speech in them."""

    def __init__(
        self, url: str, key: str, *, client: httpx.Client | None = None, timeout: float = 300.0, tries: int = 4
    ) -> None:
        """
        Args:
            url: The API's base URL.
            key: Its key, sent in the `xi-api-key` header.
            client: An httpx client to send requests with (a test's); one of its own by default.
            timeout: Seconds to wait for an answer: the first scene starts a GPU and loads a model.
            tries: How many times to send a request that fails on the way.
        """
        self.url = url.rstrip("/")
        # Redirects are followed on the API's own host only (`send`), since the key goes with them: httpx drops only
        # Authorization on the way to another host. Modal redirects a request that runs past its web timeout.
        self.http = client or httpx.Client(base_url=self.url, timeout=timeout, follow_redirects=False)
        self.http.headers["xi-api-key"] = key
        self.tries = tries

    @classmethod
    def from_environment(cls) -> "SpeechAPI":
        url, key = os.environ.get("SHORTS_SPEECH_URL", ""), os.environ.get("SHORTS_SPEECH_KEY", "")
        if not url or not key:
            raise SpeechAPIError(
                "Set SHORTS_SPEECH_URL and SHORTS_SPEECH_KEY: the voice API's URL and key (see services/voice/app.py)"
            )
        return cls(url, key)

    def request(self, method: str, path: str, **options: Any) -> httpx.Response:
        """Sends a request, again if it fails on the way, and returns the answer, or raises SpeechAPIError."""
        for attempt in range(1, self.tries + 1):
            response: httpx.Response | None = None
            try:
                response = self.send(method, path, **options)
            except httpx.TransportError as error:
                if attempt == self.tries:
                    raise SpeechAPIError(f"{method} {path}: {error!r}, after {attempt} tries") from error
            if response is not None and (response.status_code not in RETRIED or attempt == self.tries):
                if response.is_error:
                    raise SpeechAPIError(f"{method} {path}: {response.status_code} {detail(response)}")
                return response
            self.sleep(pause(response, attempt))
        raise AssertionError("unreachable")

    sleep = staticmethod(time.sleep)  # how it waits between tries (a test's doesn't)

    def send(self, method: str, path: str, **options: Any) -> httpx.Response:
        """Sends a request once, following its redirects while they stay on the API's host."""
        response = self.http.request(method, path, **options)
        home = self.http.base_url
        for _ in range(REDIRECTS):
            target = response.next_request  # where a redirect goes, when the client doesn't follow it
            if target is None:
                break
            if (target.url.scheme, target.url.host, target.url.port) != (home.scheme, home.host, home.port):
                raise SpeechAPIError(f"{method} {path}: not following a redirect to {target.url.host}, with the key")
            response = self.http.send(target)
        if response.is_redirect:
            raise SpeechAPIError(f"{method} {path}: {response.status_code}, redirected more than {REDIRECTS} times")
        return response

    def add_voice(self, name: str, sample: Path, transcript: str | None = None, language: str | None = None) -> str:
        """Clones a voice from `sample` (what's said in it, if known, helps OmniVoice). Returns its id."""
        data = {"name": name, "labels": json.dumps({"language": language} if language else {})}
        if transcript:
            data["transcript"] = transcript
        files = {"files": (Path(sample).name, Path(sample).read_bytes(), "audio/wav")}
        return self.request("POST", "/v1/voices/add", data=data, files=files).json()["voice_id"]

    def speak(
        self, voice_id: str, text: str, model: str, language: str | None = None, settings: dict[str, Any] | None = None
    ) -> bytes:
        """`text` spoken in the voice, by `model`, as MP3."""
        body: dict[str, Any] = {"text": text, "model_id": model}
        if language:
            body["language_code"] = language
        if settings:
            body["voice_settings"] = settings
        path = f"/v1/text-to-speech/{voice_id}"
        return self.request("POST", path, params={"output_format": FORMAT}, json=body).content

    def delete_voice(self, voice_id: str) -> None:
        self.request("DELETE", f"/v1/voices/{voice_id}")


def pause(response: httpx.Response | None, attempt: int) -> float:
    """Seconds to wait before trying again: what the answer's Retry-After says, or longer after each try."""
    try:
        return min(float(response.headers.get("retry-after", "")), 60.0) if response is not None else 2.0**attempt
    except ValueError:
        return min(2.0**attempt, 30.0)


def detail(response: httpx.Response) -> str:
    """What an error answer says: ElevenLabs' {"detail": {"message": ...}}, FastAPI's list, or the text."""
    try:
        found = response.json().get("detail", response.text)
    except ValueError:
        return response.text[:500]
    if isinstance(found, dict):
        return str(found.get("message") or found)
    return str(found)[:500]
