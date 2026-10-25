"""The voices: every voice in the video becomes yours, from one recording of you.

The intro's speech is converted (same words and timing, so the lips still match) and the narration
is spoken by Chatterbox. Both take the voice from the same file, so they sound like one person.
`OmniVoice` speaks the narration with OmniVoice instead, in an environment of its own.
"""

import functools
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .media import ffmpeg

# Words Chatterbox says wrong, by language, spelled the way they're said. Only what it reads changes, not the
# captions. English "makeable" was picked by ear from the voice notebook's tries (section 2). Hindi scripts keep
# makable in Latin letters, so it's read the way a Hindi speaker would write it.
PRONOUNCE = {"en": {"makable": "makeable"}, "hi": {"makable": "मेकेबल"}}
# How the narration is said: livelier than Chatterbox's default (0.5 and 0.5), as its tips suggest for expressive
# speech. More exaggeration is more feeling (and faster); less cfg_weight slows it back down. "lively", picked by
# ear from the voice notebook's tries (section 2).
DELIVERY = {"exaggeration": 0.7, "cfg_weight": 0.3}
# Where `install_omnivoice` puts OmniVoice: chatterbox-tts pins transformers 5.2, and OmniVoice needs 5.3 or newer.
OMNIVOICE_ENV = Path.home() / "omnivoice-env"


@functools.cache
def _tts(device: str, multilingual: bool):
    if multilingual:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        return ChatterboxMultilingualTTS.from_pretrained(device=device)
    from chatterbox.tts import ChatterboxTTS

    return ChatterboxTTS.from_pretrained(device=device)


@functools.cache
def _vc(device: str):
    from chatterbox.vc import ChatterboxVC

    return ChatterboxVC.from_pretrained(device)


@functools.cache
def _omnivoice_here(device: str | None):
    """OmniVoice in this Python, loaded once."""
    from .omnivoice_worker import Speaker

    return Speaker(device)


@functools.cache
def _omnivoice(env: Path, device: str | None) -> tuple[subprocess.Popen, Path]:
    """OmniVoice's worker (omnivoice_worker.py), started once and kept for every scene, and its log."""
    install_omnivoice(env)
    log = Path(tempfile.gettempdir()) / "omnivoice.log"
    command = [env / "bin" / "python", "-I", Path(__file__).with_name("omnivoice_worker.py"), *filter(None, [device])]
    with log.open("w") as stderr:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, text=True)
    return process, log


def install_omnivoice(env: Path = OMNIVOICE_ENV) -> None:
    """Installs OmniVoice in an environment of its own, with uv: a few minutes the first time, then a moment's check."""
    if not shutil.which("uv"):
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
    python = env / "bin" / "python"
    if not python.exists():
        subprocess.run(["uv", "venv", "--quiet", "--python", "3.12", str(env)], check=True)
    # The CUDA 12.6 build with an NVIDIA GPU (Colab's T4), else the CPU one, which is far smaller.
    build = "cu126" if shutil.which("nvidia-smi") else "cpu"
    install = ["uv", "pip", "install", "--quiet", "--python", str(python)]
    subprocess.run(
        [*install, "torch==2.8.0", "torchaudio==2.8.0", "--index-url", f"https://download.pytorch.org/whl/{build}"],
        check=True,
    )
    # OmniVoice uses transformers' internals: the transformers of its release, not whatever came out since.
    subprocess.run([*install, "omnivoice==0.2.1", "transformers==5.14.1"], check=True)


def best_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def voice_sample(recording: Path, out: Path, *, start: float = 0.0, length: float = 20.0) -> Path:
    """Makes the voice sample `Voice` takes from a recording of you talking (a video works).

    Its sound in mono, from `start` seconds in, without the silence before you start talking, and at most
    `length` seconds of it: Chatterbox takes the voice from the first 10 seconds or so.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg(
        "-ss", f"{start:.3f}", "-i", recording, "-vn",
        "-af", "silenceremove=start_periods=1:start_threshold=-40dB",
        "-t", f"{length:.3f}", "-ac", "1", out,
    )  # fmt: skip
    return out


def separate_speech(video: Path, workdir: Path) -> tuple[Path, Path]:
    """Splits a clip's sound into the speech and everything else, with Demucs.

    Returns:
        The speech and the background, as WAV files in `workdir`.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    audio = workdir / f"{video.stem}.wav"
    ffmpeg("-i", video, "-vn", "-ac", "2", "-ar", "44100", audio)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "demucs.separate",
            "--two-stems=vocals",
            "-n",
            "htdemucs",
            "-o",
            str(workdir),
            str(audio),
        ],
        check=True,
    )
    stems = workdir / "htdemucs" / audio.stem
    return stems / "vocals.wav", stems / "no_vocals.wav"


