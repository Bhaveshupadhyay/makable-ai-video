"""film-intro and film-outro: Gemini Omni Flash films you saying the script's intro line, or its outro line, from a
photo of you (about $1 a clip).

Because it costs money, `python -m shorts run` never films on its own: it says when a clip is missing or out of
date (its line, its setting or the photo changed), and `python -m shorts film-intro RUN` (or `film-outro`), or
`run --paid`, films it. A clip filmed elsewhere (the Gemini app) comes in with `python -m shorts import RUN intro
CLIP` (or `outro`). The outro is filmed in the intro's setting unless the script gives it one, and used as filmed.
"""

from ..intro import film, intro_prompt, outro_prompt
from ..run import FILMED_INTRO, FILMED_OUTRO, Run, Settings, file_hash, fingerprint, writing
from ..script import Script
from .base import NotReady, Stage, read_script


class FilmIntro(Stage):
    name = "film-intro"
    product = "intro"
    needs = ("script",)
    extra = "gemini"
    where = "pip install 'makable-shorts[gemini]', on a Google Cloud project with billing (see the README)"
    cost = "about $1"
    file = FILMED_INTRO

    def packages(self, settings: Settings) -> list[str]:
        return ["google.genai"]

    def prompt(self, script: Script) -> str:
        return intro_prompt(script)

    def plan(self, run: Run) -> dict[str, str]:
        settings = run.settings()
        if settings.face is None:
            raise NotReady("run.json has no photo of you: python -m shorts new RUN --face PHOTO")
        face = run.resolve(settings.face)
        if not face.exists():
            raise NotReady(f"the photo {face} isn't there")
        return {self.file: fingerprint("omni", self.prompt(read_script(run)), file_hash(face))}

    def make(self, run: Run, paths: list[str]) -> None:
        from google import genai

        print(f"Filming the {self.product} ({self.cost})")
        with writing(run.path(self.file)) as out:
            film(genai.Client(), self.prompt(run.script()), run.resolve(run.settings().face), out)


class FilmOutro(FilmIntro):
    name = "film-outro"
    product = "outro"
    file = FILMED_OUTRO

    def prompt(self, script: Script) -> str:
        if not script.outro_line.strip():
            raise NotReady("the script has no outro line (outro_line)")
        return outro_prompt(script)
