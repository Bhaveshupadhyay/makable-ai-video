"""The stages, and which one makes each product for a run (from its run.json).

    record          footage         copies the recordings in (drive records them), with their steps
    film-intro      intro           Gemini Omni or HeyGen films you saying the intro line (about $1)
    film-outro      outro           and the outro line (about $1), when run.json wants an outro
    take-voice      avatar-voice    the intro's voice, to speak the narration in (ffmpeg)
    speak           narration       ElevenLabs, your own voice API, or Kokoro speaks each scene
    assemble        video           ffmpeg and Pillow: final.mp4 (with the cards, in a video without an avatar)

A video without an avatar (intro and outro "card") isn't made from the intro or the outro, and one without a voice
(narrator "none") isn't made from the narration: the stages that make them have nothing to do.

What you bring in (`python -m shorts import`) is made by no stage: its product's stage is an `Import`. The script
is always brought in, as Claude writes it (the make-video skill).
"""

from ..run import Run
from .assemble import Assemble
from .base import NotReady, Stage, execute, states
from .bring_in import Import, bring_in
from .film_intro import FilmIntro, FilmOutro
from .record import RecordFootage
from .speak import Speak
from .take_voice import TakeVoice

STAGES: dict[str, Stage] = {
    stage.name: stage for stage in (RecordFootage(), FilmIntro(), FilmOutro(), TakeVoice(), Speak(), Assemble())
}

__all__ = ["STAGES", "Import", "NotReady", "Stage", "bring_in", "execute", "producer", "states"]


def producer(run: Run, product: str) -> Stage:
    """The stage that makes `product` for this run: an `Import` for the script, and when run.json says you bring
    the product in."""
    settings = run.settings()
    yours = {"intro": settings.intro, "outro": settings.outro, "narration": settings.narrator}
    if product == "script" or yours.get(product) == "import":
        return Import(product)
    return next(stage for stage in STAGES.values() if stage.product == product)
