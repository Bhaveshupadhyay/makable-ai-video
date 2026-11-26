"""Your own things, kept for every video, in SHORTS_HOME (~/.config/makable-shorts unless that's set):

    .env                 your keys (KEY=value lines), for what the environment doesn't set (`shorts.keys`)
    me/face.png          a photo of you, for whoever films you; me/music.mp3, played under the video; and
    me/voice.wav         a sample of you talking; me/subscribe.mp4, a green-screen subscribe animation shown over
                         the last scene (`python -m shorts me` keeps them)
    me/characters/<name>.png   a mascot's character sheet, for every animated Short it's in (`me --character`)
    choices.json         who films you (Gemini Omni, HeyGen, clips you bring in, or no one: a video without an
                         avatar) and who speaks the narration (ElevenLabs, your own voice API on Modal, Kokoro on
                         this machine, or no one: a video without a voice): `python -m shorts me --filmer --narrator`
    products/<name>.md   what the make-video skill knows about each product: its address, how to say its name, ...
    sites/<host>/        a Chrome profile signed in to each site (`python -m shorts signin`)
    accounts/<name>.json your YouTube channel and Instagram account, connected for the numbers on what you've
                         posted (`python -m shorts connect`, `shorts.platforms`): readable by you alone

A new run takes a copy of your photo, music and voice from here, and your choices, unless it's given others
(`shorts.run`).

And in the project it's run in, the product's own repo (the top of the git repo it's run in, or else the working
directory), under .makable-shorts/:

    products/<name>.md   the notes on the product whose code this is, committed with it, for teammates and CI too
    runs/<name>/         each video's run folder, which keeps itself out of git (`shorts.run`)
"""

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MINE = ("face", "music", "voice", "subscribe")  # what `me` keeps: run.json's settings of the same names
# and what it keeps of your choices (`chosen`): an animated Short's image model and animator too
CHOICES = ("filmer", "filmer_voice", "narrator", "kokoro_voice", "image_model", "animator")


def home() -> Path:
    return Path(os.environ.get("SHORTS_HOME") or Path.home() / ".config" / "makable-shorts").expanduser()


def project() -> Path:
    """The project the pipeline is run in: the top of the git repo holding the working directory, or the working
    directory itself, outside one."""
    here = Path.cwd()
    return next((folder for folder in (here, *here.parents) if (folder / ".git").exists()), here)


def runs() -> Path:
    """Where the project's run folders go."""
    return project() / ".makable-shorts" / "runs"


def products() -> dict[str, Path]:
    """The notes on each product, by its name: SHORTS_HOME's, and the project's (which win, for the same name)."""
    found = {}
    for folder in (home() / "products", project() / ".makable-shorts" / "products"):
        found.update({notes.stem: notes for notes in folder.glob("*.md")})
    return dict(sorted(found.items()))


def mine() -> dict[str, Path]:
    """Your photo, music and voice sample, those that are kept, by run.json's name for them."""
    folder = home() / "me"
    found = {kind: sorted(folder.glob(f"{kind}.*")) for kind in MINE}
    return {kind: files[0] for kind, files in found.items() if files}


def keep(kind: str, file: Path | None) -> Path | None:
    """Keeps a copy of `file` as your `kind` (one of MINE), in place of the one kept before, or forgets it (None).

    Raises:
        ValueError: `file` has no extension, which says what type it is.
    """
    folder = home() / "me"
    kept = None
    if file is not None:
        file = Path(file).expanduser()
        if not file.suffix:
            raise ValueError(f"{file} has no extension to say what it is: name it for its type, such as photo.png")
        folder.mkdir(parents=True, exist_ok=True)
        kept = folder / f"{kind}{file.suffix.lower()}"
        copy = folder / f".{kind}.part{file.suffix.lower()}"  # first, so a failed copy loses nothing
        shutil.copyfile(file, copy)
        copy.replace(kept)
    for old in folder.glob(f"{kind}.*"):
        if old != kept:
            old.unlink()
    return kept


def character(name: str) -> Path | None:
    """A mascot's character sheet, if one's kept by that name."""
    sheet = home() / "me" / "characters" / f"{name}.png"
    return sheet if sheet.exists() else None


