"""write-script: Gemini writes script.json, from the footage's steps when it has them (each scene then says
what's on screen over its stretch of a recording), or else from what changed (`changes` in run.json).

It's written in run.json's language and tone. Edit script.json to change what's said: an edited script is
kept, even when the settings change (delete it to write a new one).
"""

import json
from pathlib import Path

from ..run import SCRIPT, Run, Settings, file_hash, fingerprint, steps_file, writing
from ..script import TEXT_MODEL
from .base import NotReady, Stage


class WriteScript(Stage):
    name = "write-script"
    product = "script"
    needs = ("footage",)
    extra = "gemini"
    where = "pip install 'makable-shorts[gemini]', with GEMINI_API_KEY or Agent Platform's settings (see the README)"

    def packages(self, settings: Settings) -> list[str]:
        return ["google.genai"]

    def steps(self, run: Run, settings: Settings) -> dict[str, Path]:
        """The footage's steps files, by its name, for the footage that has them."""
        files = {name: run.path(steps_file(name)) for name in settings.footage}
        return {name: path for name, path in files.items() if path.exists()}

    def plan(self, run: Run) -> dict[str, str]:
        settings = run.settings()
        steps = {name: file_hash(path) for name, path in self.steps(run, settings).items()}
        if not steps and not settings.changes:
            raise NotReady("no footage has steps, and run.json has no changes: what's the video about?")
        made_from = (TEXT_MODEL, settings.language, settings.tone, settings.changes, sorted(settings.footage), steps)
        return {SCRIPT: fingerprint("gemini", *made_from)}

    def make(self, run: Run, paths: list[str]) -> None:
        from google import genai

        from .. import script as scripts

        settings = run.settings()
        client = genai.Client()  # Agent Platform or the Gemini API, from the environment (see the README)
        options = {"language": settings.language, "tone": settings.tone}
        steps = {name: json.loads(path.read_text()) for name, path in self.steps(run, settings).items()}
        if steps:
            script = scripts.write_script_from_steps(client, steps, changes=settings.changes, **options)
        else:
            script = scripts.write_script(client, settings.changes, list(settings.footage), **options)
        with writing(run.path(SCRIPT)) as out:
            out.write_text(script.model_dump_json(indent=2) + "\n")
        for index, scene in enumerate(script.scenes, 1):
            print(f"{index}. {scene.text}")
