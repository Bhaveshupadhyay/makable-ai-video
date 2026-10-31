"""Your own things, kept for every video, in SHORTS_HOME (~/.config/makable-shorts unless that's set):

    .env                 your keys (KEY=value lines), for what the environment doesn't set (`shorts.keys`)
    me/face.png          a photo of you, for whoever films you; me/music.mp3, played under the video; and
    me/voice.wav         a sample of you talking (`python -m shorts me` keeps them)
    choices.json         who films you (Gemini Omni, HeyGen, or clips you bring in) and who speaks the narration
                         (ElevenLabs, or your own voice API on Modal): `python -m shorts me --filmer --narrator`
    products/<name>.md   what the make-video skill knows about each product: its address, how to say its name, ...
    sites/<host>/        a Chrome profile signed in to each site (`python -m shorts signin`)

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
from pathlib import Path
from urllib.parse import urlsplit

MINE = ("face", "music", "voice")  # what `me` keeps: run.json's settings of the same names
CHOICES = ("filmer", "filmer_voice", "narrator")  # and what it keeps of your choices (`chosen`)


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


def chosen() -> dict[str, str]:
    """Your choices, those you've made: `filmer` ("omni", "heygen" or "import"), the HeyGen voice it films you in
    (`filmer_voice`), and `narrator` ("elevenlabs" or "modal")."""
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
