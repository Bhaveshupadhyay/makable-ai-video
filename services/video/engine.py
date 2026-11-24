"""MiniMax H3 through WanGP's Python API (`shared.api`), on one GPU: what `app.py`'s GPU container runs.

WanGP keeps the last model it ran loaded, so a container that makes video after video only loads a model once (and
again when a request asks for another of them). It downloads each model's files the first time into `models`, which
on Modal is a Volume, so later containers start without downloading.

WanGP's licence lets you use it for free, your company included, but not offer paid API or hosted access to it
without a commercial licence from its author: this API is for your own videos.
"""

import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

from .h3 import Media


class Cancelled(Exception):
    pass


class Engine:
    """WanGP at `root` (a checkout), with its checkpoints and LoRAs in `models` and its MP4s in `outputs`."""

    def __init__(self, root: Path, models: Path, outputs: Path, config: dict, cli_args: list[str]) -> None:
        self.root, self.outputs = Path(root), Path(outputs)
        self.outputs.mkdir(parents=True, exist_ok=True)
        (models / "loras").mkdir(parents=True, exist_ok=True)
        loras = self.root / "loras"  # WanGP keeps LoRAs (the URLs it downloads too) under <root>/loras/<family>
        if not loras.is_symlink():
            if loras.exists():
                loras.rename(self.root / "loras.image")
            loras.symlink_to(models / "loras")
        settings = {"checkpoints_paths": [str(models), "ckpts", "."], "save_path": str(self.outputs), **config}
        (self.root / "wgp_config.json").write_text(json.dumps(settings, indent=2))
        sys.path.insert(0, str(self.root))
        from shared.api import init

        self.session = init(
            root=self.root,
            config_path=self.root / "wgp_config.json",
            output_dir=self.outputs,
            cli_args=cli_args,
            console_output=True,
        )

    def generate(
        self, settings: dict, progress: Callable[[float, str], None], cancelled: Callable[[], bool]
    ) -> tuple[Path, dict[str, float]]:
        """Makes the video `settings` asks for (laid over its model's defaults), reporting `progress(0-1, phase)`
        as it goes, and returns its MP4 and how long each phase took. It stops when `cancelled()` says so.

        Raises:
            Cancelled: `cancelled()` said so.
            RuntimeError: WanGP failed: what it said.
        """
        task = {**self.session.get_default_settings(settings["model_type"]), **settings}
        timings: dict[str, float] = {}
        state = {"phase": None, "since": time.time(), "job": None, "checked": 0.0}

        def on_progress(update) -> None:
            now = time.time()
            phase = (update.phase or update.status or "working").strip().lower()
            if phase != state["phase"]:
                if state["phase"]:
                    timings[state["phase"]] = timings.get(state["phase"], 0.0) + now - state["since"]
                state.update(phase=phase, since=now)
            steps = f" {update.current_step}/{update.total_steps}" if update.total_steps else ""
            progress(max(0.0, min(1.0, (update.progress or 0) / 100)), f"{update.status or phase}{steps}".strip())
            if now - state["checked"] > 2:  # cancelled() reads a Dict on Modal: not on every update
                state["checked"] = now
                if cancelled() and state["job"] is not None:
                    state["job"].cancel()

        class Callbacks:
            pass

        callbacks = Callbacks()
        callbacks.on_progress = on_progress
        started = time.time()
        state["job"] = self.session.submit_task(task, callbacks=callbacks)
        result = state["job"].result()
        if state["phase"]:
            timings[state["phase"]] = timings.get(state["phase"], 0.0) + time.time() - state["since"]
        timings["total"] = time.time() - started
        if result.cancelled or cancelled():
            raise Cancelled
        if not result.success:
            raise RuntimeError("; ".join(e.message for e in result.errors) or "WanGP made no video")
        videos = [Path(f) for f in result.generated_files if str(f).lower().endswith(".mp4")]
        if not videos:
            raise RuntimeError(f"WanGP made no MP4 (it made {result.generated_files})")
        return videos[-1], timings


def write_media(work: Path, files: dict) -> Media:
    """Writes a request's files (name: (filename, bytes), references: a list of them) under `work`, and returns
    them as Media, with each image's size."""
    from PIL import Image

    media = Media()
    for name, value in files.items():
        for i, (filename, data) in enumerate(value if name == "references" else [value]):
            safe = os.path.basename(filename or "").replace(" ", "_") or name
            path = work / name / f"{i}-{safe}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            if name in ("start_image", "end_image", "references"):
                with Image.open(path) as image:
                    media.sizes[str(path)] = image.size
            if name == "references":
                media.references.append(str(path))
            else:
                setattr(media, name, str(path))
    return media
