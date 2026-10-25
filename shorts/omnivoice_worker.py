"""OmniVoice for `voice.OmniVoice`: in the same Python when OmniVoice is installed there (the OmniVoice notebook),
or run by the Python of its own environment (`voice.install_omnivoice`), next to Chatterbox's.

Run as a script, it loads the model once, then reads requests on stdin, one JSON object a line:

    {"text": "...", "reference": "voice.wav", "reference_text": null, "language": "en", "options": {}, "out": "scene.wav"}

writes the speech to "out", and answers on stdout, a line each: {"out": "scene.wav"}, or {"error": "..."}.
Everything else it prints goes to stderr. With an argument ("cuda", "mps" or "cpu"), it runs there.
"""

import hashlib
import json
import sys
import traceback
from pathlib import Path

MODEL = "k2-fsa/OmniVoice"


class Speaker:
    """OmniVoice's model, loaded once, and the voices it took from samples."""

    def __init__(self, device: str | None = None) -> None:
        """
        Args:
            device: "cuda", "mps" or "cpu"; the fastest available by default.
        """
        import omnivoice
        import torch

        if device is None:
            device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        self.model = omnivoice.OmniVoice.from_pretrained(MODEL, device_map=device, dtype=dtype)
        self.prompts = {}  # the voice taken from each sample (and what's said in it), to reuse

    def say(self, request: dict) -> None:
        """Speaks a request's text (keys as in the module's docstring) into its "out" file, as WAV."""
        import soundfile

        reference = Path(request["reference"])
        voice = hashlib.sha256(reference.read_bytes()).hexdigest(), request["reference_text"]
        if voice not in self.prompts:
            self.prompts[voice] = self.model.create_voice_clone_prompt(str(reference), request["reference_text"])
        [audio] = self.model.generate(
            text=request["text"],
            language=request["language"],
            voice_clone_prompt=self.prompts[voice],
            **request["options"],
        )
        soundfile.write(request["out"], audio, self.model.sampling_rate)


def main() -> None:
    answers = sys.stdout
    sys.stdout = sys.stderr  # what OmniVoice and the libraries under it print, so it can't get into the answers

    speaker = Speaker(sys.argv[1] if len(sys.argv) > 1 else None)
    for line in sys.stdin:
        request = json.loads(line)
        try:
            speaker.say(request)
            answer = {"out": request["out"]}
        except Exception:
            answer = {"error": traceback.format_exc()}
        print(json.dumps(answer), file=answers, flush=True)


if __name__ == "__main__":
    main()