class Voice:
    """Chatterbox's voice cloning (text to speech) and conversion (speech to speech), in your voice.

    It speaks one language: English with Chatterbox's English model, others ("hi" for Hindi) with its
    multilingual one. The models load on first use, which takes a while, and every Voice shares them, so
    trying several deliveries loads them once.
    """

    def __init__(
        self,
        reference: Path,
        language: str = "en",
        device: str | None = None,
        pronounce: dict[str, str] | None = None,
        **tts_options: float,
    ) -> None:
        """
        Args:
            reference: 10 to 20 seconds of you talking, clean, no music.
            language: What it speaks, as Chatterbox's language code: "en", "hi", ...
            device: "cuda", "mps" or "cpu"; the fastest available by default.
            pronounce: Words to respell for Chatterbox, e.g. {"makable": "make-a-bull"}; the language's
                `PRONOUNCE` by default.
            tts_options: Passed to Chatterbox's `generate`, over `DELIVERY`: e.g. `exaggeration=0.9`. For a
                voice sample in another language than `language`, `cfg_weight=0` carries less of its accent over.
        """
        self.reference = Path(reference)
        self.language = language
        self.device = device
        self.pronounce = PRONOUNCE.get(language, {}) if pronounce is None else pronounce
        self.tts_options = {**DELIVERY, **tts_options}

    @property
    def settings(self) -> str:
        """The language and Chatterbox's settings, for naming what's spoken with them."""
        return repr((self.language, sorted(self.tts_options.items())))

    @property
    def tts(self):
        return _tts(self.device or best_device(), self.language != "en")

    @property
    def vc(self):
        return _vc(self.device or best_device())

    def spoken(self, text: str) -> str:
        """`text` as Chatterbox reads it: the words in `pronounce` respelled, keeping a capital letter."""
        for word, said in self.pronounce.items():
            text = re.sub(
                rf"\b{re.escape(word)}\b",
                lambda match, said=said: said[:1].upper() + said[1:] if match[0][0].isupper() else said,
                text,
                flags=re.IGNORECASE,
            )
        return text

    def say(self, text: str, out: Path) -> Path:
        """Speaks `text` in your voice."""
        import torchaudio

        options = self.tts_options if self.language == "en" else {**self.tts_options, "language_id": self.language}
        wav = self.tts.generate(self.spoken(text), audio_prompt_path=str(self.reference), **options)
        torchaudio.save(str(out), wav, self.tts.sr)
        return out

    def convert(self, speech: Path, out: Path) -> Path:
        """Re-voices a recording of speech in your voice, keeping its words and timing."""
        import torchaudio

        wav = self.vc.generate(audio=str(speech), target_voice_path=str(self.reference))
        torchaudio.save(str(out), wav, self.vc.sr)
        return out


class OmniVoice(Voice):
    """A Voice whose narration OmniVoice speaks, from the same voice sample; Chatterbox still converts the intro,
    since OmniVoice only speaks text.

    With `env=None`, OmniVoice runs in this Python (installed here, as in the OmniVoice notebook, which has no
    Chatterbox). Otherwise it runs in an environment of its own, which the first scene to speak installs (a few
    minutes), in a process started then (it loads the model, and downloads it the first time) and kept for the
    rest. Both name what they speak the same way, so scenes spoken in the OmniVoice notebook are used as they are.

    Two models can make one sample sound like two people, so listen to the intro and the first scene together.
    It speaks Hindi too, but learned it from far less speech than English (117 hours to 206,000).
    """

    def __init__(
        self,
        reference: Path,
        language: str = "en",
        reference_text: str | None = None,
        device: str | None = None,
        pronounce: dict[str, str] | None = None,
        env: Path | None = OMNIVOICE_ENV,
        **tts_options: float,
    ) -> None:
        """
        Args:
            reference: 3 to 10 seconds of you talking, clean: OmniVoice clones worse from longer samples
                (`voice_sample(recording, out, length=10)` makes one).
            language: What it speaks, as OmniVoice's language id: "en", "hi", ...
            reference_text: What's said in `reference`; Whisper writes it down when it's not given.
            device: "cuda", "mps" or "cpu", for OmniVoice and Chatterbox; the fastest available by default.
            pronounce: Words to respell, as for Voice; the language's `PRONOUNCE` (picked for Chatterbox) by default.
            env: OmniVoice's own environment (`install_omnivoice`); None: OmniVoice is installed in this Python.
            tts_options: Passed to OmniVoice's `generate`: e.g. `speed=1.1`, or `num_step=16` (faster, a little
                worse). Chatterbox's `DELIVERY` doesn't apply.
        """
        super().__init__(reference, language, device, pronounce)
        self.reference_text = reference_text
        self.env = env if env is None else Path(env)
        self.tts_options = tts_options

    @property
    def settings(self) -> str:
        """OmniVoice's settings, for naming what's spoken with them."""
        return repr(("OmniVoice", self.language, self.reference_text, sorted(self.tts_options.items())))

    def say(self, text: str, out: Path) -> Path:
        """Speaks `text` in your voice, with OmniVoice."""
        request = {
            "text": self.spoken(text),
            "reference": str(self.reference.resolve()),
            "reference_text": self.reference_text,
            "language": self.language,
            "options": self.tts_options,
            "out": str(Path(out).resolve()),
        }
        if self.env is None:
            _omnivoice_here(self.device).say(request)
            return out
        process, log = _omnivoice(self.env, self.device)
        try:
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            answer = process.stdout.readline()
        except BrokenPipeError:
            answer = ""
        if not answer:
            _omnivoice.cache_clear()  # so the next scene starts it again
            raise RuntimeError(f"OmniVoice stopped. The end of its log ({log}):\n{log.read_text()[-3000:]}")
        error = json.loads(answer).get("error")
        if error:
            raise RuntimeError(f"OmniVoice couldn't say {text!r}:\n{error}")
        return out


def mix_intro_audio(speech: Path, background: Path, out: Path, background_volume: float = 0.3) -> Path:
    """Puts the clip's own background sound (quieter) back under the converted speech."""
    ffmpeg(
        "-i", speech, "-i", background,
        "-filter_complex",
        f"[0:a]aresample=48000,aformat=channel_layouts=stereo[s];"
        f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={background_volume}[b];"
        "[s][b]amix=inputs=2:duration=longest:normalize=0",
        out,
    )  # fmt: skip
    return out
