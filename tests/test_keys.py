"""Your keys: which ones your choices need, the .env they go in, and deploy-voice deploying your voice API to Modal."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

from shorts import deploy
from shorts.keys import add, google_signed_in, load, needed, read, set_values

ADDRESS = "https://me--makable-voice-web.modal.run"


def test_env_file_fills_in_what_the_environment_doesnt_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHORTS_A", "from the environment")
    monkeypatch.delenv("SHORTS_B", raising=False)
    monkeypatch.delenv("SHORTS_C", raising=False)
    (tmp_path / ".env").write_text(
        "# a comment\nSHORTS_A=from the file\nexport SHORTS_B='quoted'\nSHORTS_C=\nnot a line\n"
    )
    load(tmp_path / ".env")
    assert (os.environ["SHORTS_A"], os.environ["SHORTS_B"], os.environ["SHORTS_C"]) == (
        "from the environment",
        "quoted",
        "",
    )
    load(tmp_path / "none.env")  # a file that isn't there sets nothing


def test_each_choice_needs_its_own_keys() -> None:
    assert needed({"filmer": "omni", "narrator": "elevenlabs"}) == ["GOOGLE_CLOUD_PROJECT", "ELEVENLABS_API_KEY"]
    assert needed({"filmer": "heygen", "narrator": "modal"}) == [
        "HEYGEN_API_KEY",
        "SHORTS_SPEECH_URL",
        "SHORTS_SPEECH_KEY",
    ]
    assert needed({"filmer": "import", "narrator": "elevenlabs"}) == ["ELEVENLABS_API_KEY"]
    assert needed({"filmer": "none", "narrator": "kokoro"}) == needed({"filmer": "none", "narrator": "none"}) == []
    assert needed({}) == []


def test_each_key_gets_a_line_in_a_file_only_you_can_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("GOOGLE_CLOUD_PROJECT", "ELEVENLABS_API_KEY", "HEYGEN_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    env, keys = tmp_path / "home" / ".env", ["GOOGLE_CLOUD_PROJECT", "ELEVENLABS_API_KEY"]
    assert add(keys, env) == keys
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    text = env.read_text()
    assert text.startswith("# Your keys for makable-shorts") and "\nGOOGLE_CLOUD_PROJECT=\n" in text
    assert "# ElevenLabs speaks the narration: an API key from elevenlabs.io" in text

    env.write_text(text.replace("ELEVENLABS_API_KEY=", "ELEVENLABS_API_KEY=sk-1"))  # you fill one in
    assert add(keys, env) == ["GOOGLE_CLOUD_PROJECT"]  # it's kept, and has no second line
    assert env.read_text().count("ELEVENLABS_API_KEY=") == 1 and read(env)["ELEVENLABS_API_KEY"] == "sk-1"

    monkeypatch.setenv("HEYGEN_API_KEY", "from the environment")  # it's set: no line for it
    assert add(["HEYGEN_API_KEY"], env) == [] and "HEYGEN_API_KEY" not in env.read_text()


def test_a_env_you_made_yourself_is_made_readable_by_you_alone(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("ELEVENLABS_API_KEY=sk-1\n")  # copied from .env.example and filled in: nothing to add
    env.chmod(0o644)
    assert add(["ELEVENLABS_API_KEY"], env) == []
    assert stat.S_IMODE(env.stat().st_mode) == 0o600 and env.read_text() == "ELEVENLABS_API_KEY=sk-1\n"


def test_setting_keys_changes_their_lines_and_keeps_the_rest(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# mine\nSHORTS_SPEECH_URL=\nOTHER=1\nexport SHORTS_SPEECH_URL=old\n")
    set_values({"SHORTS_SPEECH_URL": ADDRESS, "SHORTS_SPEECH_KEY": "k"}, env)
    assert (
        env.read_text()
        == f"# mine\nSHORTS_SPEECH_URL={ADDRESS}\nOTHER=1\nSHORTS_SPEECH_URL={ADDRESS}\nSHORTS_SPEECH_KEY=k\n"
    )
    assert stat.S_IMODE(env.stat().st_mode) == 0o600


def test_google_clouds_sign_in_is_found_where_gcloud_keeps_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setenv("CLOUDSDK_CONFIG", str(tmp_path / "gcloud"))
    assert not google_signed_in()
    (tmp_path / "gcloud").mkdir()
    (tmp_path / "gcloud" / "application_default_credentials.json").write_text("{}")
    assert google_signed_in()
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "gone.json"))  # it names one, not there
    assert not google_signed_in()


class Modal:
    """A stand-in for Modal's command line: what it's asked, the secret it's given, and what deploying prints."""

    def __init__(self, fails: str = "") -> None:
        self.asked: list[tuple[str, ...]] = []
        self.secret = ""
        self.fails = fails  # the command that fails

    def __call__(self, *args: str, keep: bool = True, timeout: float | None = None) -> subprocess.CompletedProcess:
        self.asked.append(args)
        if args[:2] == ("secret", "create"):
            self.secret = Path(args[args.index("--from-dotenv") + 1]).read_text()
        said = f"Created web function web => {ADDRESS}\nApp deployed!" if args[0] == "deploy" else ""
        if args[0] == self.fails:
            return subprocess.CompletedProcess(args, 1, f"Error: no GPUs, with {self.secret.partition('=')[2]}")
        return subprocess.CompletedProcess(args, 0, said)


