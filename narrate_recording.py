"""Narrates a screen recording with a script's scenes, spoken already: one audio file per scene.

A script written from a recording's steps (a run's script.json) gives each scene a stretch of the recording
(`start` to `end`, seconds). This cuts those stretches out, in the script's order, and plays each at the speed
that makes it last as long as its scene's audio (plus a short pause), so what's said is on screen while it's
said. What no scene uses (retries, errors, waits) is left out. The picture stays the recording's size, the
voice is evened out to -14 LUFS, and there's no intro, captions or music. For the whole video from the same
files, bring them into a run folder instead (`python -m shorts import`, see the README).

    python3 narrate_recording.py recordings/makable-tight.mp4 runs/crumb-and-co/script.json \\
        assets/download\\ \\(*\\).wav [-o makable-tight-narrated.mp4]

The audio files go in the scenes' order (the shell puts download (1) to (9) in order, but (10) before (2)).
Needs ffmpeg and the shorts package next to this file (in Colab: narrate_recording.ipynb writes both).
"""

import argparse
import tempfile
from pathlib import Path

from shorts.compose import FPS, GAP, TAIL, Part, compose, even, whole_frames
from shorts.media import duration, frame_size
from shorts.script import Script


def narrate(recording: Path, script: Path, audio: list[Path], out: Path) -> Path:
    """Makes `out`: each scene's stretch of `recording`, fitted to its audio, one after another."""
    scenes = Script.model_validate_json(script.read_text()).scenes
    if len(audio) != len(scenes):
        raise SystemExit(f"{script.name} has {len(scenes)} scenes, but there are {len(audio)} audio files")
    if any(scene.start is None or scene.end is None for scene in scenes):
        raise SystemExit(f"{script.name}'s scenes have no start and end: write it from the recording's steps")
    total = duration(recording)
    parts = []
    for index, (scene, speech) in enumerate(zip(scenes, audio, strict=True)):
        start, end = scene.start, min(scene.end, total)
        if end - start < 1 / FPS:
            raise SystemExit(f"Scene {index + 1} ({start}-{scene.end} s) isn't in the {total:.1f}-second recording")
        tail = TAIL if index == len(scenes) - 1 else 0
        part = Part(recording, whole_frames(duration(speech) + GAP + tail), speech, start=start, end=end)
        print(f"Scene {index + 1}: {start:5.1f}-{end:5.1f} s at {part.speed:.2f}x, ", end="")
        print(f"with {speech.name} ({part.length:.2f} s)")
        print(f"  {scene.text}")
        parts.append(part)
    with tempfile.TemporaryDirectory() as work:
        compose(parts, Path(work), out, size=even(frame_size(recording)), captions=False)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Narrate a screen recording with its script's scenes, spoken.")
    parser.add_argument("recording", type=Path, help="the screen recording the script was written from")
    parser.add_argument("script", type=Path, help="the run's script.json, its scenes with start and end")
    parser.add_argument("audio", type=Path, nargs="+", help="each scene's narration, in the scenes' order")
    parser.add_argument("-o", "--out", type=Path, help="the video to make (default: <recording>-narrated.mp4)")
    args = parser.parse_args()
    out = args.out or args.recording.with_name(f"{args.recording.stem}-narrated.mp4")
    narrate(args.recording, args.script, args.audio, out)
    print(f"Made {out} ({duration(out):.1f} s)")


if __name__ == "__main__":
    main()
