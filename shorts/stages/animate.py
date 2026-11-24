"""cast, stills and animate: an animated Short's footage, drawn and animated shot by shot from its storyboard.

    cast      cast/<name>.png        each character's sheet (front, three-quarter, side), from run.json's
                                     image model: cast_takes takes (cast/<name>-take-1.png, ...), the first
                                     used until you choose another (`choose RUN man 2`). A mascot kept in
                                     SHORTS_HOME (`me --character man=FILE`) is used as it is.
    stills    stills/<shot>.png      each shot's still, with its characters' sheets as references, the first
                                     still for the style, and the shot before for one that follows on from it;
                                     and stills/sheet.png, all of them in one picture, to check them at a glance
    animate   footage/<shot>.mp4     each still animated (`shorts.animators`), as long as the shot's narration
                                     and a pause, saved as animations/<take>/<shot>.mp4 too. Paid ($0.07 a second
                                     with Omni): `run` never animates on its own, only `animate RUN` or `run --paid`.

The narration is spoken before the stills are animated, so each clip is asked for only as long as its shot needs.
A file you change is kept as it is (the run's usual rule): a sheet you chose is locked, and so is a clip you chose.

    python -m shorts animate RUN --with omni-1.1,omni-1.2 [--takes 2]   more takes, in animations/<take>/
    python -m shorts compare RUN                         every take of every shot side by side: animations/compare.mp4
    python -m shorts choose RUN shot-01|all TAKE         a take's clip as the footage (picks.json notes it)
    python -m shorts choose RUN man 2                    a character sheet's take, as the one every still uses
    python -m shorts prompts RUN                         each still and its motion prompt, to animate elsewhere
"""

import json
import shutil
import tempfile
from pathlib import Path

from .. import COMMAND
from ..animators import ANIMATORS, motion_prompt, take, take_name
from ..compose import GAP, TAIL
from ..home import character
from ..images import IMAGE_MODELS, Reference, sheet_prompt, still_prompt, still_references
from ..media import duration, ffmpeg
from ..run import (
    PICKS,
    Run,
    Settings,
    animation_file,
    cast_file,
    cast_take_file,
    file_hash,
    fingerprint,
    footage_file,
    narration_file,
    still_file,
    writing,
)
from ..script import Script, on_screen
from .base import NotReady, Stage, read_script

STILLS_SHEET = "stills/sheet.png"
GOOGLE = "pip install 'makable-shorts[gemini]', with GOOGLE_CLOUD_PROJECT and Google Cloud's sign-in (see the README)"


def storyboard(run: Run) -> Script:
    """The script, if it's an animated Short's, with a shot for every scene."""
    script = read_script(run)
    missing = [number for number, scene in enumerate(script.scenes, 1) if scene.shot is None]
    if missing:
        raise NotReady(f"scene {missing[0]} has no shot: {COMMAND} check-script {run.folder} says what's wrong")
    return script


class Cast(Stage):
    name = "cast"
    product = "cast"
    needs = ("script",)
    extra = "gemini"
    where = GOOGLE

    def by(self, settings: Settings) -> str:
        return f"cast ({settings.image_model})"

    def packages(self, settings: Settings) -> list[str]:
        return ["google.genai"]

    def plan(self, run: Run) -> dict[str, str]:
        settings, script = run.settings(), storyboard(run)
        plan = {}
        for one in script.characters:
            mascot = character(one.name)
            made_from = (
                ("mascot", file_hash(mascot)) if mascot else (settings.image_model, sheet_prompt(script.style, one))
            )
            plan[cast_file(one.name)] = fingerprint(*made_from)
        return plan

    def make(self, run: Run, paths: list[str]) -> None:
        from ..images import client, draw

        settings, script = run.settings(), run.script()
        google = None
        for one in script.characters:
            if cast_file(one.name) not in paths:
                continue
            if mascot := character(one.name):
                print(f"{one.name}: your mascot, {mascot}")
                with writing(run.path(cast_file(one.name))) as out:
                    shutil.copyfile(mascot, out)
                continue
            google = google or client()
            cost = settings.cast_takes * IMAGE_MODELS.get(settings.image_model, 0.0)
            print(
                f"Drawing {one.name}'s sheet, {settings.cast_takes} takes with {settings.image_model} (about ${cost:.2f})"
            )
            for number in range(1, settings.cast_takes + 1):
                with writing(run.path(cast_take_file(one.name, number))) as out:
                    draw(google, sheet_prompt(script.style, one), [], out, model=settings.image_model, aspect="16:9")
            with writing(run.path(cast_file(one.name))) as out:
                shutil.copyfile(run.path(cast_take_file(one.name, 1)), out)
            others = f"; or {COMMAND} choose {run.folder} {one.name} 2" if settings.cast_takes > 1 else ""
            print(f"  {cast_file(one.name)} is take 1{others}")


