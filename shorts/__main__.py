"""The command line: set a video up, see where it is, and make it, a stage at a time or all that's left.

    python -m shorts new RUN --footage makable=recordings/makable-tight.mp4 --voice assets/voice.wav \\
        --face assets/face.jpg [--music assets/music.mp3] [--language hi] [--tone hype] [--narrator omnivoice]
    python -m shorts status RUN
    python -m shorts run RUN [--paid]          every stage that's due, each in a process of its own
    python -m shorts <stage> RUN [--force]     one stage, here: record, write-script, film-intro,
                                               revoice-intro, speak, assemble
    python -m shorts import RUN PRODUCT FILE ...   files made elsewhere: footage (--name NAME), script,
                                               intro, voiced-intro, narration

The Gemini client is set up from the environment. For Agent Platform (Vertex AI), signed in with
`gcloud auth application-default login` (or, in GitHub Actions, google-github-actions/auth):

    GOOGLE_GENAI_USE_ENTERPRISE=true GOOGLE_CLOUD_PROJECT=<project> GOOGLE_CLOUD_LOCATION=global

For the Gemini API (AI Studio): GEMINI_API_KEY=<key>.
"""

import argparse
import sys
from pathlib import Path

from .orchestrator import advice, run_all, run_stage, status
from .run import SETTINGS, Run, Settings
from .script import LANGUAGES, TONES
from .stages import STAGES, NotReady, bring_in
from .stages.bring_in import PRODUCTS as IMPORTABLE
from .stages.record import is_url


def size(text: str) -> tuple[int, int]:
    """A size such as 1080x1920."""
    try:
        width, height = map(int, text.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} isn't a size like 1080x1920") from None
    return width, height


def option(text: str) -> tuple[str, float]:
    """A narrator option such as exaggeration=0.9."""
    key, _, value = text.partition("=")
    try:
        return key, float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} isn't an option like exaggeration=0.9") from None


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


def main() -> None:
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
    setup.add_argument("--intro-voice", choices=["convert", "import", "as-filmed"])
    setup.add_argument("--narrator", choices=["chatterbox", "omnivoice", "import"])
    setup.add_argument("--narrator-option", type=option, action="append", metavar="KEY=VALUE")
    setup.add_argument("--pronounce", dest="respellings", type=respelling, action="append", metavar="WORD=SAID")
    setup.add_argument("--reference-text", help="what's said in the voice sample, for OmniVoice")
    setup.add_argument("--size", type=size, help="the video's width x height (default 1080x1920)")
    setup.add_argument("--captions", action=argparse.BooleanOptionalAction)

    commands.add_parser("status", help="what's made, and what's next").add_argument("run", type=Path)

    everything = commands.add_parser("run", help="every stage that's due, each in a process of its own")
    everything.add_argument("run", type=Path)
    everything.add_argument("--paid", action="store_true", help="film the intro too, if it's due (about $1)")

    imported = commands.add_parser("import", help="bring in files made elsewhere")
    imported.add_argument("run", type=Path)
    imported.add_argument("product", choices=IMPORTABLE)
    imported.add_argument("files", type=Path, nargs="+")
    imported.add_argument("--name", help="the footage's name, as the script calls it")
    imported.add_argument("--as-given", action="store_true", help="narration in the order given, not by number")

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
        else:
            run_stage(run, args.command, force=args.force)
    except (NotReady, ValueError, FileNotFoundError) as problem:
        sys.exit(f"{args.command}: {problem}")


if __name__ == "__main__":
    main()