@pytest.fixture
def modal(monkeypatch: pytest.MonkeyPatch) -> Modal:
    modal = Modal()
    monkeypatch.setattr(deploy, "modal", modal)
    monkeypatch.setattr(deploy, "signed_in", lambda: True)
    for key in ("SHORTS_SPEECH_URL", "SHORTS_SPEECH_KEY"):
        monkeypatch.delenv(key, raising=False)
    return modal


def test_deploy_voice_keeps_the_address_and_its_key_in_the_env(
    tmp_path: Path, modal: Modal, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    env = tmp_path / ".env"
    assert deploy.deploy_voice(env) == ADDRESS
    kept = read(env)
    assert kept["SHORTS_SPEECH_URL"] == ADDRESS and len(kept["SHORTS_SPEECH_KEY"]) > 30
    assert modal.secret == f"VOICE_API_KEY={kept['SHORTS_SPEECH_KEY']}\n"
    assert [args[:2] for args in modal.asked] == [("secret", "create"), ("deploy", "-m")]
    assert kept["SHORTS_SPEECH_KEY"] not in capsys.readouterr().out

    # Again after an update: the same key, so a .env elsewhere with it stays right.
    monkeypatch.setenv("SHORTS_SPEECH_URL", ADDRESS)
    monkeypatch.setenv("SHORTS_SPEECH_KEY", kept["SHORTS_SPEECH_KEY"])
    deploy.deploy_voice(env)
    assert read(env)["SHORTS_SPEECH_KEY"] == kept["SHORTS_SPEECH_KEY"]
    assert kept["SHORTS_SPEECH_KEY"] not in capsys.readouterr().out

    # A key that isn't a voice API on Modal's (ElevenLabs', as SHORTS_SPEECH_URL once took it) isn't sent to Modal.
    monkeypatch.setenv("SHORTS_SPEECH_URL", "https://api.elevenlabs.io")
    monkeypatch.setenv("SHORTS_SPEECH_KEY", "sk-elevenlabs")
    deploy.deploy_voice(env)
    assert "sk-elevenlabs" not in modal.secret and read(env)["SHORTS_SPEECH_KEY"] != "sk-elevenlabs"
    assert read(env)["SHORTS_SPEECH_KEY"] not in capsys.readouterr().out


def test_deploy_voice_signs_in_to_modal_first_and_says_what_went_wrong(
    tmp_path: Path, modal: Modal, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(deploy, "signed_in", lambda: False)
    modal.fails = "deploy"
    env = tmp_path / ".env"
    with pytest.raises(RuntimeError, match="Modal failed deploying the voice API") as failed:
        deploy.deploy_voice(env)
    assert modal.asked[0] == ("setup",)
    key = modal.secret.partition("=")[2].strip()
    assert key not in str(failed.value)  # what Modal said, without the key

    # The .env has the key Modal has, from before Modal had it: running it again finishes with the same key.
    assert read(env) == {"SHORTS_SPEECH_KEY": key}
    monkeypatch.setenv("SHORTS_SPEECH_KEY", key)  # as the command loads the .env
    modal.fails = ""
    deploy.deploy_voice(env)
    assert read(env) == {"SHORTS_SPEECH_KEY": key, "SHORTS_SPEECH_URL": ADDRESS}


def test_a_modal_command_that_stalls_is_given_up_on(monkeypatch: pytest.MonkeyPatch) -> None:
    def stalls(command: list[str], **options) -> None:
        raise subprocess.TimeoutExpired(command, options["timeout"])

    monkeypatch.setattr(subprocess, "run", stalls)
    with pytest.raises(RuntimeError, match="`modal deploy` hadn't finished after 30 minutes"):
        deploy.modal("deploy", "-m", "services.voice.app", timeout=deploy.DEPLOY_WAIT)
