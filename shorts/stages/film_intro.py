"""film-intro and film-outro: a filmer (`shorts.filmers`: Gemini Omni, HeyGen; run.json's `intro` and `outro`) films
you saying the script's intro line, or its outro line, from a photo of you (about $1 a clip).

Because it costs money, `python -m shorts run` never films on its own: it says when a clip is missing or out of
date (its line, its setting, the photo or the filmer changed), and `python -m shorts film-intro RUN` (or
`film-outro`), or `run --paid`, films it. A clip filmed elsewhere (the Gemini app, HeyGen's or Higgsfield's site)
comes in with `python -m shorts import RUN intro CLIP` (or `outro`), a file or a link to one. The outro is filmed in
the intro's setting unless the script gives it one, and used as filmed.
"""

from .. import COMMAND
from ..filmers import FILMERS, Filmer
from ..run import FILMED_INTRO, FILMED_OUTRO, Run, Settings, file_hash, fingerprint, writing
from ..script import Script
from .base import NotReady, Stage, read_script


class FilmIntro(Stage):
    name = "film-intro"
    product = "intro"
    needs = ("script",)
    extra = "gemini"
    where = "a filmer's packages and key: see shorts/filmers.py and the README"
    cost = "about $1"
    file = FILMED_INTRO

    def filmer(self, settings: Settings) -> Filmer:
        return FILMERS[settings.intro]

    def by(self, settings: Settings) -> str:
        return f"{self.name} ({self.filmer(settings).name})"

    def packages(self, settings: Settings) -> list[str]:
        return list(self.filmer(settings).packages)

    def said(self, script: Script) -> tuple[str, str]:
        """The line, and the shot's setting."""
        return script.intro_line, script.intro_setting

    def plan(self, run: Run) -> dict[str, str]:
        settings = run.settings()
        if settings.face is None:
            raise NotReady(
                f"run.json has no photo of you: {COMMAND} new RUN --face PHOTO (or {COMMAND} me --face PHOTO)"
            )
        face = run.resolve(settings.face)
        if not face.exists():
            raise NotReady(f"the photo {face} isn't there")
        filmer = self.filmer(settings)
        made_from = filmer.source(*self.said(read_script(run)), settings)
        return {self.file: fingerprint(filmer.name, *made_from, file_hash(face))}

    def make(self, run: Run, paths: list[str]) -> None:
        settings = run.settings()
        filmer = self.filmer(settings)
        print(f"Filming the {self.product} with {filmer.name} ({self.cost})")
        with writing(run.path(self.file)) as out:
            filmer.film(*self.said(run.script()), run.resolve(settings.face), out, settings)


class FilmOutro(FilmIntro):
    name = "film-outro"
    product = "outro"
    file = FILMED_OUTRO

    def filmer(self, settings: Settings) -> Filmer:
        return FILMERS[settings.outro]

    def said(self, script: Script) -> tuple[str, str]:
        if not script.outro_line.strip():
            raise NotReady("the script has no outro line (outro_line)")
        return script.outro_line, script.outro_setting or script.intro_setting
