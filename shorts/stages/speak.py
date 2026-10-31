"""speak: each scene's narration, narration/01.wav and on, spoken by a text-to-speech API (`shorts.speech_api`):
ElevenLabs, or the voice API on your own Modal account (services/voice), or by Kokoro on this machine, as run.json's
`narrator` says. In a video without an avatar, it speaks the title card's line and the end card's too
(narration/intro.wav, outro.wav).

An API speaks in the voice of the person in the intro (voice/avatar.wav, from take-voice), or with `narration_voice`
"sample" in run.json, of its `voice` sample. Its key comes from the environment (ELEVENLABS_API_KEY, or
SHORTS_SPEECH_URL and SHORTS_SPEECH_KEY); run.json's `narrator_model` is its model, unless it's the API's own, and
`narrator_options` its voice settings. Kokoro speaks in a voice of its own (`kokoro_voice`), for nothing, with no key.
Only what's said whose text, voice or settings changed is spoken again.
"""

from pathlib import Path

from .. import COMMAND
from ..run import AVATAR_VOICE, CARD_NARRATION, Run, Settings, file_hash, fingerprint, narrated, writing
from ..voice import ApiVoice, KokoroVoice
from .base import NotReady, Stage, read_script, voice_sample

CARDS = {CARD_NARRATION["intro"]: "The title card", CARD_NARRATION["outro"]: "The end card"}


class Speak(Stage):
    name = "speak"
    product = "narration"
    needs = ("script",)
    extra = "speech"
    where = (
        "pip install 'makable-shorts[speech]', with ELEVENLABS_API_KEY, or SHORTS_SPEECH_URL and SHORTS_SPEECH_KEY; "
        "or for Kokoro, 'makable-shorts[kokoro]' (see the README)"
    )

    def by(self, settings: Settings) -> str:
        return f"speak ({settings.narration_model or settings.narrator})"

    def extra_for(self, settings: Settings) -> str:
        return "kokoro" if settings.narrator == "kokoro" else self.extra

    def requires(self, settings: Settings) -> tuple[str, ...]:
        intro = settings.narrator != "kokoro" and settings.narration_voice == "intro" and settings.intro != "card"
        return self.needs + (("avatar-voice",) if intro else ())

    def packages(self, settings: Settings) -> list[str]:
        return ["kokoro", "soundfile"] if settings.narrator == "kokoro" else ["httpx"]

    def sample(self, run: Run, settings: Settings) -> Path:
        """The voice an API speaks the narration in."""
        if settings.narration_voice == "sample":
            return voice_sample(run, settings)
        if settings.intro == "card":
            raise NotReady(
                f"there's no avatar in this video to take its voice from: narrate in yours ({COMMAND} new RUN "
                f"--narration-voice sample, with {COMMAND} me --voice SAMPLE), or with Kokoro (--narrator kokoro)"
            )
        if not run.path(AVATAR_VOICE).exists():
            raise NotReady(f"{AVATAR_VOICE} isn't made yet: {COMMAND} take-voice {run.folder}")
        return run.path(AVATAR_VOICE)

    def voice(self, run: Run) -> ApiVoice | KokoroVoice:
        """The narrator, set up: an API's voice is cloned when it first speaks, and Kokoro loads then."""
        settings = run.settings()
        language = read_script(run).language
        if settings.narrator == "kokoro":
            try:
                return KokoroVoice(settings.kokoro_voice, language, settings.pronounce, **settings.narrator_options)
            except ValueError as problem:
                raise NotReady(f"{problem} (run.json's kokoro_voice)") from problem
        return ApiVoice(
            self.sample(run, settings),
            language,
            settings.narration_model,
            settings.reference_text,
            settings.pronounce,
            narrator=settings.narrator,
            **settings.narrator_options,
        )

    def plan(self, run: Run) -> dict[str, str]:
        voice = self.voice(run)
        if isinstance(voice, KokoroVoice):
            made_with: tuple[str, ...] = (voice.settings,)
        else:
            made_with = ("api", voice.settings, file_hash(voice.reference))
        return {
            path: fingerprint(*made_with, voice.spoken(text))
            for path, text in narrated(read_script(run), run.settings())
        }

    def make(self, run: Run, paths: list[str]) -> None:
        voice = self.voice(run)
        failed: tuple[type[Exception], ...] = ()  # what an API raises when it says no
        if isinstance(voice, ApiVoice):
            from ..speech_api import SpeechAPIError  # httpx, which Kokoro's environment needn't have

            failed = (SpeechAPIError,)
        try:
            for path, text in narrated(run.script(), run.settings()):
                if path in paths:
                    print(f"{CARDS.get(path) or f'Scene {int(Path(path).stem)}'}: {text}")
                    with writing(run.path(path)) as out:
                        voice.say(text, out)
        except failed as error:
            raise NotReady(f"the voice API: {error}") from error
        finally:
            try:
                voice.close()
            except failed as error:
                print(f"Warning: the voice is still in the API, since it couldn't be deleted: {error}")
