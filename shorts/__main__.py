"""The command line: set a video up, see where it is, and make it, a stage at a time or all that's left.

    python -m shorts new RUN --footage makable=recordings/makable-tight.mp4 --voice assets/voice.wav \\
        --face assets/face.jpg [--music assets/music.mp3] [--language hi] [--tone hype] [--narrator omnivoice] \\
        [--outro omni]
    python -m shorts status RUN
    python -m shorts run RUN [--paid]          every stage that's due, each in a process of its own
    python -m shorts <stage> RUN [--force]     one stage, here: record, write-script, film-intro,
                                               film-outro, revoice-intro, speak, assemble
    python -m shorts import RUN PRODUCT FILE ...   files made elsewhere: footage (--name NAME), script,
                                               intro, outro, voiced-intro, narration
    python -m shorts check-script RUN [FILE]   what each scene says over which stretch, and what's wrong
    python -m shorts frames RUN NAME [--every SECONDS | --at SECONDS ...]   a recording's frames, labelled
                                               with their times, in contact sheets (RUN/frames/NAME-1.png, ...)
    python -m shorts browse RUN --name NAME --task FILE [--signed-in] [--model PROVIDER:MODEL]   footage
                                               recorded from a task in plain words (browser-use)

Keys and settings come from the environment, or from a .env file next to shorts/ (KEY=value lines), for what
the environment doesn't set: GEMINI_API_KEY, SHORTS_SPEECH_URL and SHORTS_SPEECH_KEY, ... (see .env.example).

The Gemini client is set up from the environment. For Agent Platform (Vertex AI), signed in with
`gcloud auth application-default login` (or, in GitHub Actions, google-github-actions/auth):

    GOOGLE_GENAI_USE_ENTERPRISE=true GOOGLE_CLOUD_PROJECT=<project> GOOGLE_CLOUD_LOCATION=global

For the Gemini API (AI Studio): GEMINI_API_KEY=<key>.
"""

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from .browse import FALLBACK, MODEL
from .orchestrator import PACKAGE_ROOT, advice, run_all, run_stage, status
from .run import SCRIPT, SETTINGS, Run, Settings, footage_file
from .script import LANGUAGES, TONES, Script, speed, words
from .stages import STAGES, NotReady, bring_in
from .stages.bring_in import PRODUCTS as IMPORTABLE
from .stages.bring_in import check_script
from .stages.record import is_url


def size(text: str) -> tuple[int, int]:
    """A size such as 1080x1920."""
    try:
        width, height = map(int, text.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} isn't a size like 1080x1920") from None
    return width, height


def option(text: str) -> tuple[str, float | bool | str]:
    """A narrator option such as exaggeration=0.9, use_speaker_boost=true (ElevenLabs') or a word."""
    key, _, value = text.partition("=")
    if not key or not value:
        raise argparse.ArgumentTypeError(f"{text!r} isn't an option like exaggeration=0.9")
    if value.lower() in ("true", "false"):
        return key, value.lower() == "true"
    try:
        return key, float(value)
    except ValueError:
        return key, value


def respelling(text: str) -> tuple[str, str]:
    """A word and how the narrator should read it, such as makable=makeable."""
    word, _, said = text.partition("=")
    if not word or not said:
        raise argparse.ArgumentTypeError(f"{text!r} isn't a respelling like makable=makeable")
    return word, said


def new(run: Run, args: argparse.Namespace) -> None:
    """Writes run.json, or changes the settings given in it."""
    settings = run.settings()
    updates = {key: getattr(args, key) for key in Settings.model_fields if getattr(args, key, None) is not None}
    # (footage, narrator options and respellings come in one at a time, and are added to what's there)
    for key in ("face", "voice", "music"):  # "" for none
        if key in updates:
            updates[key] = run.relative(Path(updates[key])) if updates[key] else None
    if "changes" in updates:
        updates["changes"] = Path(updates["changes"]).read_text()
    for item in args.footage_items or []:
        name, _, source = item.partition("=")
        settings.footage[name] = source if is_url(source) else run.relative(Path(source))
    if args.narrator_option:
        updates["narrator_options"] = {**settings.narrator_options, **dict(args.narrator_option)}
    if args.respellings:
        updates["pronounce"] = {**(settings.pronounce or {}), **dict(args.respellings)}
    run.save_settings(settings.model_copy(update=updates))
    print(run.path(SETTINGS).read_text())


