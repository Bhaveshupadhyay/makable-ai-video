"""speak: each scene's narration, narration/01.wav and on, spoken by a text-to-speech API (`shorts.speech_api`): the
voice API on Modal (services/voice), or ElevenLabs.

It's in the voice of the person in Omni's intro (voice/avatar.wav, from take-voice), or with `narration_voice`
"sample" in run.json, of its `voice` sample. Which API speaks is the machine's business, not the video's, so it
comes from the environment (SHORTS_SPEECH_URL and SHORTS_SPEECH_KEY); run.json's `narrator_model` is its model, and
`narrator_options` its voice settings. Only the scenes whose spoken text, voice or settings changed are spoken again.
"""

from pathlib import Path

from ..run import AVATAR_VOICE, Run, Settings, file_hash, fingerprint, narration_file, writing
from ..voice import ApiVoice
from .base import NotReady, Stage, read_script, voice_sample


class Speak(Stage):
    name = "speak"
    product = "narration"
    needs = ("script",)
    extra = "speech"
    where = "pip install 'makable-shorts[speech]', with SHORTS_SPEECH_URL and SHORTS_SPEECH_KEY (see the README)"

    def by(self, settings: Settings) -> str:
        return f"speak ({settings.narrator_model})"

    def requires(self, settings: Settings) -> tuple[str, ...]:
        return self.needs + (("avatar-voice",) if settings.narration_voice == "intro" else ())

    def packages(self, settings: Settings) -> list[str]:
        return ["httpx"]

    def sample(self, run: Run, settings: Settings) -> Path:
        """The voice the narration is spoken in."""
        if settings.narration_voice == "sample":
            return voice_sample(run, settings)
        if not run.path(AVATAR_VOICE).exists():
            raise NotReady(f"{AVATAR_VOICE} isn't made yet: python -m shorts take-voice {run.folder}")
        return run.path(AVATAR_VOICE)

    def voice(self, run: Run) -> ApiVoice:
        """The narrator, set up: its voice is cloned when it first speaks."""
        settings = run.settings()
        sample, language = self.sample(run, settings), read_script(run).language
        return ApiVoice(
            sample,
            language,
            settings.narrator_model,
            settings.reference_text,
            settings.pronounce,
            **settings.narrator_options,
        )

    def plan(self, run: Run) -> dict[str, str]:
        voice = self.voice(run)
        yours = file_hash(voice.reference)
        return {
            narration_file(index): fingerprint("api", voice.settings, yours, voice.spoken(scene.text))
            for index, scene in enumerate(read_script(run).scenes)
        }

    def make(self, run: Run, paths: list[str]) -> None:
        from ..speech_api import SpeechAPIError

        voice = self.voice(run)
        try:
            for index, scene in enumerate(run.script().scenes):
                if narration_file(index) in paths:
                    print(f"Scene {index + 1}: {scene.text}")
                    with writing(run.path(narration_file(index))) as out:
                        voice.say(scene.text, out)
        except SpeechAPIError as error:
            raise NotReady(f"the voice API: {error}") from error
        finally:
            try:
                voice.close()
            except SpeechAPIError as error:
                print(f"Warning: the voice is still in the API, since it couldn't be deleted: {error}")
