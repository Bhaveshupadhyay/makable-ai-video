"""Your own things, kept for every video, in SHORTS_HOME (~/.config/makable-shorts unless that's set):

    .env                 your keys (KEY=value lines), for what the environment doesn't set
    me/face.png          a photo of you, for whoever films you; me/music.mp3, played under the video; and
    me/voice.wav         a sample of you talking (`python -m shorts me` keeps them)
    products/<name>.md   what the make-video skill knows about each product: its address, how to say its name, ...
    sites/<host>/        a Chrome profile signed in to each site (`python -m shorts signin`)

A new run takes your photo, music and voice from here unless it's given others (`python -m shorts new`).
"""

import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

MINE = ("face", "music", "voice")  # what `me` keeps: run.json's settings of the same names


def home() -> Path:
    return Path(os.environ.get("SHORTS_HOME") or Path.home() / ".config" / "makable-shorts").expanduser()


def mine() -> dict[str, Path]:
    """Your photo, music and voice sample, those that are kept, by run.json's name for them."""
    folder = home() / "me"
    found = {kind: sorted(folder.glob(f"{kind}.*")) for kind in MINE}
    return {kind: files[0] for kind, files in found.items() if files}


def keep(kind: str, file: Path | None) -> Path | None:
    """Keeps a copy of `file` as your `kind` (one of MINE), in place of the one kept before, or forgets it (None)."""
    folder = home() / "me"
    for old in folder.glob(f"{kind}.*"):
        old.unlink()
    if file is None:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    kept = folder / f"{kind}{Path(file).suffix.lower()}"
    shutil.copyfile(Path(file).expanduser(), kept)
    return kept


def site(url: str) -> str:
    """The site an address is on, as its profile's folder is named: "app.example.com", "localhost_3000"."""
    parts = urlsplit(url if "//" in url else f"https://{url}")
    if not parts.hostname:
        raise ValueError(f"{url!r} isn't a web address")
    return re.sub(r"[^\w.-]", "_", parts.netloc.lower())


def site_profile(url: str) -> Path:
    """The Chrome profile signed in to `url`'s site (whether or not it's been made)."""
    return home() / "sites" / site(url)


def signed_in_sites() -> list[str]:
    """The sites there's a signed-in profile for."""
    folder = home() / "sites"
    return sorted(entry.name for entry in folder.iterdir() if entry.is_dir()) if folder.exists() else []
