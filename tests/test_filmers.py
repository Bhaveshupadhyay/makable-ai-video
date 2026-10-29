"""Who films the intro and the outro: HeyGen as well as Omni, and a clip brought in from a link."""

import http.server
import json
import threading
from pathlib import Path

import pytest

from shorts.filmers import FILMERS, _heygen_film, heygen_voices
from shorts.run import FILMED_INTRO, Run
from shorts.stages.bring_in import bring_in
from shorts.stages.film_intro import FilmIntro, FilmOutro

from .conftest import script

httpx = pytest.importorskip("httpx")


class HeyGen:
    """A stand-in for HeyGen's API: it takes the photo, films the clip on the second look, and serves it."""

    def __init__(self) -> None:
        self.asked: list[httpx.Request] = []
        self.looks = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        path = request.url.path
        if path == "/v3/assets":
            return httpx.Response(200, json={"data": {"asset_id": "photo-1"}})
        if path == "/v3/videos":
            return httpx.Response(200, json={"data": {"video_id": "video-1"}})
        if path == "/v3/videos/video-1":
            self.looks += 1
            done = {"status": "completed", "video_url": "https://files.example/clip.mp4"}
            return httpx.Response(200, json={"data": done if self.looks > 1 else {"status": "processing"}})
        if path == "/clip.mp4":
            return httpx.Response(200, content=b"mp4 bytes")
        if path == "/v3/voices":
            page = request.url.params.get("token")
            voices = [{"voice_id": f"v{page or 0}", "name": "Sam", "language": "English", "gender": "male"}]
            return httpx.Response(200, json={"data": voices, "has_more": page is None, "next_token": "1"})
        return httpx.Response(404, text="no such path")


def clients(heygen: HeyGen) -> dict:
    transport = httpx.MockTransport(heygen)
    return {
        "api": httpx.Client(base_url="https://api.heygen.com", headers={"x-api-key": "key"}, transport=transport),
        "files": httpx.Client(transport=transport),
    }


def with_face(run: Run, tmp_path: Path, **settings) -> Run:
    face = tmp_path / "face.jpg"
    face.write_bytes(b"jpeg")
    run.save_settings(run.settings().model_copy(update={"face": run.relative(face), **settings}))
    return run


def test_heygen_films_the_photo_saying_the_line_in_its_voice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shorts.filmers.time.sleep", lambda seconds: None)
    heygen, face = HeyGen(), tmp_path / "face.jpg"
    face.write_bytes(b"jpeg")
    settings = Run(tmp_path / "run").settings().model_copy(update={"filmer_voice": "v1"})

    _heygen_film("Hi there.", "A room.", face, tmp_path / "clip.mp4", settings, **clients(heygen))
    assert (tmp_path / "clip.mp4").read_bytes() == b"mp4 bytes"
    asked = json.loads(next(request for request in heygen.asked if request.url.path == "/v3/videos").content)
    assert (asked["type"], asked["script"], asked["voice_id"]) == ("image", "Hi there.", "v1")
    assert (asked["image"], asked["aspect_ratio"]) == ({"type": "asset_id", "asset_id": "photo-1"}, "9:16")
    download = next(request for request in heygen.asked if request.url.path == "/clip.mp4")
    assert "x-api-key" not in download.headers  # the key stays with HeyGen's API


def test_heygen_wants_a_voice(tmp_path: Path) -> None:
    settings = Run(tmp_path / "run").settings()
    with pytest.raises(ValueError, match="python -m shorts voices"):
        _heygen_film("Hi.", "", tmp_path / "face.jpg", tmp_path / "clip.mp4", settings, **clients(HeyGen()))


def test_heygen_voices_come_a_page_at_a_time() -> None:
    voices = heygen_voices("English", "male", api=clients(HeyGen())["api"])
    assert [voice["voice_id"] for voice in voices] == ["v0", "v1"]


def test_each_clip_is_filmed_by_its_filmer_and_again_when_that_changes(run: Run, tmp_path: Path) -> None:
    with_face(run, tmp_path, intro="heygen", outro="omni", filmer_voice="v1")
    written = script((0, 2))
    written.outro_line = "Try it."
    run.path("script.json").write_text(written.model_dump_json())
    intro = FilmIntro()
    assert (intro.filmer(run.settings()).name, FilmOutro().filmer(run.settings()).name) == ("heygen", "omni")
    assert intro.packages(run.settings()) == ["httpx"] and intro.by(run.settings()) == "film-intro (heygen)"

    planned = intro.plan(run)[FILMED_INTRO]
    run.save_settings(run.settings().model_copy(update={"filmer_voice": "v2"}))
    assert intro.plan(run)[FILMED_INTRO] != planned  # another voice: filmed again
    run.save_settings(run.settings().model_copy(update={"intro": "omni"}))
    assert intro.plan(run)[FILMED_INTRO] != planned
    assert set(FILMERS) == {"omni", "heygen"}


@pytest.fixture
def served(tmp_path: Path):
    """A local web server for tmp_path/www: a clip, and a page."""
    www = tmp_path / "www"
    www.mkdir()
    (www / "clip.mp4").write_bytes(b"mp4 bytes")
    (www / "page.html").write_text("<html>a video page</html>")

    class Files(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(www), **kwargs)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Files)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_a_clip_comes_in_from_its_link(run: Run, served: str) -> None:
    bring_in(run, "intro", [f"{served}/clip.mp4"])
    assert run.path(FILMED_INTRO).read_bytes() == b"mp4 bytes"
    assert run.settings().intro == "import"
    with pytest.raises(ValueError, match="is a web page"):
        bring_in(run, "outro", [f"{served}/page.html"])
