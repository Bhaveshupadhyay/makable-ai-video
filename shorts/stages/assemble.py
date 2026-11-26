"""assemble: final.mp4 and metadata.json. The intro as filmed, then each scene's stretch of its recording while its
narration plays (sped up or slowed down to fit it), then the outro as filmed, if run.json wants one, with captions
and music, at -14 LUFS.

A video without an avatar opens on a title card instead (intro "card"): a blurred still of the recording
(`shorts.cards`), while the narrator says the intro line, which the captions show as it's said. It ends on an end
card with the outro line. With captions off, the card shows the line itself, in big letters. A video without a voice
(narrator "none") shows the line on the card, plays each scene's stretch at its own speed, or slower if its words take
longer to read, while the captions say them, and holds each card for as long as it takes to read.

A scene without a stretch plays its recording on from where the scene before on it stopped. Needs only ffmpeg, and
Pillow for the captions and the cards.
metadata.json keeps where each part is in the video (`timeline`), to see where viewers left it once it's posted.
"""

import contextlib
import io
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..cards import LOOK
from ..compose import CAPTION_PLACES, COLOURS, FONT_CACHE, GAP, TAIL, Part, compose, even, whole_frames
from ..media import duration, speech_span, still
from ..run import (
    CARD_NARRATION,
    FILMED_INTRO,
    FILMED_OUTRO,
    FINAL,
    METADATA,
    NARRATOR_MODELS,
    PICKS,
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
from ..tags import found, without
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
        drawn = {"intro"} if settings.intro in ("card", "none") else set()  # what assemble makes, or the video hasn't
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
        if settings.subscribe:
            files["the subscribe animation"] = run.resolve(settings.subscribe)
        return files

    def plan(self, run: Run) -> dict[str, str]:
        settings, script = run.settings(), read_script(run)
        files = self.inputs(run, settings, script)
        if settings.narrator == "none" and not settings.captions:
            raise NotReady(
                "a video without a voice says what's happening in its captions, and run.json turns them off: turn them "
                "on (new RUN --captions), or give it a narrator"
            )
        missing = [what for what, path in files.items() if not path.exists()]
        if missing:
            raise NotReady(f"missing {', '.join(missing)}")
        hashes = {what: file_hash(path) for what, path in files.items()}
        # (and for a video with cards, or without a voice, how it's made: a video with neither is named as before)
        silent = settings.narrator == "none"
        kind = (
            (settings.intro, settings.outro, silent, LOOK)
            if silent or "card" in (settings.intro, settings.outro) or settings.intro == "none"
            else ()
        )
        # (and for a script with tags, that the captions leave them out: so a video made before they did is made again)
        said = [script.intro_line, script.outro_line, *(scene.text for scene in script.scenes)]
        tagged = ("captions without tags",) if any(found(text) for text in said) else ()
        # (and an animated Short's kind, which metadata.json notes: a demo's is named as before)
        tagged += (("kind", settings.kind),) if settings.kind != "demo" else ()
        # (and for captions low in the frame, or clips heard under the narration: so a video with neither keeps its name)
        tagged += (
            (("captions_at", settings.captions_at),) if settings.captions and settings.captions_at != "middle" else ()
        )
        tagged += tuple(sorted(self.effects(run, settings).items()))
        # (and the music's volumes, when there's music)
        tagged += (("music", settings.music_volume, settings.music_ending_volume),) if settings.music else ()
        source = fingerprint(
            script.model_dump(), hashes, settings.size, settings.captions, GAP, TAIL, COLOURS, *kind, *tagged
        )
        return {FINAL: source, METADATA: source}

    def card(self, run: Run, settings: Settings, text: str, footage: Path, at: float, out: Path, said: str) -> Part:
        """A card: `text` over the frame `at` seconds into `footage`, while the narration file `said` plays, or in a
        video without a voice, for as long as it takes to read."""
        from ..cards import card

        frame = still(footage, at, out.with_suffix(".still.png"))
        text = without(text)  # the narrator performs the tags: the card and the captions show only the words
        if settings.narrator == "none":
            picture = card(text, frame, out, FONT_CACHE, even(settings.size))
            return Part(picture, whole_frames(max(CARD_SHORTEST, words(text) / WORDS_PER_SECOND + GAP)))
        # Narrated: the card is the blurred still alone, and the line comes in the captions, a few words at a time
        # as it's said, rather than all of it at once on the card.
        picture = card("" if settings.captions else text, frame, out, FONT_CACHE, even(settings.size))
        speech = run.path(said)
        return Part(picture, whole_frames(duration(speech) + GAP), speech, text, speech_span(speech))

    @staticmethod
    def effects(run: Run, settings: Settings) -> dict[str, float]:
        """How loud each animated shot's own sound is under the narration, by footage name: run.json's effects, for
        a clip made by an animator whose clips carry sound effects (picks.json says whose each is). Footage you
        brought in keeps quiet: it may have speech or music of its own."""
        file = run.path(PICKS)
        if settings.kind != "animated" or settings.effects <= 0 or not file.exists():
            return {}
        from ..animators import ANIMATORS

        picks = json.loads(file.read_text())  # a take is named by its animator first: "h3-720", "omni-1.2-2"
        return {
            shot: settings.effects
            for shot, name in picks.items()
            if shot not in settings.footage  # brought in, so not the animator's any more
            and (animator := ANIMATORS.get(name.split("-")[0])) is not None
            and animator.sound
        }

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
        elif settings.intro in FILMED:
            intro = files["the intro"]
            parts = [Part(intro, whole_frames(duration(intro)), intro, without(script.intro_line), speech_span(intro))]
        else:  # no intro: it opens on the first scene
            parts = []
        played: dict[str, float] = {}  # how far into each recording the scenes without a stretch got
        heard = self.effects(run, settings)
        for index, scene in enumerate(script.scenes):
            footage = run.path(footage_file(scene.footage))
            tail = TAIL if index == len(script.scenes) - 1 else 0
            if silent:  # read in the captions, all of it at once, across the scene
                part = Part(
                    footage,
                    whole_frames(on_screen(scene, silent) + tail),
                    text=without(scene.caption or scene.text),
                    whole=True,
                )
            else:
                speech = run.path(narration_file(index))
                length = whole_frames(duration(speech) + GAP + tail)
                part = Part(
                    footage, length, speech, without(scene.caption or scene.text), speech_span(speech)
                )  # words alone
            if scene.start is not None and scene.end is not None:
                part.start, part.end = scene.start, min(scene.end, duration(footage))
                if part.end - part.start < 0.1:
                    raise NotReady(f"scene {index + 1}'s stretch ({scene.start}-{scene.end} s) isn't in {footage.name}")
            else:
                part.start = played.get(scene.footage, 0.0) % duration(footage)
                played[scene.footage] = part.start + part.length
            part.effects = heard.get(scene.footage, 0.0)
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
            outro_line = without(script.outro_line)
            parts.append(Part(outro, whole_frames(duration(outro)), outro, outro_line, speech_span(outro)))
        return parts

    def make(self, run: Run, paths: list[str]) -> None:
        settings, script = run.settings(), run.script()
        music = run.resolve(settings.music) if settings.music else None
        with tempfile.TemporaryDirectory() as work, writing(run.path(FINAL)) as out:
            parts = self.parts(run, settings, script, Path(work))
            # the last scene, where the narration asks them to follow: the subscribe animation is over it, and the
            # music goes quieter under it
            ending = 1 if settings.outro == "card" or settings.outro in FILMED else 0
            at = sum(part.length for part in parts[: len(parts) - ending - 1])
            subscribe = (run.resolve(settings.subscribe), at) if settings.subscribe else None
            compose(
                parts,
                Path(work),
                out,
                size=even(settings.size),
                music=music,
                music_volume=settings.music_volume,
                music_ending=(settings.music_ending_volume, at),
                captions=settings.captions,
                captions_at=CAPTION_PLACES[settings.captions_at],
                subscribe=subscribe,
            )
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
            "kind": settings.kind,  # for the insights to compare demos with animated Shorts
            **({"hook": script.hook} if script.hook else {}),
            "parts": timeline(parts, script, settings),
        }
        with writing(run.path(METADATA)) as out:
            out.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
        print(f"Made {run.path(FINAL)} ({seconds:.1f} s)")


