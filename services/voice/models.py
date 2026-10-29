"""The models behind the voice API, each loaded once in a GPU container of its own (app.py): text to speech in the
voice of a sample, by OmniVoice or Chatterbox.

The two can't share an environment (Chatterbox pins an older transformers), so each imports its packages only
when it's made. Neither respells words: the client does (`shorts.voice.PRONOUNCE`).
"""

import hashlib
from pathlib import Path
from typing import Any

OMNIVOICE = "k2-fsa/OmniVoice"
# How Chatterbox says it: livelier than its default (0.5 and 0.5), as its tips suggest for expressive speech. More
# exaggeration is more feeling (and faster); less cfg_weight slows it back down. Picked by ear.
DELIVERY = {"exaggeration": 0.7, "cfg_weight": 0.3}


class OmniVoiceModel:
    """OmniVoice, loaded once, and the voice it took from each sample (with what's said in it), to reuse."""

    def __init__(self, device: str = "cuda") -> None:
        import omnivoice
        import torch

        dtype = torch.float16 if device == "cuda" else torch.float32
        self.model = omnivoice.OmniVoice.from_pretrained(OMNIVOICE, device_map=device, dtype=dtype)
        self.voices: dict[tuple[str, str | None], Any] = {}

    def say(self, text: str, sample: Path, transcript: str | None, language: str, settings: dict, out: Path) -> None:
        """Speaks `text` in the voice of `sample` into `out`, as WAV. Without a transcript, Whisper hears the sample.
        `settings` go to OmniVoice's generate: `speed`, `num_step`, ..."""
        import soundfile

        voice = hashlib.sha256(sample.read_bytes()).hexdigest(), transcript
        if voice not in self.voices:
            self.voices[voice] = self.model.create_voice_clone_prompt(str(sample), transcript)
        [audio] = self.model.generate(text=text, language=language, voice_clone_prompt=self.voices[voice], **settings)
        soundfile.write(str(out), audio, self.model.sampling_rate)


class ChatterboxModel:
    """Chatterbox: its English model, and its multilingual one for other languages ("hi"), each loaded when first
    needed."""

    def __init__(self, device: str = "cuda") -> None:
        self.device = device
        self.models: dict[bool, Any] = {}

    def model(self, multilingual: bool) -> Any:
        if multilingual not in self.models:
            if multilingual:
                from chatterbox.mtl_tts import ChatterboxMultilingualTTS

                self.models[multilingual] = ChatterboxMultilingualTTS.from_pretrained(device=self.device)
            else:
                from chatterbox.tts import ChatterboxTTS

                self.models[multilingual] = ChatterboxTTS.from_pretrained(device=self.device)
        return self.models[multilingual]

    def say(self, text: str, sample: Path, transcript: str | None, language: str, settings: dict, out: Path) -> None:
        """Speaks `text` in the voice of `sample` into `out`, as WAV. `settings` go to Chatterbox's generate, over
        `DELIVERY`: `exaggeration`, `cfg_weight`. It takes the voice from the sample alone, without its transcript."""
        import torchaudio

        model = self.model(language != "en")
        options = {**DELIVERY, **settings, **({"language_id": language} if language != "en" else {})}
        torchaudio.save(str(out), model.generate(text, audio_prompt_path=str(sample), **options), model.sr)
