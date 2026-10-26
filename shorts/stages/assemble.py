"""assemble: final.mp4 and metadata.json. The intro in your voice, then each scene's stretch of its recording
while its narration plays (sped up or slowed down to fit it), then the outro as filmed, if run.json wants one,
with captions and music, at -14 LUFS.

A scene without a stretch (a script written from what changed, not from steps) plays its recording on from
where the scene before on it stopped. Needs only ffmpeg, and Pillow for the captions.
"""

import json
import tempfile
from pathlib import Path

from ..compose import GAP, TAIL, Part, compose, even, whole_frames
from ..media import duration, speech_span
from ..run import (
    FILMED_INTRO,
    FILMED_OUTRO,
    FINAL,
    INTRO_SPEECH,
    METADATA,
    VOICED_INTRO,
    Run,
    Settings,
    file_hash,
    fingerprint,
    footage_file,
    narration_file,
    writing,
)
from ..script import Script
from .base import NotReady, Stage, read_script


class Assemble(Stage):
    name = "assemble"
    product = "video"
    needs = ("footage", "script", "voiced-intro", "narration")  # or the intro as filmed, in place of voiced-intro
    extra = "assemble"
    where = "pip install 'makable-shorts[assemble]' (Pillow), with ffmpeg"

    def requires(self, settings: Settings) -> tuple[str, ...]:
        needs = self.needs + (("outro",) if settings.outro != "none" else ())
        if settings.intro_voice == "as-filmed":
            return tuple("intro" if need == "voiced-intro" else need for need in needs)
        return needs

    def packages(self, settings: Settings) -> list[str]:
        return ["PIL"] if settings.captions else []

    def inputs(self, run: Run, settings: Settings, script: Script) -> dict[str, Path]:
        """The files the video is made from, by what they are."""
        files = {"the intro": run.path(FILMED_INTRO if settings.intro_voice == "as-filmed" else VOICED_INTRO)}
        if settings.intro_voice == "convert":
            files["the intro's speech"] = run.path(INTRO_SPEECH)
        for name in sorted({scene.footage for scene in script.scenes}):
            files[f"the footage {name!r}"] = run.path(footage_file(name))
        for index in range(len(script.scenes)):
            files[f"scene {index + 1}'s narration"] = run.path(narration_file(index))
        if settings.outro != "none":
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
        source = fingerprint(script.model_dump(), hashes, settings.size, settings.captions, GAP, TAIL)
        return {FINAL: source, METADATA: source}

    def parts(self, run: Run, settings: Settings, script: Script) -> list[Part]:
        files = self.inputs(run, settings, script)
        intro = files["the intro"]
        words = files.get("the intro's speech", intro)
        parts = [Part(intro, whole_frames(duration(intro)), intro, script.intro_line, speech_span(words))]
        played: dict[str, float] = {}  # how far into each recording the scenes without a stretch got
        for index, scene in enumerate(script.scenes):
            footage, speech = run.path(footage_file(scene.footage)), run.path(narration_file(index))
            length = whole_frames(duration(speech) + GAP + (TAIL if index == len(script.scenes) - 1 else 0))
            part = Part(footage, length, speech, scene.text, speech_span(speech))
            if scene.start is not None and scene.end is not None:
                part.start, part.end = scene.start, min(scene.end, duration(footage))
                if part.end - part.start < 0.1:
                    raise NotReady(f"scene {index + 1}'s stretch ({scene.start}-{scene.end} s) isn't in {footage.name}")
            else:
                part.start = played.get(scene.footage, 0.0) % duration(footage)
                played[scene.footage] = part.start + length
            stretch = f"{part.start:5.1f}-{part.end:5.1f} s" if part.end is not None else f"from {part.start:.1f} s"
            print(f"Scene {index + 1}: {scene.footage} {stretch} at {part.speed:.2f}x, {length:.2f} s: {scene.text}")
            parts.append(part)
        if "the outro" in files:
            outro = files["the outro"]
            parts.append(Part(outro, whole_frames(duration(outro)), outro, script.outro_line, speech_span(outro)))
        return parts

    def make(self, run: Run, paths: list[str]) -> None:
        settings, script = run.settings(), run.script()
        parts = self.parts(run, settings, script)
        music = run.resolve(settings.music) if settings.music else None
        with tempfile.TemporaryDirectory() as work, writing(run.path(FINAL)) as out:
            compose(parts, Path(work), out, size=even(settings.size), music=music, captions=settings.captions)
            seconds = duration(out)
        metadata = {
            "title": script.title,
            "description": script.description,
            # YouTube asks for this when AI makes a real person appear to say something.
            "containsSyntheticMedia": True,
            "seconds": round(seconds, 2),
        }
        with writing(run.path(METADATA)) as out:
            out.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
        print(f"Made {run.path(FINAL)} ({seconds:.1f} s)")
