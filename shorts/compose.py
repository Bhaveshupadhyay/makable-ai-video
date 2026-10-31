"""Putting the video together with ffmpeg: parts one after another, with captions and music.

A part is footage on screen while something is heard: the intro and its speech, a scene's stretch of a
recording and its narration, or a recording and its own sound. Its footage can be a picture (a title card), held
for as long as the part lasts. A stretch with an end is sped up or slowed
down to last as long as its part, so what's said is on screen while it's said; without one, the footage
plays at its own speed from `start`, looping if it's shorter. Footage the frame's shape fills it, cropped a
little; any other is shown whole over a blurred, darker copy of itself.
"""

from dataclasses import dataclass
from pathlib import Path

from .media import ffmpeg, frame_size, has_sound

FPS = 30
SIZE = (1080, 1920)  # YouTube Shorts and Instagram Reels
GAP = 0.35  # seconds of pause after each scene's narration
TAIL = 1.0  # extra seconds on the last scene
SAME_SHAPE = 0.05  # how far footage's width:height can be from the frame's (a share of it) and still fill it
FONT_CACHE = Path.home() / ".cache" / "makable-shorts"
PICTURES = (".png", ".jpg", ".jpeg")  # footage that's a picture, held on screen
# Every part in the same colours: limited-range BT.709. Footage comes in either range (screen recordings are often
# full range, filmed clips limited), and where the parts' colours change, ffmpeg starts compose's filters over,
# without the captions it has already read: the captions after it are lost.
COLOURS = (
    "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
    "setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709"
)


@dataclass
class Part:
    """A stretch of the video: `footage` on screen for `length` seconds while `speech` plays from its start."""

    footage: Path
    length: float  # seconds on screen
    speech: Path | None = None  # what's heard (the footage itself, for its own sound); None: silence
    text: str = ""  # what's said, for the captions
    said: tuple[float, float] | None = None  # when in `speech` the words start and end; None: all along
    whole: bool = False  # the caption all at once, not a few words at a time with the speech: for text not heard
    start: float = 0.0  # where in the footage to start
    end: float | None = None  # where to end, fitting start to end to `length`; None: at the footage's own speed

    @property
    def speed(self) -> float:
        return 1.0 if self.end is None else (self.end - self.start) / self.length


def whole_frames(seconds: float) -> float:
    """Rounds to whole frames, so the parts' lengths add up exactly."""
    return round(seconds * FPS) / FPS


def even(size: tuple[int, int]) -> tuple[int, int]:
    """The nearest frame size at or under `size` that yuv420p can have: even numbers."""
    return size[0] // 2 * 2, size[1] // 2 * 2


def fills(size: tuple[int, int], frame: tuple[int, int]) -> bool:
    """Whether footage of `size` is near enough the frame's shape to fill it, cropped a little."""
    return abs(size[0] / size[1] - frame[0] / frame[1]) <= SAME_SHAPE * frame[0] / frame[1]