def show_status(run: Run) -> None:
    entries = status(run)
    print(run.folder)
    for entry in entries:
        print(f"  {entry.product:13} {entry.stage.name:14} {entry.summary()}")
    waiting = next((entry for entry in entries if not entry.ready), None)
    print(f"Next: {advice(run, waiting)}" if waiting and not waiting.waiting else "")


def show_check(run: Run, file: Path | None) -> bool:
    """Prints what each scene says over which stretch, and how fast it'll play, then what's wrong with the
    script (run.json's, or `file`). Returns whether the video can be made from it."""
    script = Script.model_validate_json((file or run.path(SCRIPT)).read_text())
    print(f"Intro, {words(script.intro_line)} words: {script.intro_line}")
    for number, scene in enumerate(script.scenes, 1):
        rate = speed(scene)
        where = f"{scene.start:5.1f}-{scene.end:5.1f} s at {rate:.1f}x" if rate is not None else "(no stretch)"
        print(f"Scene {number}: {scene.footage} {where}, {words(scene.text)} words: {scene.text}")
    if script.outro_line:
        print(f"Outro, {words(script.outro_line)} words: {script.outro_line}")
    errors, warnings = check_script(run, script)
    for warning in warnings:
        print(f"Warning: {warning}")
    for error in errors:
        print(f"Error: {error}")
    print("" if errors or warnings else "Nothing wrong")
    return not errors


def show_frames(run: Run, name: str, times: list[float] | None, every: float, width: int) -> None:
    """Saves contact sheets of a recording's frames (30 to a sheet) in RUN/frames, and prints where."""
    from .sheet import contact_sheet, times_every

    footage = run.settings().footage
    if name not in footage:
        raise NotReady(f"run.json has no footage {name!r}: {', '.join(footage) or 'it names none'}")
    video = run.path(footage_file(name))
    video = video if video.exists() else run.resolve(footage[name])
    if not video.exists():
        raise NotReady(f"the footage {name!r} isn't there yet: {video}")
    times = times or times_every(video, every)
    for number, first in enumerate(range(0, len(times), 30), 1):
        sheet = contact_sheet(video, times[first : first + 30], run.path(f"frames/{name}-{number}.png"), width=width)
        print(f"{sheet}: {times[first]:g}-{times[first : first + 30][-1]:g} s")


def load_env(file: Path) -> None:
    """Sets what a .env file says (KEY=value lines, # for comments), for what the environment doesn't set."""
    if not file.exists():
        return
    for line in file.read_text().splitlines():
        key, equals, value = line.strip().removeprefix("export ").partition("=")
        if equals and key.strip() and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def browse_elsewhere() -> None:
    """Runs this command in SHORTS_BROWSE_PYTHON, when this Python hasn't browser-use (it pins its own packages)."""
    python = os.path.expanduser(os.environ.get("SHORTS_BROWSE_PYTHON", ""))
    if not python:
        raise NotReady(
            "browser-use isn't installed here: set SHORTS_BROWSE_PYTHON to the Python of an environment that has it "
            "(uv venv ~/browse-env --python 3.12 && uv pip install --python ~/browse-env -e '.[browse]')"
        )
    paths = [str(PACKAGE_ROOT), *filter(None, [os.environ.get("PYTHONPATH")])]
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join(paths)}
    sys.exit(subprocess.run([python, "-m", "shorts", *sys.argv[1:]], env=environment).returncode)