def timeline(parts: list[Part], script: Script, settings: Settings) -> list[dict[str, Any]]:
    """Where each part is in the video, in seconds, and what's said in it: the intro (a filmed one or a title card),
    scene 1, ..., the outro (or the end card). An animated Short has only its scenes."""
    intro = ["intro"] if settings.intro == "card" or settings.intro in FILMED else []
    names = [*intro, *(f"scene {number}" for number in range(1, len(script.scenes) + 1))]
    names += ["outro"] * (len(parts) - len(names))
    found, at = [], 0.0
    for name, part in zip(names, parts, strict=True):
        found.append({"part": name, "start": round(at, 2), "end": round(at + part.length, 2), "said": part.text})
        at += part.length
    return found


def made_timeline(run: Run) -> list[dict[str, Any]] | None:
    """The finished video's parts (`timeline`): as metadata.json keeps them, or worked out again from the files it was
    made from, for a video assembled before it kept them. None, without them, or when the script, the settings or
    the files have changed since the video was made: their parts wouldn't be the video's."""
    metadata = run.path(METADATA)
    kept = json.loads(metadata.read_text()) if metadata.exists() else {}
    if "parts" in kept:
        return kept["parts"]
    final = run.path(FINAL)
    made = run.record(Assemble.product).files.get(FINAL)
    if not final.exists() or made is None or made.sha256 != file_hash(final):
        return None
    try:
        if Assemble().plan(run)[FINAL] != made.source:
            return None
        # parts says what it plays, for assemble, and draws the cards: into a folder that's thrown away
        with contextlib.redirect_stdout(io.StringIO()), tempfile.TemporaryDirectory() as work:
            settings, script = run.settings(), run.script()
            return timeline(Assemble().parts(run, settings, script, Path(work)), script, settings)
    except (OSError, ValueError, NotReady, subprocess.CalledProcessError):
        return None
