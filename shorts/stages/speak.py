"""speak: each scene's narration in your voice, narration/01.wav and on, by Chatterbox or OmniVoice (`narrator`
in run.json, with its settings in `narrator_options`).

Only the scenes whose spoken text, voice sample or settings changed are spoken again. Where OmniVoice runs
comes from the environment, since it's the machine's business, not the video's: OMNIVOICE_ENV is the folder
of its own environment (~/omnivoice-env by default, installed the first time), or "here" for this Python
(OmniVoice installed in it, as in omnivoice_from_script.ipynb).
"""

import os
from pathlib import Path

from ..run import Run, Settings, file_hash, fingerprint, narration_file, writing
from ..voice import OMNIVOICE_ENV, OmniVoice, Voice
from .base import Stage, read_script, voice_sample


def omnivoice_env() -> Path | None:
    value = os.environ.get("OMNIVOICE_ENV", "")
    return None if value == "here" else Path(value).expanduser() if value else OMNIVOICE_ENV


class Speak(Stage):
    name = "speak"
    product = "narration"
    needs = ("script",)
    extra = "voice"
    where = "a GPU: makable_shorts.ipynb, voice_from_script.ipynb or omnivoice_from_script.ipynb in Colab"

    def by(self, settings: Settings) -> str:
        return f"speak ({settings.narrator})"

    def packages(self, settings: Settings) -> list[str]:
        if settings.narrator == "omnivoice":
            return ["omnivoice"] if omnivoice_env() is None else []  # its own environment installs itself
        return ["chatterbox", "torchaudio"]

    def voice(self, run: Run) -> Voice:
        """The narrator, set up (its model loads when it first speaks)."""
        settings = run.settings()
        sample, language = voice_sample(run, settings), read_script(run).language
        options = {"pronounce": settings.pronounce, **settings.narrator_options}
        if settings.narrator == "omnivoice":
            return OmniVoice(sample, language, settings.reference_text, env=omnivoice_env(), **options)
        return Voice(sample, language, **options)

    def plan(self, run: Run) -> dict[str, str]:
        settings = run.settings()
        voice = self.voice(run)
        yours = file_hash(voice.reference)
        return {
            narration_file(index): fingerprint(settings.narrator, voice.settings, yours, voice.spoken(scene.text))
            for index, scene in enumerate(read_script(run).scenes)
        }

    def make(self, run: Run, paths: list[str]) -> None:
        voice = self.voice(run)
        for index, scene in enumerate(run.script().scenes):
            if narration_file(index) in paths:
                print(f"Scene {index + 1}: {scene.text}")
                with writing(run.path(narration_file(index))) as out:
                    voice.say(scene.text, out)
