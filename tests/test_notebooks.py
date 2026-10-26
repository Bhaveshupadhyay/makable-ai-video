"""The notebooks write the shorts package themselves, a module at a time (build_notebook.py): each list of modules
must be all that what the notebook imports needs, or its cells fail in Colab."""

import ast
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def module_lists() -> dict[str, list[str]]:
    """build_notebook.py's lists of modules, read from its source (running it writes the notebooks)."""
    tree = ast.parse((ROOT / "build_notebook.py").read_text())
    return {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "").endswith("MODULES")
    }


@pytest.mark.parametrize(
    ("modules", "imports"),
    [
        ("MODULES", "shorts.__main__, shorts.stages"),  # the Shorts, voice and OmniVoice notebooks
        ("ENGINE_MODULES", "shorts.compose, shorts.media, shorts.script"),  # merge_intro.py's, narrate_recording.py's
        ("BROWSE_MODULES", "shorts.browse, shorts.signin"),  # record_with_browser_use.ipynb's
    ],
)
def test_each_notebook_writes_all_it_imports(modules: str, imports: str, tmp_path: Path) -> None:
    for name in module_lists()[modules]:
        written = tmp_path / "shorts" / f"{name}.py"
        written.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "shorts" / f"{name}.py", written)
    # Without site (-S), so an editable install's import hook can't find the real package; with this Python's paths
    # to its packages (a venv's, or uv's layers), but not the repo's.
    paths = [str(tmp_path), *(path for path in sys.path if path and Path(path).resolve() != ROOT)]
    check = f"import sys; sys.path[:] = {paths!r}; import {imports}"
    result = subprocess.run([sys.executable, "-I", "-S", "-c", check], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