class Stills(Stage):
    name = "stills"
    product = "stills"
    needs = ("script", "cast")
    extra = "gemini"
    where = GOOGLE

    def by(self, settings: Settings) -> str:
        return f"stills ({settings.image_model})"

    def packages(self, settings: Settings) -> list[str]:
        return ["google.genai"]

    def drawings(self, run: Run) -> list[tuple[str, int, bool, str, list[Reference]]]:
        """Every image to draw, in order: its path, its scene's index, whether it's an end still, its prompt and its
        references. The references are named as if every still were drawn, so the prompts are known before."""
        settings, script = run.settings(), storyboard(run)
        sheets = {one.name: run.path(cast_file(one.name)) for one in script.characters}
        stills = {index: run.path(still_file(scene.footage)) for index, scene in enumerate(script.scenes)}
        ends = settings.animator in ANIMATORS and ANIMATORS[settings.animator].end_frame
        found = []
        for index, scene in enumerate(script.scenes):
            shot = scene.shot
            assert shot is not None
            references = still_references(script, index, sheets, stills)
            found.append(
                (still_file(scene.footage), index, False, still_prompt(script.style, shot, references), references)
            )
            if ends and shot.end_still:
                start = Reference(stills[index], "this shot's first frame: the same place and characters")
                prompt = still_prompt(script.style, shot, [*references, start], end=True)
                found.append((still_file(scene.footage, end=True), index, True, prompt, [*references, start]))
        return found

    def plan(self, run: Run) -> dict[str, str]:
        settings = run.settings()
        sheets = {}
        for one in storyboard(run).characters:
            sheet = run.path(cast_file(one.name))
            if not sheet.exists():
                raise NotReady(f"{cast_file(one.name)} isn't drawn yet: {COMMAND} cast {run.folder}")
            sheets[str(sheet)] = file_hash(sheet)
        plan: dict[str, str] = {}
        for path, _, _, prompt, references in self.drawings(run):
            # A still drawn after another is made from it: from what that one is made from, as it's drawn first.
            made_from = [
                sheets.get(str(reference.path)) or plan.get(run.relative(reference.path)) for reference in references
            ]
            plan[path] = fingerprint(settings.image_model, prompt, made_from)
        return plan

    def make(self, run: Run, paths: list[str]) -> None:
        from ..images import client, draw

        settings = run.settings()
        cost = len(paths) * IMAGE_MODELS.get(settings.image_model, 0.0)
        print(f"Drawing {len(paths)} stills with {settings.image_model} (about ${cost:.2f})")
        google = client()
        for path, _, _, prompt, references in self.drawings(run):
            if path in paths:
                print(f"  {path}")
                with writing(run.path(path)) as out:
                    draw(google, prompt, [reference.path for reference in references], out, model=settings.image_model)
        sheet = stills_sheet(run, storyboard(run))
        print(f"All of them at a glance: {sheet}")


def stills_sheet(run: Run, script: Script, *, width: int = 270) -> Path:
    """Every still there is, labelled with its shot, side by side in one picture (stills/sheet.png)."""
    from PIL import Image, ImageDraw

    drawn = [(scene.footage, run.path(still_file(scene.footage))) for scene in script.scenes]
    images = []
    for name, path in drawn:
        if path.exists():
            image = Image.open(path).convert("RGB")
            image = image.resize((width, round(image.height * width / image.width)))
            ImageDraw.Draw(image).rectangle((0, 0, 80, 20), fill="white")
            ImageDraw.Draw(image).text((5, 4), name, fill="red")
            images.append(image)
    if not images:
        raise NotReady("there are no stills yet")
    sheet = Image.new("RGB", (width * len(images), max(image.height for image in images)), "black")
    for index, image in enumerate(images):
        sheet.paste(image, (index * width, 0))
    out = run.path(STILLS_SHEET)
    with writing(out) as part:
        sheet.save(part)
    return out


def shown_for(run: Run, settings: Settings, script: Script, index: int) -> float:
    """How long scene `index` is on screen, in seconds: its narration and a pause (and a second more for the last),
    as assemble plays it; or in a video without a voice, as long as its words take to read."""
    scene = script.scenes[index]
    tail = TAIL if index == len(script.scenes) - 1 else 0.0
    if settings.narrator == "none":
        return on_screen(scene, silent=True) + tail
    speech = run.path(narration_file(index))
    if not speech.exists():
        raise NotReady(f"{narration_file(index)} isn't spoken yet: the clips are made as long as the narration")
    return duration(speech) + GAP + tail


