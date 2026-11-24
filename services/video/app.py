"""The video API on Modal: `api.create_app` in a small CPU container, MiniMax H3 (through WanGP) on an H100.

A video takes minutes, so the API runs jobs: POST /v1/videos spawns one on the GPU and answers at once, and the GPU's
container writes the job's progress into a Dict (makable-video-jobs) and its MP4 into a Volume (makable-videos),
where the API reads them. There's at most one GPU container: jobs that come while it works wait their turn, queued.
It stops `IDLE` seconds after its last job, so it costs nothing between videos. Models download (~60 GB) into a
Volume (makable-video-models) the first time each is used, so later containers start without downloading.

Set up once (`pip install modal`, then `modal setup` to sign in):

    export VIDEO_API_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')  # the client's key too
    modal secret create makable-video VIDEO_API_KEY="$VIDEO_API_KEY"
    modal deploy -m services.video.app        # from the repo's root; prints the API's URL

`modal serve -m services.video.app` serves your working copy at a temporary URL while you work on it.
"""

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import modal

GPU = "H100"  # 80 GB: H3's INT8 transformer, text encoder and VAEs all fit; "A100-80GB" is slower and cheaper
IDLE = 300  # seconds the GPU container waits for the next job before it stops
TIMEOUT = 3600  # seconds a job may take: a 720p, 15 s clip, or the first download of a model
WANGP_COMMIT = "b8b18f8114e432eea8f3d7e853a51dd91fa99571"  # WanGP, 1 Oct 2026: the version the Kaggle notebook pins
WANGP = "/opt/Wan2GP"
MODELS = "/models"
VIDEOS = "/videos"
WANGP_CONFIG = {
    "transformer_quantization": "int8",  # H3's INT8 ConvRot checkpoint (21 GB); "bf16" is 42 GB
    "text_encoder_quantization": "int8",  # Qwen3-VL-32B in Quanto INT8
    "attention_mode": "sdpa",
    "profile": 3,  # mmgp's LowRAM_HighVRAM: whole models in VRAM, nothing streamed per step
}
CLI_ARGS = ["--attention", "sdpa", "--profile", "3"]

app = modal.App("makable-video")
models = modal.Volume.from_name("makable-video-models", create_if_missing=True)
videos = modal.Volume.from_name("makable-videos", create_if_missing=True)
jobs = modal.Dict.from_name("makable-video-jobs", create_if_missing=True)

# WanGP's requirements, but onnxruntime's nightly (gone from PyPI: the stable one instead) and insightface (it builds
# from source on Linux; H3 doesn't use it). torch stays the one installed first.
REQUIREMENTS = (
    f"grep -v -E 'onnxruntime|extra-index-url|insightface|^\\s*#' {WANGP}/requirements.txt > /tmp/requirements.txt"
)
gpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg", "build-essential", "libgl1", "libglib2.0-0", "portaudio19-dev", "libsndfile1",
                 "espeak-ng")
    .uv_pip_install("torch==2.7.1", "torchvision==0.22.1", "torchaudio==2.7.1",
                    index_url="https://download.pytorch.org/whl/cu128")
    .run_commands(
        f"git init -q {WANGP} && git -C {WANGP} remote add origin https://github.com/DeepBeepMeep/Wan2GP.git",
        f"git -C {WANGP} fetch -q --depth 1 origin {WANGP_COMMIT} && git -C {WANGP} checkout -q FETCH_HEAD",
        REQUIREMENTS,
        "printf 'torch==2.7.1\\ntorchvision==0.22.1\\ntorchaudio==2.7.1\\n' > /tmp/constraints.txt",
        "uv pip install --system --index-strategy unsafe-best-match "
        "--extra-index-url https://download.pytorch.org/whl/cu128 "
        "-r /tmp/requirements.txt -c /tmp/constraints.txt onnxruntime-gpu==1.22.0",
    )
    .env({"HF_HOME": f"{MODELS}/hf", "HF_XET_HIGH_PERFORMANCE": "1", "TOKENIZERS_PARALLELISM": "false",
          "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"})
    .add_local_python_source("services")
)
web_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .uv_pip_install("fastapi[standard]", "python-multipart", "pillow")
    .add_local_python_source("services")
)


class DictJobs:
    """api.Jobs in the Dict: each job at its id, and a cancel flag beside it."""

    def get(self, job_id: str) -> dict | None:
        return jobs.get(job_id) if job_id.startswith("vid_") else None

    def put(self, job: dict) -> None:
        jobs[job["id"]] = job

    def delete(self, job_id: str) -> None:
        for key in (job_id, f"cancel:{job_id}", f"handle:{job_id}"):
            jobs.pop(key, None)

    def all(self):
        return [value for key, value in jobs.items() if key.startswith("vid_")]

    def cancel(self, job_id: str) -> None:
        jobs[f"cancel:{job_id}"] = True

    def set_handle(self, job_id: str, handle: str) -> None:
        jobs[f"handle:{job_id}"] = handle

    def handle(self, job_id: str) -> str | None:
        return jobs.get(f"handle:{job_id}")

    def cancelled(self, job_id: str) -> bool:
        return bool(jobs.get(f"cancel:{job_id}", False))

    def update(self, job_id: str, **fields) -> dict:
        job = {**(jobs.get(job_id) or {"id": job_id}), **fields}
        jobs[job_id] = job
        return job