def main() -> None:
    load_env(PACKAGE_ROOT / ".env")  # first: the options' defaults come from the environment too
    parser = argparse.ArgumentParser(prog="python -m shorts", description="Make a 1-minute video, stage by stage.")
    commands = parser.add_subparsers(dest="command", required=True)

    setup = commands.add_parser("new", help="write run.json, or change settings in it")
    setup.add_argument("run", type=Path)
    setup.add_argument("--footage", dest="footage_items", action="append", metavar="NAME=FILE_OR_URL")
    setup.add_argument("--changes", type=Path, help="a text file: what changed, for a script without steps")
    setup.add_argument("--face", help="a photo of you, for Omni")
    setup.add_argument("--voice", help="a sample of you talking")
    setup.add_argument("--music", help='music to play quietly under the video ("" for none)')
    setup.add_argument("--language", choices=sorted(LANGUAGES))
    setup.add_argument("--tone", choices=list(TONES))
    setup.add_argument("--script", choices=["gemini", "import"])
    setup.add_argument("--intro", choices=["omni", "import"])
    setup.add_argument("--outro", choices=["omni", "import", "none"], help="an outro after the recording, or none")
    setup.add_argument("--intro-voice", choices=["convert", "import", "as-filmed"])
    setup.add_argument("--narrator", choices=["chatterbox", "omnivoice", "api", "import"])
    setup.add_argument("--narration-voice", choices=["sample", "intro"], help="the voice sample's, or the intro's")
    setup.add_argument("--narrator-model", help="the voice API's model: \"omnivoice\", or ElevenLabs' own")
    setup.add_argument("--narrator-option", type=option, action="append", metavar="KEY=VALUE")
    setup.add_argument("--pronounce", dest="respellings", type=respelling, action="append", metavar="WORD=SAID")
    setup.add_argument("--reference-text", help="what's said in the voice sample, for OmniVoice")
    setup.add_argument("--size", type=size, help="the video's width x height (default 1080x1920)")
    setup.add_argument("--captions", action=argparse.BooleanOptionalAction)

    commands.add_parser("status", help="what's made, and what's next").add_argument("run", type=Path)

    everything = commands.add_parser("run", help="every stage that's due, each in a process of its own")
    everything.add_argument("run", type=Path)
    everything.add_argument("--paid", action="store_true", help="film the intro and outro too, if due (about $1 each)")

    imported = commands.add_parser("import", help="bring in files made elsewhere")
    imported.add_argument("run", type=Path)
    imported.add_argument("product", choices=IMPORTABLE)
    imported.add_argument("files", type=Path, nargs="+")
    imported.add_argument("--name", help="the footage's name, as the script calls it")
    imported.add_argument("--as-given", action="store_true", help="narration in the order given, not by number")

    checked = commands.add_parser("check-script", help="what each scene says over which stretch, and what's wrong")
    checked.add_argument("run", type=Path)
    checked.add_argument("file", type=Path, nargs="?", help="a script to check before it's brought in")

    frames = commands.add_parser("frames", help="a recording's frames, labelled with their times, in contact sheets")
    frames.add_argument("run", type=Path)
    frames.add_argument("name", help="the footage's name, as run.json calls it")
    frames.add_argument("--at", type=float, nargs="+", metavar="SECONDS", help="these times (default: --every)")
    frames.add_argument("--every", type=float, default=2.5, metavar="SECONDS", help="a frame this often")
    frames.add_argument("--width", type=int, default=240, help="each frame's width in pixels (larger to read text)")

    record = commands.add_parser("browse", help="record footage from a task in plain words (browser-use)")
    record.add_argument("run", type=Path)
    record.add_argument("--name", default="demo", help="the footage's name, as the script calls it")
    record.add_argument("--task", type=Path, required=True, help="a text file: what to do and show, in plain words")
    record.add_argument("--url", default="https://makable.tech", help="the page it starts on")
    record.add_argument("--signed-in", action="store_true", help="as makable's demo user (SUPABASE_*, MAKABLE_DEMO_*)")
    record.add_argument("--max-steps", type=int, default=60)
    model = os.environ.get("SHORTS_BROWSE_MODEL") or MODEL
    record.add_argument("--model", default=model, help=f"provider:model, such as anthropic:... (default {model})")
    fallback = os.environ.get("SHORTS_BROWSE_FALLBACK", FALLBACK)
    record.add_argument("--fallback", default=fallback, help=f'when the model fails ("" for none; default {fallback})')

    for name, stage in STAGES.items():
        one = commands.add_parser(name, help=f"make the {stage.product}, here")
        one.add_argument("run", type=Path)
        one.add_argument("--force", action="store_true", help="make every file again, edited ones too")

    args = parser.parse_args()
    run = Run(args.run)
    try:
        if args.command == "new":
            new(run, args)
        elif args.command == "status":
            show_status(run)
        elif args.command == "run":
            sys.exit(0 if run_all(run, paid=args.paid) else 1)
        elif args.command == "import":
            bring_in(run, args.product, args.files, name=args.name, as_given=args.as_given)
        elif args.command == "check-script":
            sys.exit(0 if show_check(run, args.file) else 1)
        elif args.command == "frames":
            show_frames(run, args.name, args.at, args.every, args.width)
        elif args.command == "browse":
            if importlib.util.find_spec("browser_use") is None:
                browse_elsewhere()
            from .stages.browse import browse

            options = {"url": args.url, "signed_in": args.signed_in, "max_steps": args.max_steps}
            browse(run, args.name, args.task.read_text(), model=args.model, fallback=args.fallback or None, **options)
        else:
            run_stage(run, args.command, force=args.force)
    except (NotReady, ValueError, FileNotFoundError) as problem:
        sys.exit(f"{args.command}: {problem}")


if __name__ == "__main__":
    main()
