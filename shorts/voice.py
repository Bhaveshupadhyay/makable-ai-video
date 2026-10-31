"""The narrator's voice: a text-to-speech API speaks each scene (`ApiVoice`), in a voice cloned from a sample, or
Kokoro does, on this machine, in a voice of its own (`KokoroVoice`).

The API is ElevenLabs, or the voice API on your own Modal account (services/voice, with OmniVoice and Chatterbox
on GPUs: `speech_api`), so nothing here needs a GPU. The sample is the avatar's voice, taken from the intro
(`voice_sample`), or a recording of you. Kokoro is a small open model (82M parameters, Apache-2.0) that speaks on the
CPU, about as fast as it talks, and costs nothing: it needs the `kokoro` extra.
"""

import re
import shutil
import tempfile
from pathlib import Path

from .media import ffmpeg


def voice_sample(recording: Path, out: Path, *, start: float = 0.0, length: float = 20.0) -> Path:
    """Makes a voice sample from a recording of someone talking (a video works).

    Its sound in mono, from `start` seconds in, without the silence before the talking starts, and at most
    `length` seconds of it: OmniVoice clones best from 3 to 10.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg(
        "-ss", f"{start:.3f}", "-i", recording, "-vn",
        "-af", "silenceremove=start_periods=1:start_threshold=-40dB",
        "-t", f"{length:.3f}", "-ac", "1", out,
    )  # fmt: skip
    return out


def respelled(text: str, pronounce: dict[str, str]) -> str:
    """`text` as a model reads it: the words in `pronounce` respelled, keeping a capital letter."""
    for word, said in pronounce.items():
        text = re.sub(
            rf"\b{re.escape(word)}\b",
            lambda match, said=said: said[:1].upper() + said[1:] if match[0][0].isupper() else said,
            text,
            flags=re.IGNORECASE,
        )
    return text


class ApiVoice:
    """The narrator: a text-to-speech API, ElevenLabs' or one with its shape, such as ours on Modal (`speech_api`,
    set up from the environment). The voice is cloned there from the sample when the first scene is spoken, and
    deleted by `close`, since each video's avatar voice is a new one (and ElevenLabs caps how many voices an account
    keeps).

    What it speaks is named by the model, the language, the transcript and the settings, not by the API's URL: so a
    machine without the URL can tell what's up to date, and switching APIs means switching models anyway.
    """

    def __init__(
        self,
        reference: Path,
        language: str = "en",
        model: str = "omnivoice",
        transcript: str | None = None,
        pronounce: dict[str, str] | None = None,
        api=None,
        narrator: str = "modal",
        **settings: float | bool | str,
    ) -> None:
        """
        Args:
            reference: The voice sample: 3 to 10 seconds for OmniVoice.
            language: What it speaks: sent as the voice's "language" label, which ElevenLabs takes too (unlike
                `language_code`, which most of its models refuse) and our API speaks in.
            model: The API's model: "omnivoice" or "chatterbox" on ours, ElevenLabs' own on theirs.
            transcript: What's said in the sample, for OmniVoice (None: Whisper hears it, on the API's side).
            pronounce: Words the model says wrong, spelled the way they're said, such as a product's name:
                {"nginx": "engine x"}. Only what it reads changes, not the captions.
            api: A `speech_api.SpeechAPI`; by default, the narrator's (`SpeechAPI.from_environment`), when the first
                scene is spoken.
            narrator: Whose API it is, by default: "elevenlabs", or "modal" (yours).
            settings: The API's `voice_settings`, as it takes them: OmniVoice's `speed`, ElevenLabs' `stability`.
        """
        self.reference = Path(reference)
        self.language = language
        self.model = model
        self.transcript = transcript
        self.pronounce = pronounce or {}
        self.tts_options = settings
        self.api = api
        self.narrator = narrator
        self.voice_id: str | None = None

    @property
    def settings(self) -> str:
        """The model, the language, the transcript and the settings, for naming what's spoken with them."""
        return repr(("api", self.model, self.language, self.transcript, sorted(self.tts_options.items())))

    def spoken(self, text: str) -> str:
        """`text` as the model reads it: the words in `pronounce` respelled, keeping a capital letter."""
        return respelled(text, self.pronounce)

    def say(self, text: str, out: Path) -> Path:
        """Speaks `text` in the sample's voice, through the API, and saves it as WAV."""
        if self.api is None:
            from .speech_api import SpeechAPI

            self.api = SpeechAPI.from_environment(self.narrator)
        if self.voice_id is None:
            name = f"makable-shorts {self.reference.stem}"
            self.voice_id = self.api.add_voice(name, self.reference, self.transcript, self.language)
        mp3 = self.api.speak(self.voice_id, self.spoken(text), self.model, settings=self.tts_options)
        with tempfile.TemporaryDirectory() as work:
            speech = Path(work) / "speech.mp3"
            speech.write_bytes(mp3)
            ffmpeg("-i", speech, "-ac", "1", out)
        return out

    def close(self) -> None:
        """Deletes the voice from the API."""
        if self.api is not None and self.voice_id is not None:
            self.api.delete_voice(self.voice_id)
            self.voice_id = None


