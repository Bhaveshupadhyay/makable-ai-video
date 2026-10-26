"""speak: each scene's narration, narration/01.wav and on, by Chatterbox or OmniVoice here (on a GPU), or by a
text-to-speech API (`narrator` in run.json, with its settings in `narrator_options`).

The narration is in the voice of run.json's `voice` sample, or with `narration_voice` "intro", in the voice of the
person in Omni's intro (voice/avatar.wav, from take-voice). Only the scenes whose spoken text, voice or settings
changed are spoken again.

Where OmniVoice runs comes from the environment, since it's the machine's business, not the video's: OMNIVOICE_ENV
is the folder of its own environment (~/omnivoice-env by default, installed the first time), or "here" for this
Python (OmniVoice installed in it, as in omnivoice_from_script.ipynb). So does which API speaks, with narrator
"api": SHORTS_SPEECH_URL and SHORTS_SPEECH_KEY (`shorts.speech_api`). run.json's `narrator_model` is its model.
"""

import os
from pathlib import Path

from ..run import AVATAR_VOICE, Run, Settings, file_hash, fingerprint, narration_file, writing
from ..voice import OMNIVOICE_ENV, ApiVoice, OmniVoice, Voice
from .base import NotReady, Stage, read_script, voice_sample


def omnivoice_env() -> Path | None:
    value = os.environ.get("OMNIVOICE_ENV", "")
    return None if value == "here" else Path(value).expanduser() if value else OMNIVOICE_ENV


class Speak(Stage):
    name = "speak"
    product = "narration"
    needs = ("script",)
    extra = "voice"
    where = (
        "a GPU: makable_shorts.ipynb, voice_from_script.ipynb or omnivoice_from_script.ipynb in Colab; or with "
        "narrator \"api\", pip install 'makable-shorts[speech]', with SHORTS_SPEECH_URL and SHORTS_SPEECH_KEY"
    )

    def by(self, settings: Settings) -> str:
        return f"speak ({settings.narrator})"

    def requires(self, settings: Settings) -> tuple[str, ...]:
        return self.needs + (("avatar-voice",) if settings.narration_voice == "intro" else ())

    def extra_for(self, settings: Settings) -> str:
        return "speech" if settings.narrator == "api" else self.extra

    def packages(self, settings: Settings) -> list[str]:
        if settings.narrator == "api":
            return ["httpx"]
        if settings.narrator == "omnivoice":
            return ["omnivoice"] if omnivoice_env() is None else []  # its own environment installs itself
        return ["chatterbox", "torchaudio"]

    def sample(self, run: Run, settings: Settings) -> Path:
        """The voice the narration is spoken in."""
        if settings.narration_voice == "sample":
            return voice_sample(run, settings)
        if not run.path(AVATAR_VOICE).exists():
            raise NotReady(f"{AVATAR_VOICE} isn't made yet: python -m shorts take-voice {run.folder}")
        return run.path(AVATAR_VOICE)

    def voice(self, run: Run) -> Voice:
        """The narrator, set up (its model loads, or its voice is cloned, when it first speaks)."""
        settings = run.settings()
        sample, language = self.sample(run, settings), read_script(run).language
        if settings.narrator == "api":
            options = settings.narrator_options
            return ApiVoice(
                sample, language, settings.narrator_model, settings.reference_text, settings.pronounce, **options
            )
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
        refused: tuple[type[Exception], ...] = ()
        if isinstance(voice, ApiVoice):
            from ..speech_api import SpeechAPIError

            refused = (SpeechAPIError,)
        try:
            for index, scene in enumerate(run.script().scenes):
                if narration_file(index) in paths:
                    print(f"Scene {index + 1}: {scene.text}")
                    with writing(run.path(narration_file(index))) as out:
                        voice.say(scene.text, out)
        except refused as error:
            raise NotReady(f"the voice API: {error}") from error
        finally:
            voice.close()