def fit(size: tuple[int, int], frame: tuple[int, int]) -> str:
    """The filters that scale footage of `size` to the frame."""
    width, height = frame
    if fills(size, frame):
        return f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
    small = f"{width // 4}:{height // 4}"
    blur = max(1, min(12, min(width, height) // 16 - 1))  # boxblur's radius must stay under a quarter of the
    # small copy's size (its colour is at half size): 12 for a 1080x1920 frame
    return (
        f"split[a][b];"
        f"[a]scale={small}:force_original_aspect_ratio=increase,crop={small},boxblur={blur}:2,scale={width}:{height},"
        f"eq=brightness=-0.12[bg];"
        f"[b]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
    )


def render_part(part: Part, out: Path, frame: tuple[int, int] = SIZE) -> Path:
    """Encodes one part's picture (no sound), holding the last frame if the footage runs out."""
    if part.footage.suffix.lower() in PICTURES:
        source = ["-loop", "1", "-framerate", str(FPS), "-i", part.footage]
        timing = ""
    elif part.end is None:
        source = ["-stream_loop", "-1", "-ss", f"{part.start:.3f}", "-i", part.footage]
        timing = ""
    else:
        source = ["-ss", f"{part.start:.3f}", "-to", f"{part.end:.3f}", "-i", part.footage]
        timing = f"setpts=(PTS-STARTPTS)/{part.speed:.6f},"
    ffmpeg(
        *source,
        "-filter_complex",
        f"[0:v]{timing}fps={FPS},{fit(frame_size(part.footage), frame)},setsar=1,{COLOURS},"
        f"tpad=stop_mode=clone:stop_duration={part.length:.3f}[v]",
        "-map", "[v]", "-t", f"{part.length:.3f}", "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out,
    )  # fmt: skip
    return out


def soundtrack(parts: list[Part], out: Path, music: Path | None = None, music_volume: float = 0.12) -> Path:
    """Lays each part's speech at its start (padded to its length), adds music, and evens out the loudness."""
    inputs: list[str | Path] = []
    chains = []
    for index, part in enumerate(parts):
        if part.speech is not None and has_sound(part.speech):
            inputs += ["-i", part.speech]
        else:
            inputs += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        chains.append(
            f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:{part.length:.3f}[p{index}]"
        )
    labels = "".join(f"[p{index}]" for index in range(len(parts)))
    graph = ";".join(chains) + f";{labels}concat=n={len(parts)}:v=0:a=1[voice]"
    mixed = "[voice]"
    if music is not None:
        total = sum(part.length for part in parts)
        inputs += ["-stream_loop", "-1", "-i", music]
        graph += (
            f";[{len(parts)}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},"
            f"volume={music_volume},afade=t=out:st={max(total - 2, 0):.3f}:d=2[music]"
            ";[voice][music]amix=inputs=2:duration=first:normalize=0[mixed]"
        )
        mixed = "[mixed]"
    # -14 LUFS is what YouTube and Instagram play at. loudnorm works at 192 kHz, hence the resample.
    graph += f";{mixed}loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[out]"
    ffmpeg(*inputs, "-filter_complex", graph, "-map", "[out]", "-c:a", "pcm_s16le", out)
    return out


def compose(
    parts: list[Part],
    workdir: Path,
    out: Path,
    *,
    size: tuple[int, int] = SIZE,
    music: Path | None = None,
    captions: bool = True,
) -> Path:
    """Makes the MP4 from the parts, in order: `size` (even numbers), captions of what's said, and music."""
    workdir.mkdir(parents=True, exist_ok=True)
    pictures = [render_part(part, workdir / f"part-{index}.mp4", size) for index, part in enumerate(parts)]
    listing = workdir / "parts.ffconcat"
    listing.write_text("ffconcat version 1.0\n" + "".join(f"file {picture.name}\n" for picture in pictures))
    audio = soundtrack(parts, workdir / "soundtrack.wav", music)

    inputs: list[str | Path] = ["-f", "concat", "-i", listing, "-i", audio]
    picture = ["-map", "0:v"]
    if captions:
        from .captions import Caption, load_font, render, timed  # Pillow, only for captions

        timings: list[Caption] = []
        at = 0.0
        for part in parts:
            if part.text:
                begin, end = part.said or (0.0, part.length)
                begin, end = at + begin, at + min(end, part.length)
                timings += [Caption(part.text, begin, end)] if part.whole else timed(part.text, begin, end)
            at += part.length
        inputs += ["-f", "concat", "-i", render(timings, workdir / "captions", load_font(FONT_CACHE), size)]
        picture = ["-filter_complex", "[0:v][2:v]overlay=0:0:eof_action=pass,format=yuv420p[v]", "-map", "[v]"]
    ffmpeg(
        *inputs, *picture, "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{sum(part.length for part in parts):.3f}", out,
    )  # fmt: skip
    return out
