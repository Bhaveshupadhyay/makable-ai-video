#!/bin/sh
# Rebuilds the notebooks and pushes the code to My Drive/makable-shorts/ (the rclone remote "gdrive"), to open
# the notebooks in Colab from there. Only files whose contents changed are sent. A file it replaces on Drive
# (such as a notebook Colab saved with its outputs) is kept in makable-shorts/.replaced/<time>/.
# assets/, recordings/ and runs/ on Drive aren't touched. Extra rclone options pass through: --dry-run shows
# what it would do.
set -e
cd "$(dirname "$0")"
python3 build_notebook.py
rclone copy . gdrive:makable-shorts \
    --include "/*.ipynb" --include "/build_notebook.py" --include "/narrate_recording.py" --include "/merge_intro.py" \
    --include "/README.md" \
    --include "/shorts/*.py" --include "/shorts/stages/*.py" --include "/pyproject.toml" \
    --checksum --backup-dir "gdrive:makable-shorts/.replaced/$(date +%Y-%m-%d-%H%M%S)" \
    --stats-one-line --stats 0 -v "$@"