def keep_character(name: str, file: Path | None) -> Path | None:
    """Keeps a copy of `file` (a PNG) as the mascot `name`'s character sheet, or forgets it (None)."""
    if not re.fullmatch(r"[\w-]+", name):
        raise ValueError(f"{name!r} isn't a name a character can have: letters, digits, - and _")
    sheet = home() / "me" / "characters" / f"{name}.png"
    if file is None:
        sheet.unlink(missing_ok=True)
        return None
    sheet.parent.mkdir(parents=True, exist_ok=True)
    part = sheet.with_name(f".{sheet.name}.part")
    shutil.copyfile(Path(file).expanduser(), part)
    part.replace(sheet)
    return sheet


def chosen() -> dict[str, str]:
    """Your choices, those you've made: `filmer` ("omni", "heygen", "import", or "none" for no avatar), the HeyGen
    voice it films you in (`filmer_voice`), `narrator` ("elevenlabs", "modal", "kokoro", or "none" for no voice), and
    Kokoro's voice (`kokoro_voice`)."""
    file = home() / "choices.json"
    return json.loads(file.read_text()) if file.exists() else {}


def choose(**choices: str | None) -> dict[str, str]:
    """Keeps these choices (any of CHOICES) in place of the ones before, or forgets those given as "". Returns all
    of them."""
    kept = {**chosen(), **{name: value for name, value in choices.items() if value is not None}}
    kept = {name: value for name, value in kept.items() if value}
    file = home() / "choices.json"
    file.parent.mkdir(parents=True, exist_ok=True)
    part = file.with_name(f".{file.name}.part")  # first, so a failed write loses nothing
    part.write_text(json.dumps(kept, indent=1) + "\n")
    part.replace(file)
    return kept


def site(url: str) -> str:
    """The site an address is on, as its profile's folder is named: "app.example.com", "localhost_3000". A www.
    in front doesn't make another site: a sign-in to example.com is one to www.example.com."""
    parts = urlsplit(url if "//" in url else f"https://{url}")
    host = (parts.hostname or "").removeprefix("www.")
    # Only a host's own names (or an IPv6 address): never "", "." or "..", so a site's folder is always in sites/,
    # and `forget` deletes nothing else.
    try:
        port = parts.port
    except ValueError:  # not a number
        host = ""
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)*|[0-9a-f:]+", host):
        raise ValueError(f"{url!r} isn't a web address")
    return host.replace(":", "_") + (f"_{port}" if port else "")


def site_profile(url: str) -> Path:
    """The Chrome profile signed in to `url`'s site (whether or not it's been made)."""
    return home() / "sites" / site(url)


def signed_in_sites() -> list[str]:
    """The sites there's a signed-in profile for."""
    folder = home() / "sites"
    return sorted(entry.name for entry in folder.iterdir() if entry.is_dir()) if folder.exists() else []


def account(platform: str) -> dict[str, Any]:
    """What `connect` keeps to use a platform as you (`shorts.platforms`), or {} if it isn't connected."""
    file = home() / "accounts" / f"{platform}.json"
    return json.loads(file.read_text()) if file.exists() else {}


def keep_account(platform: str, kept: dict[str, Any] | None) -> None:
    """Keeps what's needed to use a platform as you, in a file only you can read, or forgets it (None)."""
    file = home() / "accounts" / f"{platform}.json"
    if kept is None:
        file.unlink(missing_ok=True)
        return
    file.parent.mkdir(parents=True, exist_ok=True)
    # first into a file of its own (mkstemp: only you can read it), so a failed write, or another at the same time,
    # loses nothing
    descriptor, part = tempfile.mkstemp(dir=file.parent, prefix=f"{file.name}.", suffix=".part")
    try:
        with os.fdopen(descriptor, "w") as out:
            json.dump(kept, out, indent=1)
        os.replace(part, file)
    except BaseException:
        Path(part).unlink(missing_ok=True)
        raise


def accounts() -> dict[str, dict[str, Any]]:
    """The platforms that are connected, and what's kept for each."""
    folder = home() / "accounts"
    return {file.stem: json.loads(file.read_text()) for file in sorted(folder.glob("*.json"))}
