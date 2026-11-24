"""The video API: MiniMax H3 video + audio as jobs, since a clip takes minutes.

    GET    /health                      no key needed: {"status": "ok", "models": [...]}
    GET    /v1/models                   the models, their steps and what each takes
    GET    /v1/loras                    the LoRAs that can be named (any Hugging Face .safetensors link works too)
    POST   /v1/prompts                  the H3 prompt and settings a request would run with, without running it
    POST   /v1/videos                   starts a video -> 202 {"id": "vid_…", "status": "queued", ...}
    GET    /v1/videos                   the latest jobs, newest first (?limit=20)
    GET    /v1/videos/{id}              a job: status (queued, running, succeeded, failed, cancelled), progress
                                        0-1, phase, error, seed, size, timings
    GET    /v1/videos/{id}/content      the MP4 (H.264 + AAC 32 kHz stereo), once it has succeeded
    POST   /v1/videos/{id}/cancel       stops it (a queued job never starts)
    DELETE /v1/videos/{id}              forgets it and deletes its MP4

POST /v1/prompts and /v1/videos take either JSON (a request, for text to video) or multipart/form-data: the request
as JSON in a `request` field, and any of the files `start_image`, `end_image`, `references` (up to 3), `voice` (a
voice to clone, ref models) and `soundtrack` (audio the video follows and keeps, such as narration). The request's
fields are `h3.VideoRequest`'s.

Every request but /health carries the key, as `Authorization: Bearer <key>` or `x-api-key: <key>`. Errors are
{"detail": {"status": "…", "message": "…"}}.

Nothing here imports Modal or a model: `app.py` serves it on Modal with the model on a GPU, and the tests serve it
with stand-ins. It needs FastAPI, python-multipart, Pillow and ffmpeg (ffprobe).
"""

import hmac
import io
import logging
import secrets
import subprocess
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Any, Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from starlette.background import BackgroundTask

from . import h3

MAX_IMAGE = 20 * 1024 * 1024  # bytes
MAX_AUDIO = 25 * 1024 * 1024
MIN_VOICE = 2.0  # seconds a voice to clone needs, at least
FILES = ("start_image", "end_image", "references", "voice", "soundtrack")
DONE = ("succeeded", "failed", "cancelled")

log = logging.getLogger("video")


class Jobs(Protocol):
    """Where jobs are kept, by id (on Modal, a Dict that the GPU's container updates as it works)."""

    def get(self, job_id: str) -> dict | None: ...
    def put(self, job: dict) -> None: ...
    def delete(self, job_id: str) -> None: ...
    def all(self) -> Iterable[dict]: ...
    def cancel(self, job_id: str) -> None: ...  # asks the job that runs to stop
    def set_handle(self, job_id: str, handle: str) -> None: ...  # kept apart: the GPU updates the job meanwhile
    def handle(self, job_id: str) -> str | None: ...


class Runner(Protocol):
    """Starts a job on the GPU, and returns what `stop` and `ended` take."""

    def start(self, job: dict, files: dict[str, Any]) -> str: ...
    def stop(self, handle: str) -> None: ...
    def ended(self, handle: str) -> str | None: ...  # why the call has ended (it timed out...), or None: it hasn't


class Videos(Protocol):
    """The MP4s jobs made, by job id."""

    def copy(self, job_id: str) -> Path | None: ...  # a temporary copy of it, which the caller deletes
    def delete(self, job_id: str) -> None: ...


def problem(code: int, status: str, message: str) -> HTTPException:
    return HTTPException(code, detail={"status": status, "message": message})


def image_size(data: bytes, name: str) -> tuple[int, int]:
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            return image.size
    except Exception:
        raise problem(422, "invalid_image", f"{name} isn't an image Pillow can read") from None


def audio_seconds(data: bytes, name: str) -> float:
    with tempfile.NamedTemporaryFile() as file:  # from a pipe, ffprobe can't tell a WAV's duration
        file.write(data)
        file.flush()
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", file.name],
            capture_output=True,
        )
    try:
        return float(probe.stdout.decode().strip())
    except ValueError:
        raise problem(422, "invalid_audio", f"{name} isn't audio ffmpeg can read") from None


def public(job: dict) -> dict:
    """A job as the API shows it (without what only the GPU needs)."""
    return {k: v for k, v in job.items() if k != "settings"}


