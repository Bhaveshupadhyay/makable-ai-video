"""The voice API (services/voice) and the pipeline's client for it (shorts.speech_api), talking to each other in
this process, with a stand-in for the models: the same requests the pipeline sends to Modal, or to ElevenLabs."""

import subprocess
from pathlib import Path

import httpx
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("multipart")

from fastapi.testclient import TestClient  # noqa: E402

from services.voice.api import FolderVoices, create_app  # noqa: E402
from shorts.media import duration  # noqa: E402
from shorts.speech_api import SpeechAPI, SpeechAPIError  # noqa: E402

from .conftest import needs_ffmpeg, speech  # noqa: E402

KEY = "a-key"


class Tone:
    """A stand-in for OmniVoice: a beep a tenth of a second a word, as WAV, noting what it was asked."""

    def __init__(self) -> None:
        self.asked: list[tuple] = []

    def say(self, text: str, sample: bytes, transcript: str | None, language: str, settings: dict) -> bytes:
        self.asked.append((text, len(sample), transcript, language, settings))
        seconds = len(text.split()) / 10
        command = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"sine=f=440:d={seconds}", "-f", "wav", "pipe:1"]
        return subprocess.run(command, capture_output=True, check=True).stdout


@pytest.fixture
def tone() -> Tone:
    return Tone()


@pytest.fixture
def server(tmp_path: Path, tone: Tone) -> TestClient:
    app = create_app(FolderVoices(tmp_path / "voices"), {"omnivoice": tone}, key=KEY)
    return TestClient(app, base_url="http://voice")


@pytest.fixture
def api(server: TestClient) -> SpeechAPI:
    return SpeechAPI("http://voice", KEY, client=server)


def test_health_needs_no_key_and_everything_else_does(server: TestClient) -> None:
    assert server.get("/health").json() == {"status": "ok", "models": ["omnivoice"]}
    answer = server.get("/v1/voices/0123456789abcdef0123")
    assert answer.status_code == 401
    assert answer.json()["detail"]["status"] == "invalid_api_key"
    assert server.get("/v1/voices/0123456789abcdef0123", headers={"xi-api-key": "wrong"}).status_code == 401


@needs_ffmpeg
def test_speech_in_a_voice_from_a_sample(api: SpeechAPI, tone: Tone, tmp_path: Path) -> None:
    sample = speech(tmp_path / "sample.wav", 3)
    voice = api.add_voice("avatar", sample, transcript="Hi there.", language="en")
    assert api.add_voice("avatar", sample, transcript="Hi there.") == voice  # the same sample: the same voice
    assert api.add_voice("avatar", sample, transcript="Something else.") != voice

    mp3 = api.speak(voice, "one two three four five six seven eight nine ten", "omnivoice", "hi", {"speed": 1.1})
    (tmp_path / "scene.mp3").write_bytes(mp3)
    assert duration(tmp_path / "scene.mp3") == pytest.approx(1.0, abs=0.1)
    [(text, size, transcript, language, settings)] = tone.asked
    assert (transcript, language, settings) == ("Hi there.", "hi", {"speed": 1.1})
    assert size > 1000  # the sample, as WAV


@needs_ffmpeg
def test_what_the_api_refuses(api: SpeechAPI, server: TestClient, tmp_path: Path) -> None:
    voice = api.add_voice("avatar", speech(tmp_path / "sample.wav", 2))
    with pytest.raises(SpeechAPIError, match="404 No voice"):
        api.speak("0123456789abcdef0123", "Hello.", "omnivoice")
    with pytest.raises(SpeechAPIError, match="422 No model 'chatterbox'"):
        api.speak(voice, "Hello.", "chatterbox")
    with pytest.raises(SpeechAPIError, match="422 Send 1 to 5000 characters"):
        api.speak(voice, " ", "omnivoice")
    with pytest.raises(SpeechAPIError, match="422 The sample isn't audio"):
        (tmp_path / "notes.txt").write_text("not audio")
        api.add_voice("avatar", tmp_path / "notes.txt")
    headers = {"xi-api-key": KEY}
    body = {"text": "Hello.", "model_id": "omnivoice"}
    bad = server.post(f"/v1/text-to-speech/{voice}?output_format=mp3_12345_128", json=body, headers=headers)
    assert bad.status_code == 422 and bad.json()["detail"]["status"] == "invalid_output_format"
    assert server.get("/v1/voices/..%2F..%2Fetc", headers=headers).status_code == 404  # only ids, never paths


@needs_ffmpeg
def test_pcm_and_wav_as_elevenlabs_sends_them(api: SpeechAPI, server: TestClient, tmp_path: Path) -> None:
    voice = api.add_voice("avatar", speech(tmp_path / "sample.wav", 2))
    headers, body = {"xi-api-key": KEY}, {"text": "one two three four five", "model_id": "omnivoice"}
    pcm = server.post(f"/v1/text-to-speech/{voice}?output_format=pcm_24000", json=body, headers=headers)
    assert pcm.headers["content-type"] == "audio/pcm"
    assert len(pcm.content) == pytest.approx(24000 * 2 * 0.5, rel=0.05)  # 16-bit mono, half a second
    wav = server.post(f"/v1/text-to-speech/{voice}?output_format=wav_16000", json=body, headers=headers)
    assert wav.content[:4] == b"RIFF"


@needs_ffmpeg
def test_a_deleted_voice_is_gone(api: SpeechAPI, server: TestClient, tmp_path: Path) -> None:
    voice = api.add_voice("avatar", speech(tmp_path / "sample.wav", 2), transcript="Hi.")
    assert server.get(f"/v1/voices/{voice}", headers={"xi-api-key": KEY}).json()["transcript"] == "Hi."
    api.delete_voice(voice)
    with pytest.raises(SpeechAPIError, match="404"):
        api.delete_voice(voice)


def test_requests_that_fail_on_the_way_are_tried_again() -> None:
    answers = iter([httpx.Response(503), httpx.ConnectError("down"), httpx.Response(200, json={"voice_id": "v"})])

    def answer(request: httpx.Request) -> httpx.Response:
        found = next(answers)
        if isinstance(found, Exception):
            raise found
        return found

    api = SpeechAPI(
        "http://voice", KEY, client=httpx.Client(base_url="http://voice", transport=httpx.MockTransport(answer))
    )
    waits: list[float] = []
    api.sleep = waits.append
    assert api.request("GET", "/v1/voices/v").json() == {"voice_id": "v"}
    assert waits == [2.0, 4.0]

    api.tries = 1
    api.http = httpx.Client(base_url="http://voice", transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    with pytest.raises(SpeechAPIError, match="503"):
        api.request("GET", "/health")
