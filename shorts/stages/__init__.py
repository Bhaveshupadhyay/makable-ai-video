"""The stages, and which one makes each product for a run (from its run.json).

    record          footage         copies the recordings in (drive records them), with their steps
    film-intro      intro           Gemini Omni or HeyGen films you saying the intro line (about $1)
    film-outro      outro           and the outro line (about $1), when run.json wants an outro
    take-voice      avatar-voice    the intro's voice, to speak the narration in (ffmpeg)
    cast            cast            an animated Short's characters, drawn (about 3 ¢ an image)
    stills          stills          and each shot's still, drawn with them (about 3 ¢ an image)
    speak           narration       ElevenLabs, your own voice API, or Kokoro speaks each scene
    animate         footage         each still animated, as long as its narration ($0.07 a second, with Omni)
    assemble        video           ffmpeg and Pillow: final.mp4 (with the cards, in a video without an avatar)

A video without an avatar (intro and outro "card") isn't made from the intro or the outro, and one without a voice
(narrator "none") isn't made from the narration: the stages that make them have nothing to do.

What you bring in (`python -m shorts import`) is made by no stage: its product's stage is an `Import`. The script
is always brought in, as Claude writes it (the make-video skill).
"""

from ..run import Run
from .animate import Animate, Cast, Stills
from .assemble import Assemble
from .base import NotReady, Stage, execute, states
from .bring_in import Import, bring_in
from .film_intro import FilmIntro, FilmOutro
from .record import RecordFootage
from .speak import Speak
from .take_voice import TakeVoice

STAGES: dict[str, Stage] = {
    stage.name: stage
    for stage in (
        RecordFootage(),
        Cast(),
        Stills(),
        FilmIntro(),
        FilmOutro(),
        TakeVoice(),
        Speak(),
        Animate(),
        Assemble(),
    )
}

__all__ = ["STAGES", "Import", "NotReady", "Stage", "bring_in", "execute", "producer", "states"]


def producer(run: Run, product: str) -> Stage:
    """The stage that makes `product` for this run: an `Import` for the script, and when run.json says you bring
    the product in."""
    settings = run.settings()
    yours = {"intro": settings.intro, "outro": settings.outro, "narration": settings.narrator}
    if product == "script" or yours.get(product) == "import":
        return Import(product)
    if product == "footage":  # an animated Short's is animated, unless you animate it and bring it in (record)
        animated = settings.kind == "animated" and settings.animator != "import"
        return STAGES["animate" if animated else "record"]
    return next(stage for stage in STAGES.values() if stage.product == product)
