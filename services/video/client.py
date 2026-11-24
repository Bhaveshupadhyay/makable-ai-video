"""A client for the video API (services/video/api.py), and a command line on it.

    from services.video.client import VideoClient
    client = VideoClient(url, key)                    # or VideoClient() with VIDEO_API_URL and VIDEO_API_KEY set
    job = client.create({"prompt": "...", "dialogue": "...", "aspect": "9:16"}, start_image="still.png")
    job = client.wait(job["id"], on_progress=print)   # until it has succeeded, failed or been cancelled
    client.download(job["id"], "clip.mp4")

    python -m services.video.client models
    python -m services.video.client make "A fox reads the news" --dialogue "Good evening." --aspect 9:16 -o fox.mp4
    python -m services.video.client make "She smiles" --start-image still.png --soundtrack narration.wav -o shot.mp4
    python -m services.video.client status vid_…  |  cancel vid_…  |  list

It needs httpx.
"""

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

DONE = ("succeeded", "failed", "cancelled")


class VideoError(RuntimeError):
    pass


class VideoClient:
    def __init__(self, url: str | None = None, key: str | None = None, timeout: float = 120) -> None:
        url = url or os.environ.get("VIDEO_API_URL")
        key = key or os.environ.get("VIDEO_API_KEY")
        if not url or not key:
            raise VideoError("Set VIDEO_API_URL and VIDEO_API_KEY (or pass url and key)")
        self.http = httpx.Client(base_url=url.rstrip("/"), headers={"Authorization": f"Bearer {key}"},
                                 timeout=timeout, follow_redirects=True)

    def _call(self, method: str, path: str, **kwargs) -> httpx.Response:
        answer = self.http.request(method, path, **kwargs)
        if answer.status_code >= 400:
            try:
                detail = answer.json()["detail"]
                message = f"{detail['status']}: {detail['message']}" if isinstance(detail, dict) else str(detail)
            except (ValueError, KeyError, TypeError):
                message = answer.text[:500]
            raise VideoError(f"{method} {path} -> {answer.status_code} {message}")
        return answer

    def models(self) -> dict[str, Any]:
        return self._call("GET", "/v1/models").json()

    def loras(self) -> dict[str, Any]:
        return self._call("GET", "/v1/loras").json()

    @staticmethod
    def _files(start_image=None, end_image=None, references=(), voice=None, soundtrack=None) -> list:
        files = []
        for name, path in (("start_image", start_image), ("end_image", end_image), ("voice", voice),
                           ("soundtrack", soundtrack)):
            if path:
                files.append((name, (Path(path).name, Path(path).read_bytes())))
        for path in references or ():
            files.append(("references", (Path(path).name, Path(path).read_bytes())))
        return files

    def _send(self, path: str, request: dict, **media) -> dict[str, Any]:
        files = self._files(**media)
        if files:
            return self._call("POST", path, data={"request": json.dumps(request)}, files=files).json()
        return self._call("POST", path, json=request).json()

    def prompt(self, request: dict, **media) -> dict[str, Any]:
        """The H3 prompt and settings `request` would run with, without running it."""
        return self._send("/v1/prompts", request, **media)

    def create(self, request: dict, **media) -> dict[str, Any]:
        """Starts a video. media: start_image, end_image, references (paths), voice, soundtrack."""
        return self._send("/v1/videos", request, **media)

    def get(self, job_id: str) -> dict[str, Any]:
        return self._call("GET", f"/v1/videos/{job_id}").json()

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._call("GET", "/v1/videos", params={"limit": limit}).json()["data"]

    def cancel(self, job_id: str) -> dict[str, Any]:
        return self._call("POST", f"/v1/videos/{job_id}/cancel").json()

    def delete(self, job_id: str) -> dict[str, Any]:
        return self._call("DELETE", f"/v1/videos/{job_id}").json()

    def wait(self, job_id: str, every: float = 5, timeout: float = 3 * 3600,
             on_progress: Callable[[dict], None] | None = None) -> dict[str, Any]:
        """Waits until the job is done, and returns it.

        Raises:
            VideoError: it failed or was cancelled, or wasn't done after `timeout` seconds.
        """
        deadline = time.time() + timeout
        while True:
            job = self.get(job_id)
            if on_progress:
                on_progress(job)
            if job["status"] == "succeeded":
                return job
            if job["status"] in DONE:
                raise VideoError(f"{job_id} {job['status']}: {job.get('error') or ''}".strip())
            if time.time() > deadline:
                raise VideoError(f"{job_id} wasn't done after {timeout / 60:g} minutes")
            time.sleep(every)

    def download(self, job_id: str, out: str | Path) -> Path:
        out = Path(out)
        with self.http.stream("GET", f"/v1/videos/{job_id}/content") as answer:
            if answer.status_code >= 400:
                answer.read()
                raise VideoError(f"GET content -> {answer.status_code} {answer.text[:300]}")
            with out.open("wb") as file:
                for chunk in answer.iter_bytes():
                    file.write(chunk)
        return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m services.video.client", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("models")
    commands.add_parser("loras")
    commands.add_parser("list")
    for name in ("status", "cancel", "delete", "download"):
        command = commands.add_parser(name)
        command.add_argument("id")
        if name == "download":
            command.add_argument("-o", "--out", required=True)
    for name in ("make", "prompt"):
        make = commands.add_parser(name)
        make.add_argument("prompt")
        make.add_argument("--dialogue", default="")
        make.add_argument("--language", default="English")
        make.add_argument("--sound", default="")
        make.add_argument("--music", default="")
        make.add_argument("--model", default=None)
        make.add_argument("--resolution", default="480p")
        make.add_argument("--aspect", default="auto")
        make.add_argument("--duration", type=float, default=5)
        make.add_argument("--steps", type=int, default=None)
        make.add_argument("--seed", type=int, default=None)
        make.add_argument("--lora", action="append", default=[], help="name[:strength], or a Hugging Face link")
        make.add_argument("--start-image")
        make.add_argument("--end-image")
        make.add_argument("--reference", action="append", default=[])
        make.add_argument("--reference-name", action="append", default=[])
        make.add_argument("--voice")
        make.add_argument("--soundtrack")
        make.add_argument("-o", "--out", help="where to save the MP4 (make: waits for it)")
    args = parser.parse_args(argv)
    client = VideoClient()
    try:
        if args.command in ("make", "prompt"):
            loras = []
            for lora in args.lora:
                name, _, strength = lora.rpartition(":") if lora.count(":") > (1 if "://" in lora else 0) else (lora, "", "")
                loras.append({"name": name, "strength": float(strength)} if strength else {"name": name or lora})
            request = {k: v for k, v in {
                "prompt": args.prompt, "dialogue": args.dialogue, "language": args.language, "sound": args.sound,
                "music": args.music, "model": args.model, "resolution": args.resolution, "aspect": args.aspect,
                "duration": args.duration, "steps": args.steps, "seed": args.seed, "loras": loras,
                "reference_names": args.reference_name,
            }.items() if v not in (None, [], "")}
            media = {"start_image": args.start_image, "end_image": args.end_image, "references": args.reference,
                     "voice": args.voice, "soundtrack": args.soundtrack}
            if args.command == "prompt":
                print(json.dumps(client.prompt(request, **media), indent=2, ensure_ascii=False))
                return 0
            job = client.create(request, **media)
            print(f"{job['id']}: {job['width']}x{job['height']}, {job['frames']} frames, {job['steps']} steps, "
                  f"seed {job['seed']}", flush=True)
            if not args.out:
                return 0
            shown = {"line": ""}

            def show(current: dict) -> None:
                line = f"  {current['status']} {current.get('progress', 0) * 100:3.0f}% {current.get('phase', '')}"
                if line != shown["line"]:
                    shown["line"] = line
                    print(line, flush=True)

            job = client.wait(job["id"], on_progress=show)
            print(f"Saved {client.download(job['id'], args.out)} ({job.get('timings', {})})")
        elif args.command in ("models", "loras", "list"):
            result = {"models": client.models, "loras": client.loras, "list": client.list}[args.command]()
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.command == "download":
            print(client.download(args.id, args.out))
        else:
            result = {"status": client.get, "cancel": client.cancel, "delete": client.delete}[args.command](args.id)
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except VideoError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
