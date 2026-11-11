"""Your own things, kept for every video, in SHORTS_HOME (~/.config/makable-shorts unless that's set):

    .env                 your keys (KEY=value lines), for what the environment doesn't set (`shorts.keys`)
    me/face.png          a photo of you, for whoever films you; me/music.mp3, played under the video; and
    me/voice.wav         a sample of you talking (`python -m shorts me` keeps them)
    choices.json         who films you (Gemini Omni, HeyGen, clips you bring in, or no one: a video without an
                         avatar) and who speaks the narration (ElevenLabs, your own voice API on Modal, Kokoro on
                         this machine, or no one: a video without a voice): `python -m shorts me --filmer --narrator`
    products/<name>.md   what the make-video skill knows about each product: its address, how to say its name, ...
    sites/<host>/        a Chrome profile signed in to each site (`python -m shorts signin`)
    sign-offs/hi.mp4     your sign-off for "useful website" Shorts, a language at a time: one clip of your avatar
    sign-offs/hi.json    saying it (and what it says), brought in as each one's outro (`python -m shorts sign-off`)
    topics.json          the sites those Shorts were made about, so none is made twice (`shorts.trends`)
    trends/<date>.json   the day's YouTube searches, kept so the same one again that day costs no quota

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
CHOICES = ("filmer", "filmer_voice", "narrator", "kokoro_voice")  # and what it keeps of your choices (`chosen`)


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


def sign_off(language: str) -> tuple[Path, str] | None:
    """Your sign-off for website Shorts in `language` ("hi"): the clip, and what's said in it. None: none is kept."""
    clip, about = home() / "sign-offs" / f"{language}.mp4", home() / "sign-offs" / f"{language}.json"
    if not clip.exists() or not about.exists():
        return None
    return clip, json.loads(about.read_text())["line"]


def sign_offs() -> dict[str, str]:
    """What each kept sign-off says, by its language."""
    folder = home() / "sign-offs"
    found = (sign_off(about.stem) for about in sorted(folder.glob("*.json"))) if folder.exists() else ()
    return {clip.stem: line for clip, line in filter(None, found)}


def keep_sign_off(language: str, clip: Path, line: str) -> Path:
    """Keeps a copy of `clip`, an MP4 of your avatar saying `line`, as your sign-off in `language`, in place of the
    one kept before."""
    if not re.fullmatch(r"[a-z]{2,3}", language):
        raise ValueError(f"{language!r} isn't a language's code, such as hi or en")
    if not line.strip():
        raise ValueError("Say what the sign-off says: its line")
    folder = home() / "sign-offs"
    folder.mkdir(parents=True, exist_ok=True)
    kept = folder / f"{language}.mp4"
    part = folder / f".{language}.part.mp4"  # first, so a failed copy loses nothing
    shutil.copyfile(Path(clip).expanduser(), part)
    part.replace(kept)
    about = folder / f".{language}.part.json"
    about.write_text(json.dumps({"line": line.strip()}, ensure_ascii=False, indent=1) + "\n")
    about.replace(folder / f"{language}.json")
    return kept