def shots(run: Run, settings: Settings) -> list[tuple[str, Path, Path | None, str, int]]:
    """Each shot to animate, in order: its footage's name, its still, its end still (or None), its motion prompt,
    and the clip's seconds. Shots whose footage you brought in are left out: they're yours."""
    from ..animators import clip_seconds

    script = storyboard(run)
    found = []
    for index, scene in enumerate(script.scenes):
        if scene.footage in settings.footage:
            continue
        shot = scene.shot
        assert shot is not None
        still = run.path(still_file(scene.footage))
        if not still.exists():
            raise NotReady(f"{still_file(scene.footage)} isn't drawn yet: {COMMAND} stills {run.folder}")
        end = run.path(still_file(scene.footage, end=True))
        seconds = clip_seconds(shown_for(run, settings, script, index))
        found.append(
            (scene.footage, still, end if end.exists() else None, motion_prompt(script.style, shot.motion), seconds)
        )
    return found


def note_picks(run: Run, picks: dict[str, str]) -> None:
    """Notes which take each shot's footage is (picks.json), for the insights to compare models by."""
    file = run.path(PICKS)
    kept = json.loads(file.read_text()) if file.exists() else {}
    with writing(file) as out:
        out.write_text(json.dumps(kept | picks, indent=1, sort_keys=True) + "\n")


def animate_take(run: Run, name: str, made: list[tuple[str, Path, Path | None, str, int]], folder: str) -> None:
    """Animates each of `made` with the take `name`, into animations/<folder>/<shot>.mp4, printing what it costs."""
    animator, model = take(name)
    seconds = sum(clip[4] for clip in made)
    print(f"Animating {len(made)} shots with {name} ({model}): {seconds} s, about ${seconds * animator.per_second:.2f}")
    for shot, still, end, prompt, length in made:
        print(f"  {shot}: {length} s")
        with writing(run.path(animation_file(folder, shot))) as out:
            animator.animate(still, end if animator.end_frame else None, prompt, length, out, model)


class Animate(Stage):
    name = "animate"
    product = "footage"
    needs = ("script", "stills", "narration")
    extra = "gemini"
    where = GOOGLE
    cost = "$0.07 a second of video, with Omni"

    def by(self, settings: Settings) -> str:
        return f"animate ({take_name(settings.animator, settings.animator_model)})"

    def requires(self, settings: Settings) -> tuple[str, ...]:
        return tuple(need for need in self.needs if need != "narration" or settings.narrator != "none")

    def packages(self, settings: Settings) -> list[str]:
        return list(ANIMATORS[settings.animator].packages) if settings.animator in ANIMATORS else []

    def plan(self, run: Run) -> dict[str, str]:
        settings = run.settings()
        name = take_name(settings.animator, settings.animator_model)
        plan = {}
        for shot, still, end, prompt, seconds in shots(run, settings):
            ending = file_hash(end) if end and ANIMATORS[settings.animator].end_frame else None
            plan[footage_file(shot)] = fingerprint(name, take(name)[1], file_hash(still), ending, prompt, seconds)
        return plan

    def make(self, run: Run, paths: list[str]) -> None:
        settings = run.settings()
        name = take_name(settings.animator, settings.animator_model)
        made = [clip for clip in shots(run, settings) if footage_file(clip[0]) in paths]
        animate_take(run, name, made, name)
        for shot, *_ in made:
            with writing(run.path(footage_file(shot))) as out:
                shutil.copyfile(run.path(animation_file(name, shot)), out)
        note_picks(run, {shot: name for shot, *_ in made})


def more_takes(run: Run, names: list[str], copies: int = 1) -> list[str]:
    """Animates every shot with each take in `names`, `copies` times (omni-1.2, omni-1.2-2, ...), into
    animations/, for `compare`: what's there already is kept. Returns the takes' folders."""
    settings = run.settings()
    for name in names:
        take(name)  # a take that's no such thing is refused before anything's paid for
    folders = []
    for name in names:
        for copy in range(1, copies + 1):
            folder = name if copy == 1 else f"{name}-{copy}"
            todo = [clip for clip in shots(run, settings) if not run.path(animation_file(folder, clip[0])).exists()]
            if todo:
                animate_take(run, name, todo, folder)
            folders.append(folder)
    return folders


