"""assemble: final.mp4 and metadata.json. The intro as filmed, then each scene's stretch of its recording while its
narration plays (sped up or slowed down to fit it), then the outro as filmed, if run.json wants one, with captions
and music, at -14 LUFS.

A video without an avatar opens on a title card instead (intro "card"): the intro line in big letters over a still
of the recording (`shorts.cards`), while the narrator says it. It ends on an end card with the outro line. A video
without a voice (narrator "none") plays each scene's stretch at its own speed, or slower if its words take longer to
read, while the captions say them, and holds each card for as long as it takes to read.

A scene without a stretch plays its recording on from where the scene before on it stopped. Needs only ffmpeg, and
Pillow for the captions and the cards.
"""

import json
import tempfile
from pathlib import Path

from ..cards import LOOK
from ..compose import COLOURS, FONT_CACHE, GAP, TAIL, Part, compose, even, whole_frames
from ..media import duration, speech_span, still
from ..run import (
    CARD_NARRATION,
    FILMED_INTRO,
    FILMED_OUTRO,
    FINAL,
    METADATA,
    NARRATOR_MODELS,
    Run,
    Settings,
    file_hash,
    fingerprint,
    footage_file,
    narrated,
    narration_file,
    writing,
)
from ..script import WORDS_PER_SECOND, Script, on_screen, words
from .base import NotReady, Stage, read_script

FILMED = ("omni", "heygen", "import")  # an intro or outro that's a clip of you
CARD_SHORTEST = 2.0  # seconds a card is on screen, at least, in a video without a voice


def heard(path: str) -> str:
    """What a narration file is, by its path."""
    cards = {CARD_NARRATION["intro"]: "the title card's narration", CARD_NARRATION["outro"]: "the end card's narration"}
    return cards.get(path) or f"scene {int(Path(path).stem)}'s narration"