def create_app(jobs: Jobs, runner: Runner, videos: Videos, key: str) -> FastAPI:
    if not key:
        raise ValueError("The API needs a key: set VIDEO_API_KEY")
    app = FastAPI(title="makable video", docs_url=None, redoc_url=None, openapi_url=None)

    def authorized(
        authorization: Annotated[str | None, Header()] = None, x_api_key: Annotated[str | None, Header()] = None
    ) -> None:
        given = x_api_key or (authorization or "").removeprefix("Bearer ").strip()
        if not given or not hmac.compare_digest(given.encode(), key.encode()):
            raise problem(401, "invalid_api_key", "Send the key as `Authorization: Bearer <key>` or `x-api-key`")

    def job(job_id: str) -> dict:
        found = jobs.get(job_id)
        if found is None:
            raise problem(404, "job_not_found", f"No job {job_id!r}")
        return found

    async def read(request: Request) -> tuple[h3.VideoRequest, h3.Media, dict[str, Any]]:
        """The request, its media (with the files' names as their paths) and the files' bytes."""
        files: dict[str, Any] = {}
        if request.headers.get("content-type", "").startswith("multipart/form-data"):
            form = await request.form()
            raw = form.get("request") or "{}"
            for name in FILES:
                uploads = [u for u in form.getlist(name) if hasattr(u, "read")]
                if name == "references":
                    files[name] = [(u.filename or f"reference-{i}", await u.read()) for i, u in enumerate(uploads)]
                elif uploads:
                    files[name] = (uploads[0].filename or name, await uploads[0].read())
            unknown = set(form.keys()) - {"request", *FILES}
            if unknown:
                raise problem(422, "unknown_field", f"Unknown fields {sorted(unknown)}: send the request as JSON in `request`")
        else:
            raw = (await request.body()).decode() or "{}"
        try:
            video = h3.VideoRequest.model_validate_json(raw if isinstance(raw, str) else "{}")
        except ValidationError as error:
            messages = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
            raise problem(422, "invalid_request", messages) from None
        media = h3.Media()
        for name in ("start_image", "end_image"):
            if name in files:
                filename, data = files[name]
                if len(data) > MAX_IMAGE:
                    raise problem(422, "file_too_large", f"{name} is over {MAX_IMAGE >> 20} MB")
                path = f"{name}/{filename}"
                media.sizes[path] = image_size(data, name)
                setattr(media, name, path)
        for i, (filename, data) in enumerate(files.get("references", [])):
            if len(data) > MAX_IMAGE:
                raise problem(422, "file_too_large", f"reference {i + 1} is over {MAX_IMAGE >> 20} MB")
            path = f"references/{i}-{filename}"
            media.sizes[path] = image_size(data, f"reference {i + 1}")
            media.references.append(path)
        for name in ("voice", "soundtrack"):
            if name in files:
                filename, data = files[name]
                if len(data) > MAX_AUDIO:
                    raise problem(422, "file_too_large", f"{name} is over {MAX_AUDIO >> 20} MB")
                seconds = audio_seconds(data, name)
                if name == "voice" and seconds < MIN_VOICE:
                    raise problem(422, "voice_too_short", f"The voice is {seconds:.1f} s: it needs {MIN_VOICE:g} s at least")
                setattr(media, name, f"{name}/{filename}")
        found = h3.problems(video, media)
        if found:
            raise problem(422, "invalid_request", "; ".join(found))
        return video, media, files

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "models": list(h3.MODELS), "engine": "WanGP (github.com/deepbeepmeep/Wan2GP)"}

    @app.get("/v1/models", dependencies=[Depends(authorized)])
    def models() -> dict[str, Any]:
        return {
            "default": h3.DEFAULT_MODEL,
            "models": [
                {"id": name, "description": m.description, "steps": m.steps, "references": m.references,
                 "inputs": (["prompt", "references", "voice"] if m.references
                            else ["prompt", "start_image", "end_image", "soundtrack"])}
                for name, m in h3.MODELS.items()
            ],
            "resolutions": list(h3.RESOLUTIONS),
            "aspects": list(h3.ASPECTS),
            "durations": list(h3.DURATIONS),
            "languages": list(h3.LANGUAGES),
        }

    @app.get("/v1/loras", dependencies=[Depends(authorized)])
    def loras() -> dict[str, Any]:
        return {"loras": [{"name": n, "url": u, "strength": s, "trigger": t} for n, (u, s, t) in h3.LORAS.items()]}

    @app.post("/v1/prompts", dependencies=[Depends(authorized)])
    async def prompt(request: Request) -> dict[str, Any]:
        video, media, _ = await read(request)
        settings = h3.settings(video, media)
        return {"prompt": settings.pop("prompt"), "settings": settings}

    @app.post("/v1/videos", status_code=202, dependencies=[Depends(authorized)])
    async def create(request: Request) -> JSONResponse:
        video, media, files = await read(request)
        settings = h3.settings(video, media)
        width, height = map(int, settings["resolution"].split("x"))
        new = {
            "id": f"vid_{secrets.token_hex(10)}",
            "object": "video",
            "status": "queued",
            "created_at": time.time(),
            "progress": 0.0,
            "phase": "queued",
            "model": video.model,
            "seed": settings["seed"],
            "width": width,
            "height": height,
            "frames": settings["video_length"],
            "seconds": video.duration,
            "steps": settings["num_inference_steps"],
            "prompt": settings["prompt"],
            "request": video.model_dump(),
            "settings": settings,
        }
        jobs.put(new)
        try:
            handle = runner.start(new, files)
        except Exception as error:
            log.exception("Couldn't start %s", new["id"])
            jobs.delete(new["id"])
            raise problem(503, "start_failed", f"The GPU couldn't take the job: {error}") from None
        try:
            jobs.set_handle(new["id"], handle)
        except Exception as error:  # without its handle the call can't be stopped later: stop it now
            log.exception("Couldn't keep %s's handle", new["id"])
            jobs.cancel(new["id"])
            runner.stop(handle)
            jobs.delete(new["id"])
            raise problem(503, "start_failed", f"The job couldn't be kept: {error}") from None
        current = jobs.get(new["id"]) or new  # the GPU may have started it already
        return JSONResponse(public(current), status_code=202, headers={"Location": f"/v1/videos/{new['id']}"})

    def settled(found: dict) -> dict:
        """The job, failed if its call ended without saying how (a timeout, a lost container): the GPU writes the
        outcome itself otherwise."""
        handle = found["status"] not in DONE and jobs.handle(found["id"])
        why = handle and runner.ended(handle)
        if not why:
            return found
        current = jobs.get(found["id"]) or found  # the GPU may have written it just before its call ended
        if current["status"] in DONE:
            return current
        current = {**current, "status": "failed", "phase": "failed", "error": why, "finished_at": time.time()}
        jobs.put(current)
        return current

    @app.get("/v1/videos", dependencies=[Depends(authorized)])
    def list_jobs(limit: Annotated[int, Query(ge=1, le=100)] = 20) -> dict[str, Any]:
        latest = sorted(jobs.all(), key=lambda j: j.get("created_at", 0), reverse=True)[:limit]
        return {"data": [public(settled(j)) for j in latest]}

    @app.get("/v1/videos/{job_id}", dependencies=[Depends(authorized)])
    def get_job(job_id: str) -> dict[str, Any]:
        return public(settled(job(job_id)))

    @app.get("/v1/videos/{job_id}/content", dependencies=[Depends(authorized)])
    def content(job_id: str) -> FileResponse:
        found = job(job_id)
        if found["status"] != "succeeded":
            raise problem(409, "not_ready", f"The job is {found['status']}: the video is there once it has succeeded")
        path = videos.copy(job_id)  # a copy: the Volume's file isn't held open while it streams
        if path is None:
            raise problem(404, "video_not_found", "The job succeeded, but its MP4 is gone")
        return FileResponse(path, media_type="video/mp4", filename=f"{job_id}.mp4",
                            background=BackgroundTask(path.unlink, missing_ok=True))

    @app.post("/v1/videos/{job_id}/cancel", dependencies=[Depends(authorized)])
    def cancel(job_id: str) -> dict[str, Any]:
        found = job(job_id)
        if found["status"] in DONE:
            return public(found)
        jobs.cancel(job_id)
        handle = jobs.handle(job_id)
        if found["status"] == "queued" and handle:
            runner.stop(handle)  # it hasn't started: it never will
            found = {**found, "status": "cancelled", "phase": "cancelled", "finished_at": time.time()}
            jobs.put(found)
        return public(jobs.get(job_id) or found)

    @app.delete("/v1/videos/{job_id}", dependencies=[Depends(authorized)])
    def delete(job_id: str) -> dict[str, str]:
        found = job(job_id)
        if found["status"] not in DONE:
            jobs.cancel(job_id)
            handle = jobs.handle(job_id)
            if handle:
                runner.stop(handle)
        videos.delete(job_id)
        jobs.delete(job_id)
        return {"id": job_id, "status": "deleted"}

    return app
