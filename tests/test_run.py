"""The contract: what a file's record says about it, and a stage making only what's due."""

from pathlib import Path

import pytest

from shorts.run import Run, Settings, fingerprint
from shorts.stages.base import CURRENT, EDITED, ELSEWHERE, MISSING, STALE, Stage, execute, states


class Echo(Stage):
    """A stage writing each planned file's text: "<name>: <word>"."""

    name = "echo"
    product = "narration"

    def __init__(self, words: dict[str, str]) -> None:
        self.words = words
        self.made: list[str] = []

    def plan(self, run: Run) -> dict[str, str]:
        return {path: fingerprint(word) for path, word in self.words.items()}

    def make(self, run: Run, paths: list[str]) -> None:
        self.made += paths
        for path in paths:
            run.path(path).parent.mkdir(parents=True, exist_ok=True)
            run.path(path).write_text(f"{path}: {self.words[path]}")


def test_only_what_changed_is_made_again(run: Run) -> None:
    stage = Echo({"a.txt": "one", "b.txt": "two"})
    assert execute(run, stage) == ["a.txt", "b.txt"]
    assert states(run, "narration", stage.plan(run)) == {"a.txt": CURRENT, "b.txt": CURRENT}
    assert execute(run, stage) == []

    stage.words["b.txt"] = "three"
    assert states(run, "narration", stage.plan(run))["b.txt"] == STALE
    assert execute(run, stage) == ["b.txt"]
    assert run.path("b.txt").read_text() == "b.txt: three"


def test_a_file_edited_by_hand_is_kept(run: Run) -> None:
    stage = Echo({"a.txt": "one"})
    execute(run, stage)
    run.path("a.txt").write_text("mine")
    stage.words["a.txt"] = "two"  # even when what it's made from changes
    assert states(run, "narration", stage.plan(run)) == {"a.txt": EDITED}
    assert execute(run, stage) == []
    assert run.path("a.txt").read_text() == "mine"
    assert execute(run, stage, force=True) == ["a.txt"]
    assert run.path("a.txt").read_text() == "a.txt: two"


def test_missing_and_made_elsewhere(run: Run) -> None:
    stage = Echo({"a.txt": "one", "b.txt": "two"})
    run.path("b.txt").write_text("from somewhere")
    assert states(run, "narration", stage.plan(run)) == {"a.txt": MISSING, "b.txt": ELSEWHERE}
    assert execute(run, stage) == ["a.txt"]


def test_a_failed_stage_leaves_nothing_that_looks_made(run: Run) -> None:
    from shorts.run import writing

    with pytest.raises(RuntimeError), writing(run.path("narration/01.wav")) as out:
        out.write_text("half")
        raise RuntimeError("stopped")
    assert list(run.path("narration").iterdir()) == []


def test_settings_keep_paths_relative_to_the_run(run: Run, tmp_path: Path) -> None:
    face = tmp_path / "assets" / "face.jpg"
    face.parent.mkdir()
    face.write_bytes(b"jpeg")
    settings = run.settings().model_copy(update={"face": run.relative(face)})
    run.save_settings(settings)
    assert Settings.model_validate_json(run.path("run.json").read_text()).face == "../../assets/face.jpg"
    assert run.resolve(run.settings().face) == face.resolve()


def test_a_run_from_before_the_voice_api_loads_with_its_engine_as_the_apis_model() -> None:
    # Those files wrote narrator_model out too, unused: the engine they named is what they spoke with.
    old = Settings.model_validate({"narrator": "chatterbox", "narrator_model": "omnivoice"})
    assert (old.narrator, old.narrator_model) == ("api", "chatterbox")
    older = Settings.model_validate({"narrator": "omnivoice", "narrator_options": {"speed": 1.1}})
    assert (older.narrator, older.narrator_model, older.narrator_options) == ("api", "omnivoice", {"speed": 1.1})
    assert Settings.model_validate({"narrator": "import"}).narrator == "import"
