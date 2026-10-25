"""Puts the intro (Omni's clip of you) before a screen recording: the whole video, start to end.

The intro plays first, then the recording, each with its own sound: the intro's speech, then the recording's
(say, the narration narrate_recording.py put over it). A recording with no sound stays silent. Omni's clip has
Omni's voice: pass the intro in your voice (a run's intro/voiced.mp4), or Omni's clip with `--intro-audio` (the
intro's sound in your voice). The picture is 1080x1920, like the Shorts (`--size 1920x1080` for a wide video):
a clip the frame's shape fills it, any other is shown whole over a blurred, darker copy of itself. The sound is
evened out to -14 LUFS, and there are no captions or music. For the whole video with those, bring the files
into a run folder instead (`python -m shorts import`, see the README).

    python3 merge_intro.py runs/crumb-and-co/intro/voiced.mp4 makable-tight-narrated.mp4 \\
        [--intro-audio intro-in-your-voice.wav] [--size 1080x1920] [-o final.mp4]

Needs ffmpeg and the shorts package next to this file (in Colab: merge_intro.ipynb writes both).
"""

import argparse
import tempfile
from pathlib import Path

from shorts.compose import SIZE, Part, compose, fills, whole_frames
from shorts.media import duration, frame_size, has_sound


def merge(
    intro: Path, recording: Path, out: Path, *, intro_audio: Path | None = None, size: tuple[int, int] = SIZE
) -> Path:
    """Makes `out`: the intro, then the recording, in one frame size, each with its own sound."""
    if out.resolve() in {intro.resolve(), recording.resolve()}:
        raise SystemExit(f"{out} is one of the videos going in: pick another name with -o")
    parts = []
    for name, clip, sound in [("Intro", intro, intro_audio or intro), ("Recording", recording, recording)]:
        shape, length = frame_size(clip), whole_frames(duration(clip))
        fitted = "fills the frame" if fills(shape, size) else "whole, over a blurred copy"
        heard = f"sound from {sound.name}" if has_sound(sound) else "silent"
        print(f"{name}: {clip.name}, {shape[0]}x{shape[1]}, {length:.2f} s, {fitted}, {heard}")
        parts.append(Part(clip, length, sound))
    with tempfile.TemporaryDirectory() as work:
        compose(parts, Path(work), out, size=size, captions=False)
    return out


def frame_size_arg(text: str) -> tuple[int, int]:
    """--size's value, such as 1080x1920: even numbers, which yuv420p needs."""
    try:
        width, height = map(int, text.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} isn't a size like 1080x1920") from None
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise argparse.ArgumentTypeError(f"{text}: the width and height must be even")
    return width, height


def main() -> None:
    parser = argparse.ArgumentParser(description="Put the intro before a screen recording, for the whole video.")
    parser.add_argument("intro", type=Path, help="the intro clip Omni filmed (in your voice, or with --intro-audio)")
    parser.add_argument("recording", type=Path, help="the screen recording, narrated or silent")
    parser.add_argument("--intro-audio", type=Path, help="the intro's sound in your voice, in place of the clip's")
    parser.add_argument(
        "--size", type=frame_size_arg, default=SIZE, help="the video's width x height (default: 1080x1920)"
    )
    parser.add_argument("-o", "--out", type=Path, help="the video to make (default: <recording>-with-intro.mp4)")
    args = parser.parse_args()
    out = args.out or args.recording.with_name(f"{args.recording.stem}-with-intro.mp4")
    merge(args.intro, args.recording, out, intro_audio=args.intro_audio, size=args.size)
    print(f"Made {out} ({duration(out):.1f} s)")


if __name__ == "__main__":
    main()
