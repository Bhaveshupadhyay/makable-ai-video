"""revoice-intro: the intro in your voice. Demucs separates the speech in Omni's clip from its background,
Chatterbox converts the speech to your voice (same words and timing, so the lips still match), and the
background goes back under it, quieter.

With `intro_voice` "as-filmed" in run.json (the voice sample came from the intro, so it's yours already),
there's nothing to do, and the video uses the clip as Omni filmed it.
"""

import shutil
import tempfile
from pathlib import Path

from ..media import ffmpeg
from ..run import FILMED_INTRO, INTRO_SPEECH, VOICED_INTRO, Run, Settings, file_hash, fingerprint, writing
from .base import NotReady, Stage, voice_sample


class RevoiceIntro(Stage):
    name = "revoice-intro"
    product = "voiced-intro"
    needs = ("intro",)
    extra = "voice"
    where = "a GPU: makable_shorts.ipynb or voice_from_script.ipynb in Colab (or pip install 'makable-shorts[voice]')"

    def requires(self, settings: Settings) -> tuple[str, ...]:
        return self.needs if settings.intro_voice == "convert" else ()

    def packages(self, settings: Settings) -> list[str]:
        return [] if settings.intro_voice == "as-filmed" else ["chatterbox", "demucs", "torchaudio"]

    def plan(self, run: Run) -> dict[str, str]:
        settings = run.settings()
        if settings.intro_voice == "as-filmed":
            return {}
        filmed = run.path(FILMED_INTRO)
        if not filmed.exists():
            raise NotReady(f"{FILMED_INTRO} isn't there yet")
        source = fingerprint("convert", file_hash(filmed), file_hash(voice_sample(run, settings)))
        return {VOICED_INTRO: source, INTRO_SPEECH: source}

    def make(self, run: Run, paths: list[str]) -> None:
        from ..voice import Voice, mix_intro_audio, separate_speech

        settings = run.settings()
        filmed = run.path(FILMED_INTRO)
        voice = Voice(voice_sample(run, settings), settings.language)
        with tempfile.TemporaryDirectory() as work:
            print("Separating the intro's speech from its background (Demucs)")
            speech, background = separate_speech(filmed, Path(work))
            print("Converting the speech to your voice (Chatterbox)")
            converted = voice.convert(speech, Path(work) / "speech.wav")
            audio = mix_intro_audio(converted, background, Path(work) / "audio.wav")
            with writing(run.path(INTRO_SPEECH)) as out:
                shutil.copyfile(converted, out)
            with writing(run.path(VOICED_INTRO)) as out:
                ffmpeg(
                    "-i", filmed, "-i", audio, "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-shortest", out,
                )  # fmt: skip
