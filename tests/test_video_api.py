"""The video API (services/video) and its client, talking to each other in this process, with a stand-in for the GPU:
the same requests a client sends to Modal. And the H3 prompts and WanGP settings requests become."""

import shutil
import subprocess
import time
from pathlib import Path

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")
pytest.importorskip("multipart")
PIL = pytest.importorskip("PIL")

from fastapi.testclient import TestClient  # noqa: E402

from services.video import h3  # noqa: E402
from services.video.api import create_app  # noqa: E402
from services.video.client import VideoClient, VideoError  # noqa: E402

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffprobe") is None, reason="the video API probes audio with ffprobe")
KEY = "a-key"


class MemoryJobs:
    def __init__(self) -> None:
        self.jobs, self.flags, self.handles = {}, set(), {}

    def get(self, job_id):
        return self.jobs.get(job_id)

    def put(self, job):
        self.jobs[job["id"]] = dict(job)

    def delete(self, job_id):
        self.jobs.pop(job_id, None)

    def all(self):
        return list(self.jobs.values())

    def cancel(self, job_id):
        self.flags.add(job_id)

    def set_handle(self, job_id, handle):
        if getattr(self, "broken", False):
            raise OSError("the Dict is down")
        self.handles[job_id] = handle

    def handle(self, job_id):
        return self.handles.get(job_id)


class FakeGpu:
    """Runs a job at once (unless `hold`), writing a tiny MP4 where the Volume would have it."""

    def __init__(self, jobs: MemoryJobs, folder: Path) -> None:
        self.jobs, self.folder, self.started, self.stopped, self.hold = jobs, folder, [], [], False
        self.why = None  # what `ended` says

    def start(self, job, files):
        self.started.append((job, files))
        if not self.hold:
            (self.folder / f"{job['id']}.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
            self.jobs.put({**self.jobs.get(job["id"]), "status": "succeeded", "progress": 1.0,
                           "finished_at": time.time()})
        return f"call-{job['id']}"

    def stop(self, handle):
        self.stopped.append(handle)

    def ended(self, handle):
        return self.why


class FolderVideos:
    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def copy(self, job_id):
        path = self.folder / f"{job_id}.mp4"
        if not path.exists():
            return None
        copied = self.folder / f"copy-{job_id}.mp4"
        shutil.copyfile(path, copied)
        return copied

    def delete(self, job_id):
        (self.folder / f"{job_id}.mp4").unlink(missing_ok=True)


@pytest.fixture
def world(tmp_path: Path):
    jobs = MemoryJobs()
    gpu = FakeGpu(jobs, tmp_path)
    server = TestClient(create_app(jobs, gpu, FolderVideos(tmp_path), key=KEY), base_url="http://video")
    client = VideoClient("http://video", KEY)
    client.http = server  # TestClient is an httpx.Client
    server.headers["Authorization"] = f"Bearer {KEY}"
    return jobs, gpu, server, client


def png(path: Path, size=(300, 600)) -> Path:
    from PIL import Image

    Image.new("RGB", size, "teal").save(path)
    return path


def wav(path: Path, seconds: float) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=f=300:d={seconds}", str(path)],
                   check=True)
    return path


