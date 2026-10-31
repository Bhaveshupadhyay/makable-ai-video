"""deploy-voice: the voice API (services/voice: OmniVoice and Chatterbox, on GPUs) on your own Modal account, to speak
the narration with (run.json's narrator "modal"), with its address and key in SHORTS_HOME's .env.

    python -m shorts deploy-voice

It runs Modal's own command through uv, so there's nothing to install, in the folder services/ is in (the plugin's).
If Modal has no sign-in here yet, it has Modal open your browser to sign in, or make an account, and waits until you
have. Then it writes the API's key (SHORTS_SPEECH_KEY) into the .env, a new one unless the .env has one for a voice API
on Modal already, keeps it in a Modal secret (makable-voice), deploys the API, and writes its address
(SHORTS_SPEECH_URL) into the .env too. The key is never printed. The key is in the .env before Modal has it, so if this
stops partway, running it again finishes the job with the same key.

Run it again after an update, to deploy the new version: it keeps the key, so a .env elsewhere with it stays right.
Modal charges your account for each model's GPU while it speaks, and a little while after (`services/voice/app.py`).
"""

import os
import re
import secrets
import subprocess
import tempfile
from pathlib import Path

from .keys import env_file, set_values
from .orchestrator import PACKAGE_ROOT

MODAL = "modal==1.6.2"  # the Modal services/voice/app.py is written for
SECRET = "makable-voice"  # the secret app.py reads VOICE_API_KEY from
ADDRESS = re.compile(r"https://[\w.-]+\.modal\.run")
SECRET_WAIT = 5 * 60  # seconds before giving up on keeping the key
DEPLOY_WAIT = 30 * 60  # and on deploying: the first time, Modal builds the models' images


def modal(*args: str, keep: bool = True, timeout: float | None = None) -> subprocess.CompletedProcess:
    """Runs Modal's command line (through uv) in PACKAGE_ROOT, where services/ is, for `timeout` seconds at most
    (None: as long as it takes, for signing in). With `keep`, what it prints is kept, not shown, printed wide enough
    that an address isn't broken over two lines.

    Raises:
        RuntimeError: It ran past `timeout`.
    """
    command = ["uv", "tool", "run", "--from", MODAL, "modal", *args]
    output = {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT} if keep else {}
    try:
        return subprocess.run(
            command, cwd=PACKAGE_ROOT, text=True, env={**os.environ, "COLUMNS": "1000"}, timeout=timeout, **output
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"`modal {args[0]}` hadn't finished after {timeout / 60:g} minutes") from error


def signed_in() -> bool:
    """Whether Modal has a sign-in here: a token in the environment, or its config file (~/.modal.toml)."""
    config = Path(os.environ.get("MODAL_CONFIG_PATH") or Path.home() / ".modal.toml").expanduser()
    return bool(os.environ.get("MODAL_TOKEN_ID")) or config.exists()


def _check(done: subprocess.CompletedProcess, doing: str, key: str) -> subprocess.CompletedProcess:
    if done.returncode:
        said = (done.stdout or "").replace(key, "…")[-2000:]
        raise RuntimeError(f"Modal failed {doing} (it exited with {done.returncode}): {said}")
    return done


def deploy_voice(env: Path | None = None) -> str:
    """Deploys the voice API to your Modal account (see the module's docstring), and returns its address.

    Raises:
        RuntimeError: Modal's command failed: what it said.
    """
    env = env or env_file()
    if not signed_in():
        print("Modal opens your browser: sign in there, or make an account. This goes on once you have.", flush=True)
        _check(modal("setup", keep=False), "signing in", "")
    # The key the .env has, unless it's for another API (ElevenLabs', as SHORTS_SPEECH_URL once took it).
    url = os.environ.get("SHORTS_SPEECH_URL", "").rstrip("/")
    ours = not url or ADDRESS.fullmatch(url)
    key = (ours and os.environ.get("SHORTS_SPEECH_KEY")) or secrets.token_urlsafe(32)
    set_values({"SHORTS_SPEECH_KEY": key}, env)  # first: Modal never has a key the .env hasn't
    with tempfile.TemporaryDirectory() as work:  # in a file of your own, so the key isn't on a command line
        secret = Path(work) / "voice.env"
        with os.fdopen(os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as out:
            out.write(f"VOICE_API_KEY={key}\n")
        kept = modal("secret", "create", SECRET, "--from-dotenv", str(secret), "--force", timeout=SECRET_WAIT)
        _check(kept, "keeping the key", key)
    print("Deploying the voice API: the first time, Modal builds the models' images, which takes several minutes")
    deployed = _check(modal("deploy", "-m", "services.voice.app", timeout=DEPLOY_WAIT), "deploying the voice API", key)
    print(deployed.stdout.replace(key, "…"))
    address = ADDRESS.search(deployed.stdout)
    if not address:
        raise RuntimeError(
            "Modal deployed the voice API, but didn't say its address (https://….modal.run): find it at "
            "modal.com/apps, and set SHORTS_SPEECH_URL to it in the .env"
        )
    set_values({"SHORTS_SPEECH_URL": address[0]}, env)
    return address[0]


def health(address: str) -> str:
    """What the API says it speaks with ("omnivoice, chatterbox"), or why it didn't answer."""
    import httpx

    try:
        answer = httpx.get(f"{address}/health", timeout=120)
        answer.raise_for_status()
        return ", ".join(answer.json().get("models", [])) or "no models"
    except (httpx.HTTPError, ValueError) as error:
        return f"no answer ({error})"
