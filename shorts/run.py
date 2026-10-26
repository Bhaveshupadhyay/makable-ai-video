"""The run folder: the one thing the stages share, and the contract between them.

Each stage is a program of its own (`python -m shorts <stage> RUN`), with its own packages, that reads files
from a video's run folder and writes others there, under these names and in these formats. No stage calls or
imports another, so anything that writes a file under its name can stand in for the stage that makes it:
`python -m shorts import` brings in files made elsewhere (the script Claude writes, a clip from the Gemini app,
scenes spoken by another tool).

    run.json                         the settings: what the video is made from (yours to edit)
    footage/<name>.mp4               each recording the scenes are said over, and
    footage/<name>.steps.json        what happens in it when (browser-use's steps), if that's known
    script.json                      what's said (`script.Script`): the intro and outro lines, and each scene
    intro/filmed.mp4                 Omni's clip of you saying the intro line, used as filmed
    outro/filmed.mp4                 and the outro line
    voice/avatar.wav                 the intro's voice, to speak the narration in (with narration_voice "intro")
    narration/01.wav, 02.wav, ...    each scene's narration
    final.mp4, metadata.json         the video, and what to upload it with
    .records/<product>.json          what made each of a product's files, and from what

A product is the files one stage makes. Its record notes, for each file, a fingerprint of what it was made
from and of the file as written. So a file is out of date when what it would be made from now differs (the
scene's text, the voice sample, a setting), and only that file is made again. A file that changed since it
was written was edited by hand: it's kept as it is.
"""

import contextlib
import hashlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from .script import Script

SETTINGS = "run.json"
SCRIPT = "script.json"
FILMED_INTRO = "intro/filmed.mp4"
FILMED_OUTRO = "outro/filmed.mp4"
AVATAR_VOICE = "voice/avatar.wav"
FINAL = "final.mp4"
METADATA = "metadata.json"
RECORDS = ".records"

# What each stage makes, in the order they're made.
PRODUCTS = ("footage", "script", "intro", "outro", "avatar-voice", "narration", "video")


def footage_file(name: str) -> str:
    return f"footage/{name}.mp4"


def steps_file(name: str) -> str:
    return f"footage/{name}.steps.json"


def narration_file(index: int) -> str:
    """Scene `index`'s narration, counting from 0: narration/01.wav for the first."""
    return f"narration/{index + 1:02d}.wav"


class Settings(BaseModel):
    """What a video is made from (run.json). Paths are relative to the run folder, or absolute."""

    language: str = "en"  # what the script is written and spoken in: one of script.LANGUAGES
    tone: str = "friendly"  # how the script sounds: one of script.TONES
    footage: dict[str, str] = {}  # each recording, by name: a file to copy in (browse brings its recordings in)
    intro: Literal["omni", "import"] = "omni"  # intro/filmed.mp4: Gemini Omni films it (about $1), or import
    outro: Literal["omni", "import", "none"] = "omni"  # outro/filmed.mp4: the same, or the video has no outro
    # Who speaks narration/*.wav: a text-to-speech API (shorts.speech_api: the voice API on Modal, or ElevenLabs),
    # or you bring it in. It's in the voice of the person in Omni's intro (voice/avatar.wav), or of the `voice`
    # sample, with narration_voice "sample".
    narrator: Literal["api", "import"] = "api"
    narration_voice: Literal["intro", "sample"] = "intro"
    narrator_model: str = "omnivoice"  # the API's model: "omnivoice" or "chatterbox" on ours, ElevenLabs' own on theirs
    narrator_options: dict[str, float | bool | str] = {}  # the API's voice_settings: OmniVoice's speed, say
    pronounce: dict[str, str] | None = None  # words to respell for the narrator; voice.PRONOUNCE by default
    reference_text: str | None = None  # what's said in the voice sample, for OmniVoice (None: Whisper hears it)
    face: str | None = None  # a photo of you, for Omni
    voice: str | None = None  # a sample of you talking, 3 to 10 seconds (with narration_voice "sample")
    music: str | None = None  # played quietly under the video
    size: tuple[int, int] = (1080, 1920)  # the video's width and height
    captions: bool = True


class Made(BaseModel):
    """A file a stage wrote."""

    by: str  # the stage, as it calls itself: "speak (omnivoice)", "import"
    source: str  # a fingerprint of what it was made from
    sha256: str  # of the file as it was written


class Record(BaseModel):
    """A product's record (.records/<product>.json). Only the stage making the product writes it."""

    files: dict[str, Made] = {}  # by path in the run folder


def fingerprint(*parts: Any) -> str:
    """A short fingerprint of what something is made from (anything JSON can write)."""
    text = json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


_hashes: dict[tuple[str, int, int], str] = {}


def file_hash(path: Path) -> str:
    """The SHA-256 of a file's contents, worked out once for each version of the file."""
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    if key not in _hashes:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            while chunk := file.read(1 << 20):
                digest.update(chunk)
        _hashes[key] = digest.hexdigest()
    return _hashes[key]


@contextlib.contextmanager
def writing(path: Path) -> Iterator[Path]:
    """A name to write `path` under, moved into place only if the writing works: a stage that fails halfway
    never leaves a file that looks made. It keeps the extension, for tools that go by it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.part{path.suffix}")
    try:
        yield temporary
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Run:
    """A video's run folder."""

    def __init__(self, folder: Path | str) -> None:
        self.folder = Path(folder)

    def path(self, name: str) -> Path:
        """A file in the run folder, by its name in the contract."""
        return self.folder / name

    def resolve(self, value: str) -> Path:
        """A path from the settings: relative to the run folder, or absolute."""
        return (self.folder / Path(value).expanduser()).resolve()

    def relative(self, path: Path) -> str:
        """`path` as the settings keep it: relative to the run folder, so a copy of the folder elsewhere works."""
        return os.path.relpath(Path(path).expanduser().resolve(), self.folder.resolve())

    def settings(self) -> Settings:
        file = self.path(SETTINGS)
        return Settings.model_validate_json(file.read_text()) if file.exists() else Settings()

    def save_settings(self, settings: Settings) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        with writing(self.path(SETTINGS)) as out:
            out.write_text(settings.model_dump_json(indent=2) + "\n")

    def script(self) -> Script:
        return Script.model_validate_json(self.path(SCRIPT).read_text())

    def record(self, product: str) -> Record:
        file = self.folder / RECORDS / f"{product}.json"
        return Record.model_validate_json(file.read_text()) if file.exists() else Record()

    def save_record(self, product: str, record: Record) -> None:
        with writing(self.folder / RECORDS / f"{product}.json") as out:
            out.write_text(record.model_dump_json(indent=1) + "\n")
