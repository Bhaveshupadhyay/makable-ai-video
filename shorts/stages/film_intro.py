"""film-intro: Gemini Omni Flash films you saying the script's intro line, from a photo of you (about $1 a clip).

Because it costs money, `python -m shorts run` never films it on its own: it says when the intro is missing or
out of date (the intro line, its setting or the photo changed), and `python -m shorts film-intro RUN` films it.
A clip filmed elsewhere (the Gemini app) comes in with `python -m shorts import RUN intro CLIP`.
"""

from ..intro import film_intro, intro_prompt
from ..run import FILMED_INTRO, Run, Settings, file_hash, fingerprint, writing
from .base import NotReady, Stage, read_script


class FilmIntro(Stage):
    name = "film-intro"
    product = "intro"
    needs = ("script",)
    extra = "gemini"
    where = "pip install 'makable-shorts[gemini]', on a Google Cloud project with billing (see the README)"
    cost = "about $1"

    def packages(self, settings: Settings) -> list[str]:
        return ["google.genai"]

    def plan(self, run: Run) -> dict[str, str]:
        settings = run.settings()
        if settings.face is None:
            raise NotReady("run.json has no photo of you: python -m shorts new RUN --face PHOTO")
        face = run.resolve(settings.face)
        if not face.exists():
            raise NotReady(f"the photo {face} isn't there")
        return {FILMED_INTRO: fingerprint("omni", intro_prompt(read_script(run)), file_hash(face))}

    def make(self, run: Run, paths: list[str]) -> None:
        from google import genai

        print("Filming the intro (about $1)")
        with writing(run.path(FILMED_INTRO)) as out:
            film_intro(genai.Client(), run.script(), run.resolve(run.settings().face), out)
