"""Your keys: the ones the services you chose need, in SHORTS_HOME's .env, which you fill in yourself.

    python -m shorts keys [--open]

Who films you and who speaks the narration (`python -m shorts me --filmer ... --narrator ...`, `home.chosen`) say
which keys a video needs (`needed`). `keys` adds a line to the .env for each one it hasn't, under a comment saying
where to get it, and with --open, opens the file in your text editor: you paste the keys in there, so they never
pass through Claude, and nothing here prints one. The file is readable by you alone.

The commands take the keys from the environment, or from this file for what the environment doesn't set (`load`).
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import COMMAND
from .home import home

HEADER = "# Your keys for makable-shorts: KEY=value, one a line. The environment wins over this file."

# Each key, and where to get it: `add` writes it in a comment above the key's line.
ABOUT = {
    "GOOGLE_CLOUD_PROJECT": (
        "Gemini Omni films you in this Google Cloud project: its ID, from console.cloud.google.com (with billing, and "
        "the Vertex AI API on). Sign in to it once: gcloud auth application-default login"
    ),
    "HEYGEN_API_KEY": "HeyGen films you: an API key from app.heygen.com (Settings, API), paid from its API balance",
    "ELEVENLABS_API_KEY": (
        "ElevenLabs speaks the narration: an API key from elevenlabs.io (Developers, API keys), on a plan that can "
        "clone a voice"
    ),
    "SHORTS_SPEECH_URL": f"Your voice API on Modal speaks the narration: its address. `{COMMAND} deploy-voice` sets it",
    "SHORTS_SPEECH_KEY": f"and its key, which `{COMMAND} deploy-voice` sets too",
}

# The keys each choice needs: who films you (`filmer`), and who speaks (`narrator`).
NEEDS = {
    "omni": ("GOOGLE_CLOUD_PROJECT",),
    "heygen": ("HEYGEN_API_KEY",),
    "import": (),
    "none": (),  # no avatar, or no voice
    "elevenlabs": ("ELEVENLABS_API_KEY",),
    "modal": ("SHORTS_SPEECH_URL", "SHORTS_SPEECH_KEY"),
    "kokoro": (),  # on this machine
}


def env_file() -> Path:
    return home() / ".env"


def needed(choices: dict[str, str]) -> list[str]:
    """The keys your choices need (`home.chosen`'s), in ABOUT's order."""
    wanted = {key for choice in (choices.get("filmer"), choices.get("narrator")) for key in NEEDS.get(choice or "", ())}
    return [key for key in ABOUT if key in wanted]


def read(file: Path) -> dict[str, str]:
    """What a .env file says: KEY=value lines, # for comments, with quotes or `export` in front if you like."""
    found = {}
    for line in file.read_text().splitlines() if file.exists() else []:
        key, equals, value = line.strip().removeprefix("export ").partition("=")
        if equals and key.strip() and not key.startswith("#"):
            found[key.strip()] = value.strip().strip("'\"")
    return found


def load(file: Path) -> None:
    """Sets what a .env file says, for what the environment doesn't set."""
    for key, value in read(file).items():
        os.environ.setdefault(key, value)


def _write(file: Path, text: str) -> None:
    """Writes the .env all at once, so a failed write loses nothing, readable by you alone. Each write goes through
    a file of its own (mkstemp's, made readable by you alone), so two at once never clash."""
    file.parent.mkdir(parents=True, exist_ok=True)
    handle, part = tempfile.mkstemp(dir=file.parent, prefix=f".{file.name}.", suffix=".part")
    try:
        with os.fdopen(handle, "w") as out:
            out.write(text)
        os.replace(part, file)
    finally:
        Path(part).unlink(missing_ok=True)


def add(keys: list[str], file: Path) -> list[str]:
    """Adds a line to the .env for each of `keys` that neither it nor the environment has, with what the key is for
    above it, making the file if it isn't there, and makes it readable by you alone. Returns the keys that are still
    empty."""
    there = read(file)
    lines = [
        line
        for key in keys
        if key not in there and not os.environ.get(key)
        for line in ("", f"# {ABOUT[key]}", f"{key}=")
    ]
    if lines or not file.exists():
        text = file.read_text().rstrip("\n") if file.exists() else HEADER
        _write(file, "\n".join([text, *lines]) + "\n")
    else:  # one you made yourself, from .env.example, say
        file.chmod(0o600)
    there = read(file)
    return [key for key in keys if not (os.environ.get(key) or there.get(key))]


def set_values(values: dict[str, str], file: Path) -> None:
    """Sets keys in the .env, on the lines they're on, or on new ones at the end."""
    lines = file.read_text().splitlines() if file.exists() else [HEADER]
    done = set()
    for number, line in enumerate(lines):
        key, equals, _ = line.strip().removeprefix("export ").partition("=")
        if equals and key.strip() in values:
            lines[number] = f"{key.strip()}={values[key.strip()]}"
            done.add(key.strip())
    lines += [f"{key}={value}" for key, value in values.items() if key not in done]
    _write(file, "\n".join(lines) + "\n")


def google_signed_in() -> bool:
    """Whether Google Cloud's sign-in for programs is here: the file GOOGLE_APPLICATION_CREDENTIALS names (GitHub
    Actions' google-github-actions/auth sets it), or the one `gcloud auth application-default login` writes."""
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return Path(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]).expanduser().exists()
    gcloud = Path(os.environ.get("CLOUDSDK_CONFIG") or Path.home() / ".config" / "gcloud").expanduser()
    return (gcloud / "application_default_credentials.json").exists()


def open_in_editor(file: Path) -> bool:
    """Opens the file in your text editor, if this machine has a way to (macOS's `open -t`, or xdg-open), and says
    whether it did."""
    command = ["open", "-t", str(file)] if sys.platform == "darwin" else ["xdg-open", str(file)]
    try:
        return subprocess.run(command, capture_output=True).returncode == 0
    except FileNotFoundError:
        return False
