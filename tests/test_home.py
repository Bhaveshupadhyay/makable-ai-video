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
from shorts.home import chosen, home, keep, mine, products, project, runs, signed_in_sites, site, site_profile
from shorts.orchestrator import PACKAGE_ROOT
from shorts.run import Run, Settings
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
    assert site("http://[::1]:8080/") == "__1_8080" and site("https://user:pw@app.example.com") == "app.example.com"
    for wrong in ("https://..", "https://www..", "https://www...", "https://a..b", "https://ex_ample.com", "x:abc"):
        with pytest.raises(ValueError, match="isn't a web address"):
            site(wrong)
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
    keep("face", a_file(kept.parent / "me.png"))
    with pytest.raises(ValueError):  # not a site: never a folder outside sites/ (`..` was SHORTS_HOME itself)
        forget("https://www...")
    assert mine() == {"face": kept / "me" / "face.png"}


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


def test_a_copy_that_fails_leaves_the_runs_own(tmp_path: Path, kept: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil

    keep("face", a_file(tmp_path / "me.png", b"first"))
    run = Run(tmp_path / "runs" / "first")
    run.save_settings(run.settings())
    keep("face", a_file(tmp_path / "newer.png", b"newer"))

    def half(source, out) -> None:  # the disk fills up halfway
        Path(out).write_bytes(b"ne")
        raise OSError("No space left on device")

    monkeypatch.setattr(shutil, "copyfile", half)
    with pytest.raises(OSError):
        run.save_settings(run.settings().model_copy(update={"face": str(kept / "me" / "face.png")}))
    assert run.path("me/face.png").read_bytes() == b"first" and run.settings().face == "me/face.png"


def test_a_run_made_by_a_recording_first_takes_your_files_too(tmp_path: Path, kept: Path) -> None:
    keep("face", a_file(tmp_path / "me.png", b"me"))
    run = Run(tmp_path / "runs" / "first")
    settings = run.settings()  # as bringing a recording in does, before `new`
    settings.footage["demo"] = "recordings/demo-tight.mp4"
    run.save_settings(settings)
    assert run.settings().face == "me/face.png" and run.path("me/face.png").read_bytes() == b"me"


def shorts(*args: str, cwd: Path, home: Path) -> str:
    """The command line, run in `cwd`."""
    environment = {**os.environ, "PYTHONPATH": str(PACKAGE_ROOT), "SHORTS_HOME": str(home)}
    command = [sys.executable, "-m", "shorts", *args]
    return subprocess.run(command, capture_output=True, text=True, env=environment, cwd=cwd, check=True).stdout


def test_me_keeps_and_shows_your_files(tmp_path: Path, kept: Path) -> None:
    def me(*args: str) -> str:
        return shorts("me", *args, cwd=tmp_path, home=kept)

    shown = me("--face", str(a_file(tmp_path / "me.png")))
    assert f"face       {kept / 'me' / 'face.png'}" in shown and "music      (none)" in shown
    assert "products   (none)" in shown and f"runs       {tmp_path / '.makable-shorts' / 'runs'}" in shown
    a_file(kept / "products" / "makable.md")
    assert f"products   makable  {kept / 'products' / 'makable.md'}" in me()
    assert "face       (none)" in me("--face", "")
    with pytest.raises(subprocess.CalledProcessError) as refused:
        me("--face", str(a_file(tmp_path / "photo")))
    assert "has no extension" in refused.value.stderr


def test_me_keeps_who_films_you_and_who_speaks_and_says_the_keys_they_need(
    tmp_path: Path, kept: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def me(*args: str) -> str:
        return shorts("me", *args, cwd=tmp_path, home=kept)

    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)  # no Google Cloud sign-in here
    monkeypatch.setenv("CLOUDSDK_CONFIG", str(tmp_path / "gcloud"))

    shown = me()
    assert "filmer     (not chosen" in shown and "narrator   (not chosen" in shown
    assert "keys       (they depend on who films you and who speaks" in shown
    shown = me("--filmer", "omni", "--narrator", "elevenlabs")
    assert "filmer     Gemini Omni, in your Google Cloud project" in shown and "narrator   ElevenLabs" in shown
    assert "GOOGLE_CLOUD_PROJECT" in shown and "ELEVENLABS_API_KEY" in shown and "HEYGEN_API_KEY" not in shown
    assert "google     not signed in: gcloud auth application-default login" in shown
    a_file(tmp_path / "gcloud" / "application_default_credentials.json", b"{}")  # gcloud's, once you've signed in
    assert "google     signed in" in me()
    assert chosen() == {"filmer": "omni", "narrator": "elevenlabs"}

    shown = me("--filmer", "heygen", "--narrator", "modal")
    assert "pick its voice" in shown and "SHORTS_SPEECH_URL" in shown and "GOOGLE_CLOUD_PROJECT" not in shown
    assert "in its voice v1" in me("--filmer-voice", "v1")
    assert chosen() == {"filmer": "heygen", "filmer_voice": "v1", "narrator": "modal"}
    me("--filmer-voice", "")
    assert chosen() == {"filmer": "heygen", "narrator": "modal"}


def test_a_new_run_takes_your_choices(tmp_path: Path, kept: Path) -> None:
    shorts("me", "--filmer", "heygen", "--filmer-voice", "v1", "--narrator", "elevenlabs", cwd=tmp_path, home=kept)
    run = Run(tmp_path / "runs" / "first")
    new(run, options())
    settings = run.settings()
    assert (settings.intro, settings.outro, settings.filmer_voice) == ("heygen", "heygen", "v1")
    assert (settings.narrator, settings.narration_model) == ("elevenlabs", "eleven_multilingual_v2")

    shorts("me", "--filmer", "import", cwd=tmp_path, home=kept)  # clips you bring in, for the next run
    later = Run(tmp_path / "runs" / "second")
    new(later, options(outro="none"))  # what it's given wins
    assert (later.settings().intro, later.settings().outro) == ("import", "none")
    assert run.settings().intro == "heygen"  # a run that's there keeps what it has


def test_another_narrator_for_a_run_speaks_with_its_own_model(tmp_path: Path, kept: Path) -> None:
    run = Run(tmp_path / "runs" / "first")
    run.save_settings(Settings(narrator="modal", narrator_model="omnivoice"))  # as a run.json from before wrote it
    new(run, options(narrator="elevenlabs"))
    assert (run.settings().narrator_model, run.settings().narration_model) == (None, "eleven_multilingual_v2")
    new(run, options(narrator="modal", narrator_model="chatterbox"))  # one it's given is kept
    assert run.settings().narration_model == "chatterbox"
    new(run, options(tone="hype"))  # the narrator as it was: so is its model
    assert run.settings().narration_model == "chatterbox"


def test_keys_adds_the_lines_your_choices_need(tmp_path: Path, kept: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def keys(*args: str) -> str:
        return shorts("keys", *args, cwd=tmp_path, home=kept)

    with pytest.raises(subprocess.CalledProcessError) as refused:
        keys()
    assert "choose who films you and who speaks the narration first" in refused.value.stderr
    shorts("me", "--filmer", "import", "--narrator", "modal", cwd=tmp_path, home=kept)
    for key in ("SHORTS_SPEECH_URL", "SHORTS_SPEECH_KEY"):
        monkeypatch.delenv(key, raising=False)  # the environment's would win over the file's
    shown = keys()
    assert f"{kept / '.env'}" in shown and "SHORTS_SPEECH_URL      empty" in shown and "deploy-voice" in shown
    assert "SHORTS_SPEECH_KEY=" in (kept / ".env").read_text()


def test_the_products_repo_has_its_own_notes_and_runs(
    tmp_path: Path, kept: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "acme"
    (repo / ".git").mkdir(parents=True)
    (repo / "web" / "src").mkdir(parents=True)
    monkeypatch.chdir(repo / "web" / "src")  # Claude Code, in a folder of the repo
    assert project() == repo and runs() == repo / ".makable-shorts" / "runs"
    a_file(kept / "products" / "acme.md", b"mine")
    a_file(kept / "products" / "other.md")
    assert products() == {"acme": kept / "products" / "acme.md", "other": kept / "products" / "other.md"}
    a_file(repo / ".makable-shorts" / "products" / "acme.md", b"the repo's")  # committed with its code: it wins
    assert products() == {
        "acme": repo / ".makable-shorts" / "products" / "acme.md",
        "other": kept / "products" / "other.md",
    }
    shown = shorts("me", cwd=repo / "web", home=kept)
    assert f"products   acme   {repo / '.makable-shorts' / 'products' / 'acme.md'}" in shown
    assert f"           other  {kept / 'products' / 'other.md'}" in shown

    monkeypatch.chdir(tmp_path)  # not in a repo: here, then
    assert project() == tmp_path and set(products()) == {"acme", "other"}


def test_a_run_folder_keeps_itself_out_of_git(tmp_path: Path, kept: Path) -> None:
    repo = tmp_path / "acme"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    a_file(repo / ".makable-shorts" / "products" / "acme.md")
    keep("face", a_file(tmp_path / "me.png"))
    shorts("new", ".makable-shorts/runs/first", "--tone", "hype", cwd=repo, home=kept)
    assert Run(repo / ".makable-shorts" / "runs" / "first").settings().tone == "hype"
    git = ["git", "status", "--porcelain", "--untracked-files=all"]
    changed = subprocess.run(git, cwd=repo, capture_output=True, text=True, check=True).stdout
    assert changed == "?? .makable-shorts/products/acme.md\n"  # the notes, to commit; none of the run


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