@app.cls(
    image=gpu_image,
    gpu=GPU,
    cpu=8,
    memory=65536,
    volumes={MODELS: models, VIDEOS: videos},
    scaledown_window=IDLE,
    max_containers=1,
    timeout=TIMEOUT,
)
class H3Video:
    @modal.enter()
    def load(self) -> None:
        from services.video.engine import Engine

        self.engine = Engine(Path(WANGP), Path(MODELS), Path("/tmp/h3-outputs"), WANGP_CONFIG, CLI_ARGS)

    @modal.method()
    def run(self, job_id: str, request: dict, seed: int, files: dict) -> None:
        from services.video import h3
        from services.video.engine import Cancelled, write_media

        store = DictJobs()
        if store.cancelled(job_id) or store.get(job_id) is None:
            store.update(job_id, status="cancelled", phase="cancelled", finished_at=time.time())
            return
        store.update(job_id, status="running", phase="starting", started_at=time.time())
        last = {"at": 0.0}

        def progress(fraction: float, phase: str) -> None:
            now = time.time()
            if now - last["at"] >= 2 or fraction >= 1:
                last["at"] = now
                store.update(job_id, progress=round(fraction, 3), phase=phase)

        try:
            with tempfile.TemporaryDirectory() as work:
                media = write_media(Path(work), files)
                settings = h3.settings(h3.VideoRequest.model_validate(request), media, seed)
                path, timings = self.engine.generate(settings, progress, lambda: store.cancelled(job_id))
                out = Path(VIDEOS) / f"{job_id}.mp4"
                shutil.copyfile(path, out)
                path.unlink(missing_ok=True)
            videos.commit()
            # What the MP4 really is: WanGP rounds some lengths up (3 s, 73 frames, came out as 107 frames)
            probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-count_packets",
                                    "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(out)],
                                   capture_output=True, text=True)
            frames = int(probe.stdout.strip() or 0) or None
            store.update(job_id, status="succeeded", phase="done", progress=1.0, finished_at=time.time(),
                         timings={k: round(v, 1) for k, v in timings.items()}, bytes=out.stat().st_size,
                         frames=frames, seconds=round(frames / 24, 2) if frames else None)
        except Cancelled:
            store.update(job_id, status="cancelled", phase="cancelled", finished_at=time.time())
        except Exception as error:
            store.update(job_id, status="failed", phase="failed", error=str(error)[:2000], finished_at=time.time())
            raise
        finally:
            models.commit()  # what it downloaded (a model the first time, a LoRA), for the containers after it


class GpuRunner:
    """api.Runner: a job, spawned on H3Video."""

    def start(self, job: dict, files: dict) -> str:
        call = H3Video().run.spawn(job["id"], job["request"], job["seed"], files)
        return call.object_id

    def stop(self, handle: str) -> None:
        modal.FunctionCall.from_id(handle).cancel()

    def ended(self, handle: str) -> str | None:
        from modal.exception import FunctionTimeoutError, OutputExpiredError

        try:
            modal.FunctionCall.from_id(handle).get(timeout=0)
        except FunctionTimeoutError:  # modal.exception.TimeoutError's: the call hit TIMEOUT
            return f"It ran past the GPU's limit of {TIMEOUT // 60} minutes"
        except OutputExpiredError:
            return "Its GPU call ended long ago without saying how"
        except TimeoutError:  # Python's own, which get(timeout=0) raises while the call is queued or running
            return None
        except Exception as error:
            return f"Its GPU call failed: {error}"[:2000]
        return "Its GPU call ended without saying how"  # it returned, but never wrote the job's outcome


class VolumeVideos:
    """api.Videos: the MP4s in the Volume. A reload fails while this container has one of its files open, so reading
    and deleting happen one at a time, and downloads stream from a copy, not from the Volume."""

    def __init__(self) -> None:
        import threading

        self.lock = threading.Lock()

    def copy(self, job_id: str) -> Path | None:
        with self.lock:
            videos.reload()  # the GPU container committed it
            path = Path(VIDEOS) / f"{job_id}.mp4"
            if not path.exists():
                return None
            handle, name = tempfile.mkstemp(suffix=".mp4")
            os.close(handle)
            try:
                shutil.copyfile(path, name)
            except BaseException:  # a part-written copy: the response never gets it to clean up
                Path(name).unlink(missing_ok=True)
                raise
            return Path(name)  # the response deletes it once sent

    def delete(self, job_id: str) -> None:
        with self.lock:
            videos.reload()  # it may have been committed after this container last looked
            path = Path(VIDEOS) / f"{job_id}.mp4"
            if path.exists():
                path.unlink()
                videos.commit()


@app.function(
    image=web_image,
    volumes={VIDEOS: videos},
    secrets=[modal.Secret.from_name("makable-video")],
    max_containers=1,
    scaledown_window=300,
)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def web():
    from services.video.api import create_app

    return create_app(DictJobs(), GpuRunner(), VolumeVideos(), key=os.environ["VIDEO_API_KEY"])