def test_health_needs_no_key_and_everything_else_does(world) -> None:
    _, _, server, _ = world
    assert TestClient(server.app).get("/health").json()["models"] == list(h3.MODELS)
    bare = TestClient(server.app)
    assert bare.get("/v1/models").status_code == 401
    assert bare.get("/v1/models", headers={"x-api-key": KEY}).status_code == 200
    assert bare.get("/v1/models", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_text_to_video_runs_and_downloads(world, tmp_path: Path) -> None:
    jobs, gpu, _, client = world
    job = client.create({"prompt": "A fox reads the news", "dialogue": "Good evening.", "aspect": "9:16"})
    assert job["status"] in ("queued", "succeeded") and job["id"].startswith("vid_")
    assert (job["width"], job["height"]) == (480, 832) and job["frames"] == 124 and job["steps"] == 8
    assert "<d>[English] Good evening.</d>" in job["prompt"] and "settings" not in job
    sent, files = gpu.started[0]
    assert sent["settings"]["model_type"] == "minimax_h3_fl2va_pruned_pdd"
    assert sent["settings"]["activated_loras"] == [] and files == {}
    done = client.wait(job["id"], every=0)
    assert done["status"] == "succeeded"
    out = client.download(job["id"], tmp_path / "out.mp4")
    assert out.read_bytes().startswith(b"\x00\x00\x00\x18ftyp")
    assert not (tmp_path / f"copy-{job['id']}.mp4").exists()  # the copy it streamed from is gone
    assert [j["id"] for j in client.list()] == [job["id"]]
    assert client.delete(job["id"])["status"] == "deleted" and jobs.get(job["id"]) is None


def test_a_bad_request_never_reaches_the_gpu(world) -> None:
    _, gpu, _, client = world
    for request, says in (
        ({"prompt": ""}, "Write a prompt"),
        ({"prompt": "x", "duration": 7}, "duration"),
        ({"prompt": "x", "model": "nope"}, "model"),
        ({"prompt": "x", "loras": [{"name": "https://example.com/x.safetensors"}]}, "loras"),
    ):
        with pytest.raises(VideoError, match=says):
            client.create(request)
    assert gpu.started == []


def test_start_image_sets_the_aspect_and_the_anchor(world, tmp_path: Path) -> None:
    _, gpu, _, client = world
    job = client.create({"prompt": "She smiles", "resolution": "360p"}, start_image=png(tmp_path / "still.png"))
    assert job["height"] > job["width"]  # auto: the still's 1:2
    settings = gpu.started[0][0]["settings"]
    assert settings["image_prompt_type"] == "S" and settings["image_start"].endswith("still.png")
    assert "<Picture 1>" in job["prompt"] and "Continue directly from <Picture 1>" in job["prompt"]
    assert gpu.started[0][1]["start_image"][0] == "still.png"


@needs_ffmpeg
def test_references_and_voice_need_a_reference_model(world, tmp_path: Path) -> None:
    _, gpu, _, client = world
    face, voice = png(tmp_path / "face.png", (512, 512)), wav(tmp_path / "voice.wav", 3)
    with pytest.raises(VideoError, match="reference model"):
        client.create({"prompt": "x"}, references=[face])
    job = client.create({"prompt": "waves", "model": "ref-pdd", "dialogue": "Hi", "reference_names": ["the girl"]},
                        references=[face], voice=voice)
    settings = gpu.started[-1][0]["settings"]
    assert settings["video_prompt_type"] == "I" and settings["audio_prompt_type"] == "A"
    assert "<Subject 1> is the girl in <Picture 1>" in job["prompt"] and "<Audio 1>" in job["prompt"]
    with pytest.raises(VideoError, match="at least"):
        client.create({"prompt": "x", "model": "ref-pdd"}, references=[face], voice=wav(tmp_path / "s.wav", 1))


@needs_ffmpeg
def test_a_soundtrack_drives_fl2va(world, tmp_path: Path) -> None:
    _, gpu, _, client = world
    client.create({"prompt": "He explains"}, soundtrack=wav(tmp_path / "narration.wav", 4))
    settings = gpu.started[0][0]["settings"]
    assert settings["audio_prompt_type"] == "A" and settings["audio_guide"].startswith("soundtrack/")


def test_cancel_stops_a_queued_job(world) -> None:
    _, gpu, _, client = world
    gpu.hold = True
    job = client.create({"prompt": "slow"})
    assert client.cancel(job["id"])["status"] == "cancelled"
    assert gpu.stopped == [f"call-{job['id']}"]
    with pytest.raises(VideoError, match="409"):
        client.download(job["id"], "/dev/null")


def test_prompts_show_what_would_run(world) -> None:
    _, gpu, _, client = world
    shown = client.prompt({"prompt": "A city", "loras": [{"name": "camera-motion"}], "seed": 7})
    assert shown["prompt"].startswith("integrated_multimodal_description: [Shot 1] camera motion, A 5-second")
    assert shown["settings"]["seed"] == 7 and shown["settings"]["loras_multipliers"] == "0.9"
    assert gpu.started == []


def test_a_structured_prompt_is_kept() -> None:
    prompt = "integrated_multimodal_description: [Shot 1] A cat.\noverall_soundscape: Purring."
    request = h3.VideoRequest(prompt=prompt)
    assert h3.build_prompt(request, h3.Media()) == prompt


def test_a_call_that_ends_without_an_outcome_fails(world) -> None:
    _, gpu, _, client = world
    gpu.hold = True
    job = client.create({"prompt": "slow"})
    assert client.get(job["id"])["status"] == "queued"
    gpu.why = "It ran past the GPU's limit of 60 minutes"
    failed = client.get(job["id"])
    assert failed["status"] == "failed" and failed["error"] == gpu.why
    assert client.list()[0]["status"] == "failed"


def test_a_job_whose_handle_cant_be_kept_is_stopped(world) -> None:
    jobs, gpu, _, client = world
    gpu.hold, jobs.broken = True, True
    with pytest.raises(VideoError, match="503"):
        client.create({"prompt": "x"})
    assert len(gpu.stopped) == 1 and jobs.all() == []


def test_reference_names_keep_their_places() -> None:
    request = h3.VideoRequest(prompt="x", model="ref-pdd", reference_names=["", "the red car"])
    prompt = h3.build_prompt(request, h3.Media(references=["a.png", "b.png"]))
    assert "<Subject 1> is the main subject in <Picture 1>" in prompt
    assert "<Subject 2> is the red car in <Picture 2>" in prompt
