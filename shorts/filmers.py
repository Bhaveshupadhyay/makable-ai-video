"""Who films you saying the intro line and the outro line, from a photo of you: run.json's `intro` and `outro` name one.

    omni     Gemini Omni Flash (`shorts.intro`), about $1 a clip. It films the shot the script's setting describes,
             with a voice of its own, a new one each clip. Through the Gemini API (GEMINI_API_KEY, from a prepaid
             balance) or Agent Platform (GOOGLE_GENAI_USE_ENTERPRISE=true, GOOGLE_CLOUD_PROJECT and Google's sign-in,
             from Google Cloud credits).
    heygen   HeyGen's photo to video (HEYGEN_API_KEY), from HeyGen's API balance. It animates the photo as it is,
             saying the line in one of HeyGen's voices (run.json's filmer_voice; `python -m shorts voices` lists
             them), the same voice every clip.

Or you film it with anything else (the Gemini app, HeyGen's or Higgsfield's site) and bring it in: `python -m shorts
import RUN intro CLIP`, where CLIP is a file or a link to one. Another service is one more `Filmer` here.
"""

import mimetypes
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .intro import avatar_prompt
from .run import Settings

HEYGEN = "https://api.heygen.com"
HEYGEN_MOTION = "Talks straight to the camera, relaxed and friendly, with small natural gestures."
HEYGEN_LANGUAGES = {"en": "English", "hi": "Hindi"}  # run.json's language, as HeyGen's voices name it
HEYGEN_WAIT = 30 * 60  # seconds before giving up on a clip


@dataclass(frozen=True)
class Filmer:
    """A service that films you saying a line, from a photo of you, as a vertical MP4 with its sound."""

    name: str
    packages: tuple[str, ...]  # the modules it imports
    where: str  # what a machine needs to film with it
    # What a clip is made from, besides the photo: when it changes, the clip is filmed again.
    source: Callable[[str, str, Settings], tuple[str, ...]]
    film: Callable[[str, str, Path, Path, Settings], Path]  # (line, setting, photo, out, settings) -> out


def _omni_film(line: str, setting: str, face: Path, out: Path, settings: Settings) -> Path:
    from google import genai

    from .intro import film

    return film(genai.Client(), avatar_prompt(line, setting), face, out)


def _heygen_api(key: str | None = None) -> Any:
    import httpx

    key = key or os.environ.get("HEYGEN_API_KEY")
    if not key:
        raise ValueError("Set HEYGEN_API_KEY: an API key from HeyGen (Settings, API), in .env or the environment")
    return httpx.Client(base_url=HEYGEN, headers={"x-api-key": key}, timeout=120)


def _answer(response: Any) -> dict[str, Any]:
    """HeyGen's answer, or what went wrong (its message, never the key)."""
    if response.is_error:
        raise RuntimeError(
            f"HeyGen answered {response.status_code} to {response.request.url.path}: {response.text[:400]}"
        )
    return response.json()


def heygen_voices(language: str | None = None, gender: str | None = None, *, api: Any = None) -> list[dict[str, Any]]:
    """HeyGen's voices for `language` ("English") and `gender` ("male", "female"): voice_id, name, preview."""
    voices: list[dict[str, Any]] = []
    query = {"limit": 100, **({"language": language} if language else {}), **({"gender": gender} if gender else {})}
    with api or _heygen_api() as client:
        while True:
            page = _answer(client.get("/v3/voices", params=query))
            voices += page["data"]
            if not page.get("has_more") or not page.get("next_token"):
                return voices
            query["token"] = page["next_token"]


def _heygen_film(
    line: str, setting: str, face: Path, out: Path, settings: Settings, *, api: Any = None, files: Any = None
) -> Path:
    """Films it with HeyGen: `api` and `files` (for downloads) are httpx clients, made here unless given."""
    import httpx

    if not settings.filmer_voice:
        raise ValueError(
            "HeyGen needs a voice: pick one with `python -m shorts voices`, then "
            "`python -m shorts new RUN --filmer-voice VOICE_ID`"
        )
    with api or _heygen_api() as client:
        kind = mimetypes.guess_type(face.name)[0] or "image/jpeg"
        photo = _answer(client.post("/v3/assets", files={"file": (face.name, face.read_bytes(), kind)}))
        asked = {
            "type": "image",
            "image": {"type": "asset_id", "asset_id": photo["data"]["asset_id"]},
            "script": line,
            "voice_id": settings.filmer_voice,
            "resolution": "1080p",
            "aspect_ratio": "9:16",
            "motion_prompt": HEYGEN_MOTION,
            "title": f"makable Short: {out.parent.name}",
        }
        video = _answer(client.post("/v3/videos", json=asked))["data"]["video_id"]
        deadline = time.time() + HEYGEN_WAIT
        while (made := _answer(client.get(f"/v3/videos/{video}"))["data"])["status"] != "completed":
            if made["status"] == "failed":
                raise RuntimeError(f"HeyGen couldn't film it: {made.get('failure_message') or made}")
            if time.time() > deadline:
                raise RuntimeError(f"HeyGen hadn't filmed it after {HEYGEN_WAIT // 60} minutes (video {video})")
            time.sleep(10)
    # The video's own link is on another host, so it's fetched without the key.
    with (
        files or httpx.Client(timeout=300, follow_redirects=True) as plain,
        plain.stream("GET", made["video_url"]) as download,
    ):
        download.raise_for_status()
        with out.open("wb") as file:
            for chunk in download.iter_bytes():
                file.write(chunk)
    return out


FILMERS: dict[str, Filmer] = {
    "omni": Filmer(
        "omni",
        ("google.genai",),
        "pip install 'makable-shorts[gemini]', with GEMINI_API_KEY or a Google Cloud project (see the README)",
        lambda line, setting, settings: (avatar_prompt(line, setting),),
        _omni_film,
    ),
    "heygen": Filmer(
        "heygen",
        ("httpx",),
        "pip install 'makable-shorts[heygen]', with HEYGEN_API_KEY",
        lambda line, setting, settings: (line, settings.filmer_voice or "", HEYGEN_MOTION),
        _heygen_film,
    ),
}