KOKORO = "hexgrad/Kokoro-82M"  # its weights, on Hugging Face: downloaded once, the first time it speaks
KOKORO_VOICES = {"en": "af_heart", "hi": "hf_alpha"}  # its voice for each language, unless run.json names another
# What each of its voices speaks, by the voice's first letter: af_heart is American English, bm_george British
# English, hm_omega Hindi. Its other languages aren't ones a script is written in.
KOKORO_LANGUAGES = {"a": "en", "b": "en", "h": "hi"}
KOKORO_RATE = 24000  # samples a second
ESPEAK_PATH = 150  # bytes: espeak-ng keeps its data folder's path in 160, with a file's name after it


class KokoroVoice:
    """The narrator: Kokoro, on this machine's CPU, in one of its own voices (it can't clone yours). Free: the model
    downloads once (about 330 MB), and a minute of narration takes about a minute to speak.

    What it speaks is named by the voice and its settings, as `ApiVoice`'s is by its model.
    """

    def __init__(
        self, voice: str | None = None, language: str = "en", pronounce: dict[str, str] | None = None, **settings: float
    ) -> None:
        """
        Args:
            voice: One of Kokoro's voices for `language`, such as "am_michael" (None: KOKORO_VOICES').
            language: What it speaks: one of KOKORO_LANGUAGES'.
            pronounce: Words it says wrong, spelled the way they're said, as for `ApiVoice`.
            settings: Its pipeline's options: `speed` (1 by default).

        Raises:
            ValueError: The voice isn't one of Kokoro's for the language.
        """
        self.voice = voice or KOKORO_VOICES.get(language, "")
        speaks = KOKORO_LANGUAGES.get(self.voice[:1])
        if speaks != language:
            yours = ", ".join(f"{name} ({code})" for code, name in KOKORO_VOICES.items())
            said = f"speaks {speaks}" if speaks else "isn't one of its voices for en or hi"
            raise ValueError(f"Kokoro's voice {self.voice!r} {said}, and the script is in {language}: {yours}, say")
        self.language = language
        self.pronounce = pronounce or {}
        self.tts_options = settings
        self.pipeline = None

    @property
    def settings(self) -> str:
        """The voice and the settings, for naming what's spoken with them."""
        return repr(("kokoro", self.voice, sorted(self.tts_options.items())))

    def spoken(self, text: str) -> str:
        return respelled(text, self.pronounce)

    def say(self, text: str, out: Path) -> Path:
        """Speaks `text` in its voice, and saves it as WAV."""
        import numpy
        import soundfile

        if self.pipeline is None:
            from kokoro import KPipeline

            espeak_data()
            self.pipeline = KPipeline(lang_code=self.voice[0], repo_id=KOKORO)
        said = [
            numpy.asarray(audio)
            for _, _, audio in self.pipeline(self.spoken(text), voice=self.voice, **self.tts_options)
        ]
        soundfile.write(out, numpy.concatenate(said), KOKORO_RATE)
        return out

    def close(self) -> None:
        """Nothing to let go of: the model is on this machine."""


def espeak_data() -> None:
    """Points espeak-ng, which Kokoro reads some words with (and Hindi), at its data: the copy that comes with it, or
    when that's in folders too deep for espeak-ng to find it (`ESPEAK_PATH`), a copy in the temp folder. espeak-ng
    looks for a path that's too long in the folder it was built in instead, and quits."""
    import espeakng_loader
    from phonemizer.backend.espeak.wrapper import EspeakWrapper

    data = Path(espeakng_loader.get_data_path())
    if len(str(data).encode()) > ESPEAK_PATH:
        copy = Path(tempfile.gettempdir()) / "makable-shorts-espeak-ng-data"
        if not (copy / "phontab").exists():
            part = copy.with_name(f".{copy.name}.part")  # first, so a copy that fails isn't taken for one
            shutil.rmtree(part, ignore_errors=True)
            shutil.copytree(data, part)
            shutil.rmtree(copy, ignore_errors=True)
            part.rename(copy)
        data = copy
    EspeakWrapper.set_data_path(str(data))
