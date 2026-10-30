"""Your own things, kept for every video: your files, the sites you've signed in to, and a new run taking them."""

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from shorts import browse as recorder
from shorts.__main__ import new
from shorts.home import home, keep, mine, signed_in_sites, site, site_profile
from shorts.orchestrator import PACKAGE_ROOT
from shorts.run import Run
from shorts.signin import forget, recording_profile


@pytest.fixture
def kept(shorts_home: Path) -> Path:
    return shorts_home


def a_file(path: Path, data: bytes = b"data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_your_files_are_kept_one_of_each(tmp_path: Path, kept: Path) -> None:
    assert home() == kept and mine() == {}
    keep("face", a_file(tmp_path / "old.JPG"))
    keep("face", a_file(tmp_path / "Downloads" / "me.png", b"png"))  # in place of the one before
    keep("music", a_file(tmp_path / "song.mp3"))
    assert mine() == {"face": kept / "me" / "face.png", "music": kept / "me" / "music.mp3"}
    assert (kept / "me" / "face.png").read_bytes() == b"png"
    keep("music", None)
    assert mine() == {"face": kept / "me" / "face.png"}
    keep("face", kept / "me" / "face.png")  # the one that's kept: it stays
    assert (kept / "me" / "face.png").read_bytes() == b"png"
    with pytest.raises(ValueError, match="has no extension"):
        keep("face", a_file(tmp_path / "photo"))
    assert mine() == {"face": kept / "me" / "face.png"}


def test_a_site_is_named_by_its_host() -> None:
    assert site("https://Makable.tech/new?x=1") == "makable.tech"
    assert site("app.example.com/dashboard") == "app.example.com"
    assert site("http://localhost:3000/") == "localhost_3000"
    assert site("https://www.example.com/dashboard") == site("example.com") == "example.com"
    with pytest.raises(ValueError, match="isn't a web address"):
        site("https://")


def test_recording_signed_in_needs_someone_to_have_signed_in(kept: Path) -> None:
    with pytest.raises(ValueError, match="sign in once with `python -m shorts signin --url https://app.example.com/x`"):
        recording_profile("https://app.example.com/x")
    site_profile("https://app.example.com").mkdir(parents=True)  # as `signin` leaves it
    assert recording_profile("https://app.example.com/x") == kept / "sites" / "app.example.com"
    assert signed_in_sites() == ["app.example.com"]
    assert forget("https://app.example.com") and not forget("https://app.example.com")
    assert signed_in_sites() == []


def options(**given) -> argparse.Namespace:
    return argparse.Namespace(footage_items=None, narrator_option=None, respellings=None, **given)


def test_a_new_run_keeps_a_copy_of_your_files_unless_its_given_others(tmp_path: Path, kept: Path) -> None:
    keep("face", a_file(tmp_path / "me.png", b"me"))
    keep("music", a_file(tmp_path / "song.mp3"))
    run = Run(tmp_path / "runs" / "first")
    new(run, options(music=str(a_file(tmp_path / "other.mp3"))))
    settings = run.settings()
    assert (settings.face, run.resolve(settings.music)) == ("me/face.png", (tmp_path / "other.mp3").resolve())
    assert run.path("me/face.png").read_bytes() == b"me"

    keep("face", a_file(tmp_path / "newer.jpg", b"newer"))  # later: the run keeps its own, as it was
    new(run, options(music=""))  # a run that's there keeps what it has, but for what's given
    assert (run.settings().face, run.settings().music) == ("me/face.png", None)
    assert run.path("me/face.png").read_bytes() == b"me"


def test_a_run_made_by_a_recording_first_takes_your_files_too(tmp_path: Path, kept: Path) -> None:
    keep("face", a_file(tmp_path / "me.png", b"me"))
    run = Run(tmp_path / "runs" / "first")
    settings = run.settings()  # as bringing a recording in does, before `new`
    settings.footage["demo"] = "recordings/demo-tight.mp4"
    run.save_settings(settings)
    assert run.settings().face == "me/face.png" and run.path("me/face.png").read_bytes() == b"me"


def test_me_keeps_and_shows_your_files(tmp_path: Path, kept: Path) -> None:
    def me(*args: str) -> str:
        environment = {**os.environ, "PYTHONPATH": str(PACKAGE_ROOT), "SHORTS_HOME": str(kept)}
        command = [sys.executable, "-m", "shorts", "me", *args]
        return subprocess.run(command, capture_output=True, text=True, env=environment, check=True).stdout

    shown = me("--face", str(a_file(tmp_path / "me.png")))
    assert f"face       {kept / 'me' / 'face.png'}" in shown and "music      (none)" in shown
    a_file(kept / "products" / "makable.md")
    assert "products   makable" in me()
    assert "face       (none)" in me("--face", "")
    with pytest.raises(subprocess.CalledProcessError) as refused:
        me("--face", str(a_file(tmp_path / "photo")))
    assert "has no extension" in refused.value.stderr


def test_chrome_quits_by_itself_and_lets_go_of_the_profile(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "SingletonLock").symlink_to("host-1234")  # as Chrome holds it

    async def close() -> None:  # Chrome quits a moment later
        asyncio.get_running_loop().call_later(0.3, (profile / "SingletonLock").unlink)

    session = SimpleNamespace(
        browser_profile=SimpleNamespace(user_data_dir=str(profile)),
        cdp_client=SimpleNamespace(send=SimpleNamespace(Browser=SimpleNamespace(close=close))),
    )

    async def quit() -> float:
        start = asyncio.get_running_loop().time()
        await recorder._quit(session)
        return asyncio.get_running_loop().time() - start

    assert 0.25 <= asyncio.run(quit()) <= 1.0
    assert not os.path.lexists(profile / "SingletonLock")


def test_a_sign_in_whose_chrome_never_opens_leaves_no_profile(kept: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from shorts import signin

    monkeypatch.setattr(signin, "_chrome", lambda: "/usr/bin/false")  # a Chrome that quits at once
    with pytest.raises(RuntimeError, match="Chrome didn't open"):
        signin.sign_in("https://app.example.com")
    assert not site_profile("https://app.example.com").exists() and signed_in_sites() == []

    site_profile("https://app.example.com").mkdir(parents=True)  # signed in before: that's kept
    with pytest.raises(RuntimeError, match="Chrome didn't open"):
        signin.sign_in("https://app.example.com")
    assert signed_in_sites() == ["app.example.com"]