def takes(run: Run) -> list[str]:
    """The takes in animations/, by folder name."""
    folder = run.path("animations")
    return sorted(entry.name for entry in folder.iterdir() if entry.is_dir()) if folder.exists() else []


def compare(run: Run, *, width: int = 360) -> Path:
    """Every take of every shot side by side, a shot after another, each column labelled with its take:
    animations/compare.mp4."""
    from PIL import Image, ImageDraw

    script, columns = storyboard(run), takes(run)
    if not columns:
        raise NotReady(f"there are no takes yet: {COMMAND} animate {run.folder} --with omni-1.1,omni-1.2")
    height = width * 16 // 9
    with tempfile.TemporaryDirectory() as work:
        label = Path(work) / "label.png"
        header = Image.new("RGB", (width * len(columns), 40), "black")
        for index, name in enumerate(columns):
            ImageDraw.Draw(header).text((index * width + 10, 12), name, fill="white")
        header.save(label)
        segments = []
        for scene in script.scenes:
            clips = [run.path(animation_file(name, scene.footage)) for name in columns]
            inputs: list[str | Path] = []
            for clip in clips:
                inputs += (
                    ["-i", clip]
                    if clip.exists()
                    else ["-f", "lavfi", "-t", "1", "-i", f"color=black:s={width}x{height}"]
                )
            scaled = "".join(f"[{index}:v]scale={width}:{height},setsar=1[c{index}];" for index in range(len(clips)))
            row = "".join(f"[c{index}]" for index in range(len(clips)))
            joined = f"{row}hstack=inputs={len(clips)}:shortest=0[row];" if len(clips) > 1 else "[c0]null[row];"
            graph = f"{scaled}{joined}[{len(clips)}:v][row]vstack=shortest=1,fps=30,format=yuv420p[out]"
            segment = Path(work) / f"{scene.footage}.mp4"
            ffmpeg(
                *inputs,
                "-loop",
                "1",
                "-i",
                label,
                "-filter_complex",
                graph,
                "-map",
                "[out]",
                "-an",
                "-c:v",
                "libx264",
                segment,
            )
            segments.append(segment)
        listing = Path(work) / "segments.txt"
        listing.write_text("".join(f"file '{segment}'\n" for segment in segments))
        out = run.path("animations/compare.mp4")
        with writing(out) as part:
            ffmpeg("-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", part)
    print(f"{out}: {' | '.join(columns)}, left to right; the shots one after another")
    return out


def choose(run: Run, what: str, pick: str) -> list[str]:
    """Makes a take the one used: a character sheet's (`what` a character's name, `pick` its take's number), or a
    shot's clip (`what` its footage name, or "all", and `pick` the take). Returns the files it wrote."""
    script = storyboard(run)
    if what in {one.name for one in script.characters}:
        source = run.path(cast_take_file(what, int(pick)) if pick.isdigit() else pick)
        if not source.exists():
            raise NotReady(f"there's no take {pick} of {what}'s sheet")
        with writing(run.path(cast_file(what))) as out:
            shutil.copyfile(source, out)
        print(f"{cast_file(what)} is now take {pick}: every still is drawn from it ({COMMAND} stills {run.folder})")
        return [cast_file(what)]
    names = [scene.footage for scene in script.scenes]
    if what != "all" and what not in names:
        raise ValueError(f"{what!r} is neither a character nor a shot: one of {', '.join(names)}, or all")
    chosen = names if what == "all" else [what]
    for shot in chosen:
        if not run.path(animation_file(pick, shot)).exists():
            raise NotReady(
                f"there's no {animation_file(pick, shot)}: takes there are: {', '.join(takes(run)) or 'none'}"
            )
    for shot in chosen:
        with writing(run.path(footage_file(shot))) as out:
            shutil.copyfile(run.path(animation_file(pick, shot)), out)
        print(f"{footage_file(shot)} is {pick}'s")
    note_picks(run, dict.fromkeys(chosen, pick))
    return [footage_file(shot) for shot in chosen]


def prompts(run: Run) -> list[str]:
    """Each still, the clip's length and its motion prompt, to animate somewhere else (the Gemini website, for
    free): then `import RUN footage --name SHOT CLIP` brings each clip in."""
    settings = run.settings().model_copy(update={"footage": {}})  # every shot, brought in or not
    lines = []
    for shot, still, _, prompt, seconds in shots(run, settings):
        lines.append(f"{shot} ({seconds} s): {still}\n  {prompt}")
    return lines
