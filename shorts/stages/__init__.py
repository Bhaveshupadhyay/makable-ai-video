"""The stages, and which one makes each product for a run (from its run.json).

    record          footage         copies recordings in, or records pages (Playwright)
    write-script    script          Gemini, from the footage's steps or what changed
    film-intro      intro           Gemini Omni films you (about $1)
    revoice-intro   voiced-intro    Demucs and Chatterbox: the intro in your voice (GPU)
    speak           narration       Chatterbox or OmniVoice speaks each scene (GPU)
    assemble        video           ffmpeg and Pillow: final.mp4

What you bring in (`python -m shorts import`) is made by no stage: its product's stage is an `Import`.
"""

from ..run import Run
from .assemble import Assemble
from .base import NotReady, Stage, execute, states
from .bring_in import Import, bring_in
from .film_intro import FilmIntro
from .record import RecordFootage
from .revoice_intro import RevoiceIntro
from .speak import Speak
from .write_script import WriteScript

STAGES: dict[str, Stage] = {
    stage.name: stage for stage in (RecordFootage(), WriteScript(), FilmIntro(), RevoiceIntro(), Speak(), Assemble())
}

__all__ = ["STAGES", "Import", "NotReady", "Stage", "bring_in", "execute", "producer", "states"]


def producer(run: Run, product: str) -> Stage:
    """The stage that makes `product` for this run: an `Import` when run.json says you bring it in."""
    settings = run.settings()
    yours = {"script": settings.script, "intro": settings.intro, "voiced-intro": settings.intro_voice}
    yours["narration"] = settings.narrator
    if yours.get(product) == "import":
        return Import(product)
    return next(stage for stage in STAGES.values() if stage.product == product)