class Assemble(Stage):
    name = "assemble"
    product = "video"
    needs = ("footage", "script", "intro", "narration")
    extra = "assemble"
    where = "pip install 'makable-shorts[assemble]' (Pillow), with ffmpeg"

    def requires(self, settings: Settings) -> tuple[str, ...]:
        drawn = {"intro"} if settings.intro == "card" else set()  # what assemble makes itself, or the video hasn't
        silent = {"narration"} if settings.narrator == "none" else set()
        return tuple(need for need in self.needs if need not in drawn | silent) + (
            ("outro",) if settings.outro in FILMED else ()
        )

    def packages(self, settings: Settings) -> list[str]:
        return ["PIL"] if settings.captions or "card" in (settings.intro, settings.outro) else []

    def inputs(self, run: Run, settings: Settings, script: Script) -> dict[str, Path]:
        """The files the video is made from, by what they are."""
        files = {"the intro": run.path(FILMED_INTRO)} if settings.intro in FILMED else {}
        for name in sorted({scene.footage for scene in script.scenes}):
            files[f"the footage {name!r}"] = run.path(footage_file(name))
        if settings.narrator != "none":
            for path, _ in narrated(script, settings):
                files[heard(path)] = run.path(path)
        if settings.outro in FILMED:
            files["the outro"] = run.path(FILMED_OUTRO)
        if settings.music:
            files["the music"] = run.resolve(settings.music)
        return files

    def plan(self, run: Run) -> dict[str, str]:
        settings, script = run.settings(), read_script(run)
        files = self.inputs(run, settings, script)
        missing = [what for what, path in files.items() if not path.exists()]
        if missing:
            raise NotReady(f"missing {', '.join(missing)}")
        hashes = {what: file_hash(path) for what, path in files.items()}
        # (and for a video with cards, or without a voice, how it's made: a video with neither is named as before)
        silent = settings.narrator == "none"
        kind = (
            (settings.intro, settings.outro, silent, LOOK)
            if silent or "card" in (settings.intro, settings.outro)
            else ()
        )
        source = fingerprint(script.model_dump(), hashes, settings.size, settings.captions, GAP, TAIL, COLOURS, *kind)
        return {FINAL: source, METADATA: source}

    def card(self, run: Run, settings: Settings, text: str, footage: Path, at: float, out: Path, said: str) -> Part:
        """A card: `text` over the frame `at` seconds into `footage`, while the narration file `said` plays, or in a
        video without a voice, for as long as it takes to read."""
        from ..cards import card

        picture = card(text, still(footage, at, out.with_suffix(".still.png")), out, FONT_CACHE, even(settings.size))
        if settings.narrator == "none":
            return Part(picture, whole_frames(max(CARD_SHORTEST, words(text) / WORDS_PER_SECOND + GAP)))
        speech = run.path(said)
        return Part(picture, whole_frames(duration(speech) + GAP), speech, "", speech_span(speech))

    def parts(self, run: Run, settings: Settings, script: Script, work: Path) -> list[Part]:
        """The video's parts, in order. Cards are drawn into `work`."""
        if not script.scenes:
            raise NotReady("the script has no scenes")
        files = self.inputs(run, settings, script)
        silent = settings.narrator == "none"
        if settings.intro == "card":  # over where the recording starts
            first = script.scenes[0]
            footage = run.path(footage_file(first.footage))
            title = work / "title-card.png"
            parts = [
                self.card(run, settings, script.intro_line, footage, first.start or 0.0, title, CARD_NARRATION["intro"])
            ]
        else:
            intro = files["the intro"]
            parts = [Part(intro, whole_frames(duration(intro)), intro, script.intro_line, speech_span(intro))]
        played: dict[str, float] = {}  # how far into each recording the scenes without a stretch got
        for index, scene in enumerate(script.scenes):
            footage = run.path(footage_file(scene.footage))
            tail = TAIL if index == len(script.scenes) - 1 else 0
            if silent:  # read in the captions, all of it at once, across the scene
                part = Part(footage, whole_frames(on_screen(scene, silent) + tail), text=scene.text, whole=True)
            else:
                speech = run.path(narration_file(index))
                length = whole_frames(duration(speech) + GAP + tail)
                part = Part(footage, length, speech, scene.text, speech_span(speech))
            if scene.start is not None and scene.end is not None:
                part.start, part.end = scene.start, min(scene.end, duration(footage))
                if part.end - part.start < 0.1:
                    raise NotReady(f"scene {index + 1}'s stretch ({scene.start}-{scene.end} s) isn't in {footage.name}")
            else:
                part.start = played.get(scene.footage, 0.0) % duration(footage)
                played[scene.footage] = part.start + part.length
            stretch = f"{part.start:5.1f}-{part.end:5.1f} s" if part.end is not None else f"from {part.start:.1f} s"
            print(
                f"Scene {index + 1}: {scene.footage} {stretch} at {part.speed:.2f}x, {part.length:.2f} s: {scene.text}"
            )
            parts.append(part)
        if settings.outro == "card":  # over where the recording ends
            if not script.outro_line.strip():
                raise NotReady("the script has no outro line (outro_line), for the end card")
            last = script.scenes[-1]
            footage = run.path(footage_file(last.footage))
            at = last.end if last.end is not None else duration(footage)
            end = work / "end-card.png"
            parts.append(self.card(run, settings, script.outro_line, footage, at, end, CARD_NARRATION["outro"]))
        elif "the outro" in files:
            outro = files["the outro"]
            parts.append(Part(outro, whole_frames(duration(outro)), outro, script.outro_line, speech_span(outro)))
        return parts

    def make(self, run: Run, paths: list[str]) -> None:
        settings, script = run.settings(), run.script()
        music = run.resolve(settings.music) if settings.music else None
        with tempfile.TemporaryDirectory() as work, writing(run.path(FINAL)) as out:
            parts = self.parts(run, settings, script, Path(work))
            compose(parts, Path(work), out, size=even(settings.size), music=music, captions=settings.captions)
            seconds = duration(out)
        avatar = settings.intro in FILMED or settings.outro in FILMED
        cloned = settings.narrator in (*NARRATOR_MODELS, "import")  # a voice cloned from someone's, or may be
        metadata = {
            "title": script.title,
            "description": script.description,
            # YouTube asks for this when AI makes a real person appear to say something: an avatar of you, or a voice
            # cloned from yours. Kokoro's voices aren't anyone's.
            "containsSyntheticMedia": avatar or cloned,
            "seconds": round(seconds, 2),
        }
        with writing(run.path(METADATA)) as out:
            out.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
        print(f"Made {run.path(FINAL)} ({seconds:.1f} s)")
