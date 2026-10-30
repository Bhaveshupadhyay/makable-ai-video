"""The command line: set a video up, see where it is, and make it, a stage at a time or all that's left.

    python -m shorts me [--face PHOTO] [--music FILE] [--voice FILE]   your own files, kept for every video
                                               (in SHORTS_HOME, ~/.config/makable-shorts: see shorts/home.py)
    python -m shorts signin --url URL          sign in to a site by hand, once, for recordings --signed-in
    python -m shorts new RUN [--face PHOTO] [--music FILE] [--language hi] [--tone hype]   a run, with your files
    python -m shorts browse RUN --url URL --name NAME --task FILE [--signed-in] [--model PROVIDER:MODEL]   footage
                                               recorded from a task in plain words (browser-use)
    python -m shorts drive RUN start|look|click|type|...|stop   footage recorded by driving Chrome a command
                                               at a time, as Claude Code does (see shorts/drive.py)
    python -m shorts import RUN PRODUCT FILE ...   files made elsewhere, or links to them: the script (always),
                                               footage (--name NAME), intro, outro, narration
    python -m shorts voices [--gender male]    HeyGen's voices, for run.json's filmer_voice
    python -m shorts status RUN
    python -m shorts run RUN [--paid]          every stage that's due, each in a process of its own
    python -m shorts <stage> RUN [--force]     one stage, here: record, film-intro, film-outro, take-voice,
                                               speak, assemble
    python -m shorts check-script RUN [FILE]   what each scene says over which stretch, and what's wrong
    python -m shorts frames RUN NAME [--every SECONDS | --at SECONDS ...]   a recording's frames, labelled
                                               with their times, in contact sheets (RUN/frames/NAME-1.png, ...)

Keys and settings come from the environment, or from a .env file (KEY=value lines) for what the environment doesn't
set: the one in SHORTS_HOME, or one next to shorts/. GEMINI_API_KEY, SHORTS_SPEECH_URL and SHORTS_SPEECH_KEY, ... (see
.env.example).

Omni's Gemini client (film-intro, film-outro) is set up from the environment. For Agent Platform (Vertex AI), with
`gcloud auth application-default login` (or, in GitHub Actions, google-github-actions/auth):

    GOOGLE_GENAI_USE_ENTERPRISE=true GOOGLE_CLOUD_PROJECT=<project> GOOGLE_CLOUD_LOCATION=global

For the Gemini API (AI Studio): GEMINI_API_KEY=<key>.
"""

import argparse
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from . import COMMAND
from .browse import FALLBACK, MODEL
from .filmers import FILMERS, heygen_voices
from .home import MINE, home, keep, mine, signed_in_sites, site
from .orchestrator import PACKAGE_ROOT, advice, run_all, run_stage, status
from .run import SCRIPT, SETTINGS, Run, Settings, footage_file
from .script import LANGUAGES, TONES, Script, speed, words
from .stages import STAGES, NotReady, bring_in
from .stages.bring_in import PRODUCTS as IMPORTABLE
from .stages.bring_in import check_script

WINDOW = "the browser's window, WIDTHxHEIGHT: 720x1280 gets a site's phone layout, 1280x800 its desktop one"


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
    """A word and how the narrator should read it, such as nginx=engine-x."""
    word, _, said = text.partition("=")
    if not word or not said:
        raise argparse.ArgumentTypeError(f"{text!r} isn't a respelling like nginx=engine-x")
    return word, said


def new(run: Run, args: argparse.Namespace) -> None:
    """Writes run.json, or changes the settings given in it."""
    settings = run.settings()
    updates = {key: getattr(args, key) for key in Settings.model_fields if getattr(args, key, None) is not None}
    # (footage, narrator options and respellings come in one at a time, and are added to what's there)
    for key in ("face", "voice", "music"):  # "" for none
        if key in updates:
            updates[key] = run.relative(Path(updates[key])) if updates[key] else None
    for item in args.footage_items or []:
        name, _, source = item.partition("=")
        settings.footage[name] = run.relative(Path(source))
    if args.narrator_option:
        updates["narrator_options"] = {**settings.narrator_options, **dict(args.narrator_option)}
    if args.respellings:
        updates["pronounce"] = {**(settings.pronounce or {}), **dict(args.respellings)}
    run.save_settings(settings.model_copy(update=updates))
    print(run.path(SETTINGS).read_text())


# The keys a video needs (.env.example says what each is for): `me` says which are set, never what they are.
# Omni films with GEMINI_API_KEY, or on Google Cloud with GOOGLE_CLOUD_PROJECT; HeyGen only if it films you.
KEYS = ("GEMINI_API_KEY", "GOOGLE_CLOUD_PROJECT", "HEYGEN_API_KEY", "SHORTS_SPEECH_URL", "SHORTS_SPEECH_KEY")


def show_me(args: argparse.Namespace) -> None:
    """Keeps the files given (or forgets those given as ""), then says what's kept for every video."""
    for kind in MINE:
        file = getattr(args, kind)
        if file and not Path(file).expanduser().is_file():
            sys.exit(f"me: there's no file {file}")
        try:
            if file is not None:
                keep(kind, Path(file) if file else None)
        except ValueError as problem:
            sys.exit(f"me: {problem}")
    kept = mine()
    print(home())
    for kind in MINE:
        print(f"  {kind:10} {kept.get(kind, '(none)')}")
    products = sorted(path.stem for path in (home() / "products").glob("*.md"))
    print(f"  {'products':10} {', '.join(products) or '(none)'}")
    print(f"  {'signed in':10} {', '.join(signed_in_sites()) or '(nowhere)'}")
    unset = [key for key in KEYS if not os.environ.get(key)]
    print(f"  {'keys':10} set: {', '.join(key for key in KEYS if key not in unset) or 'none'}")
    print(f"  {'':10} not set: {', '.join(unset) or 'none'} (in {home() / '.env'}, or the environment)")


def sign_in(args: argparse.Namespace) -> None:
    """Signs in to a site by hand (`shorts.signin`), or forgets its sign-in."""
    from .signin import forget

    if args.forget:
        print(f"Forgot the sign-in to {site(args.url)}" if forget(args.url) else f"No sign-in to {site(args.url)}")
        return
    if importlib.util.find_spec("browser_use") is None:  # for the Chrome browser-use records with
        browse_elsewhere()
    from .signin import sign_in

    print(f"Chrome is open on {args.url}: sign in there, then close the window.", flush=True)
    profile = sign_in(args.url)
    print(f"Kept what {site(args.url)} saved, in {profile}: recordings with --signed-in start from it")


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


def browse_python() -> tuple[str, dict[str, str]]:
    """A Python with browser-use, and the environment to run shorts in it: this one, or SHORTS_BROWSE_PYTHON's
    (browser-use pins its own packages)."""
    if importlib.util.find_spec("browser_use") is not None:
        return sys.executable, dict(os.environ)
    python = os.path.expanduser(os.environ.get("SHORTS_BROWSE_PYTHON", ""))
    install = "uv venv ~/browse-env --python 3.12 && uv pip install --python ~/browse-env -e '.[browse]'"
    if os.environ.get("SHORTS_BROWSE_SENT"):  # this is that Python, and it hasn't browser-use either
        raise NotReady(f"SHORTS_BROWSE_PYTHON ({sys.executable}) hasn't browser-use either: {install}")
    if not python:
        raise NotReady(
            f"browser-use isn't installed here: set SHORTS_BROWSE_PYTHON to the Python of one that has it ({install})"
        )
    paths = [str(PACKAGE_ROOT), *filter(None, [os.environ.get("PYTHONPATH")])]
    return python, {**os.environ, "PYTHONPATH": os.pathsep.join(paths), "SHORTS_BROWSE_SENT": "1"}


def browse_elsewhere() -> None:
    """Runs this command in SHORTS_BROWSE_PYTHON, when this Python hasn't browser-use."""
    python, environment = browse_python()
    sys.exit(subprocess.run([python, "-m", "shorts", *sys.argv[1:]], env=environment).returncode)


# What each of drive's commands asks Chrome for: one of browser-use's actions, and its parameters.
ACTIONS = {
    "click": lambda args: ("click", {"index": args.number}),
    "type": lambda args: ("input", {"index": args.number, "text": args.text, "clear": not args.add}),
    "keys": lambda args: ("send_keys", {"keys": args.keys}),
    "scroll": lambda args: (
        "scroll",
        {"down": args.direction == "down", "pages": args.pages, **({"index": args.number} if args.number else {})},
    ),
    "tab": lambda args: ("switch", {"tab_id": args.tab}),
    "open": lambda args: ("navigate", {"url": args.url, "new_tab": args.new_tab}),
    "act": lambda args: (args.action_name, json.loads(args.params)),
}


def drive(run: Run, args: argparse.Namespace) -> None:
    """One of drive's commands (see shorts.drive): prints what the driver says, and the page as it is now."""
    from . import drive as driver

    goal = {"goal": args.goal} if getattr(args, "goal", None) else {}
    if args.step == "serve":
        chrome = driver.Driver(run, args.name, args.url, args.signed_in, args.window)
        asyncio.run(driver.serve(chrome, driver.driving_file(run, args.name)))
    elif args.step == "start":
        print(driver.start(run, args.name, args.url, args.signed_in, args.window, *browse_python()))
    elif args.step in ACTIONS:
        action, params = ACTIONS[args.step](args)
        spotlight = {"spotlight": True} if getattr(args, "spotlight", False) else {}
        print(driver.send(run, args.name, "act", action=action, params=params, **goal, **spotlight))
    elif args.step in ("wait", "hold"):
        print(driver.send(run, args.name, args.step, seconds=args.seconds, **goal))
    elif args.step == "wait-for":
        print(driver.send(run, args.name, "wait-for", text=args.text, timeout=args.timeout, **goal))
    elif args.step == "stop":
        print(driver.send(run, args.name, "stop", report=args.report, success=not args.failed))
    else:
        print(driver.send(run, args.name, args.step))


def main() -> None:
    for env in (home() / ".env", PACKAGE_ROOT / ".env"):  # first: the options' defaults come from the environment too
        load_env(env)
    parser = argparse.ArgumentParser(prog=COMMAND, description="Make a 1-minute video, stage by stage.")
    commands = parser.add_subparsers(dest="command", required=True)

    setup = commands.add_parser("new", help="write run.json, or change settings in it")
    setup.add_argument("run", type=Path)
    setup.add_argument("--footage", dest="footage_items", action="append", metavar="NAME=FILE")
    setup.add_argument("--face", help="a photo of you, for Omni")
    setup.add_argument("--voice", help="a sample of you talking, for --narration-voice sample")
    setup.add_argument("--music", help='music to play quietly under the video ("" for none)')
    setup.add_argument("--language", choices=LANGUAGES)
    setup.add_argument("--tone", choices=TONES)
    setup.add_argument("--intro", choices=[*FILMERS, "import"], help="who films the intro (shorts/filmers.py)")
    setup.add_argument("--outro", choices=[*FILMERS, "import", "none"], help="who films the outro, or none")
    setup.add_argument("--filmer-voice", help=f"the filmer's voice, for HeyGen: a voice_id ({COMMAND} voices)")
    setup.add_argument("--narrator", choices=["api", "import"])
    setup.add_argument("--narration-voice", choices=["intro", "sample"], help="the intro's voice, or --voice's")
    setup.add_argument("--narrator-model", help="the voice API's model: \"omnivoice\", or ElevenLabs' own")
    setup.add_argument("--narrator-option", type=option, action="append", metavar="KEY=VALUE")
    setup.add_argument("--pronounce", dest="respellings", type=respelling, action="append", metavar="WORD=SAID")
    setup.add_argument("--reference-text", help="what's said in the voice sample, for OmniVoice")
    setup.add_argument("--size", type=size, help="the video's width x height (default 1080x1920)")
    setup.add_argument("--captions", action=argparse.BooleanOptionalAction)

    me = commands.add_parser("me", help="your own files, kept for every video: a photo, music, a voice sample")
    for kind, what in (
        ("face", "a photo of you, for whoever films you"),
        ("music", "music to play quietly under your videos"),
        ("voice", "a sample of you talking, 3 to 10 seconds, to narrate in your voice"),
    ):
        me.add_argument(f"--{kind}", metavar="FILE", help=f'{what} ("" to forget it)')

    signing = commands.add_parser("signin", help="sign in to a site by hand, once, for recordings --signed-in")
    signing.add_argument("--url", required=True, help="the site's page to sign in on")
    signing.add_argument("--forget", action="store_true", help="delete the site's sign-in instead")

    commands.add_parser("status", help="what's made, and what's next").add_argument("run", type=Path)

    everything = commands.add_parser("run", help="every stage that's due, each in a process of its own")
    everything.add_argument("run", type=Path)
    everything.add_argument("--paid", action="store_true", help="film the intro and outro too, if due (about $1 each)")

    imported = commands.add_parser("import", help="bring in files made elsewhere")
    imported.add_argument("run", type=Path)
    imported.add_argument("product", choices=IMPORTABLE)
    imported.add_argument("files", nargs="+", help="files, or links to them")
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

    voices = commands.add_parser("voices", help="HeyGen's voices, for run.json's filmer_voice")
    voices.add_argument("--language", default="English", help='such as "English" or "Hindi" ("" for all)')
    voices.add_argument("--gender", choices=["male", "female"])

    record = commands.add_parser("browse", help="record footage from a task in plain words (browser-use)")
    record.add_argument("run", type=Path)
    record.add_argument("--name", default="demo", help="the footage's name, as the script calls it")
    record.add_argument("--task", type=Path, required=True, help="a text file: what to do and show, in plain words")
    record.add_argument("--url", required=True, help="the page it starts on: the product's")
    record.add_argument("--signed-in", action="store_true", help="signed in, as `signin` left the site")
    record.add_argument("--window", type=size, default=(720, 1280), help=WINDOW)
    record.add_argument("--max-steps", type=int, default=60)
    model = os.environ.get("SHORTS_BROWSE_MODEL") or MODEL
    record.add_argument("--model", default=model, help=f"provider:model, such as anthropic:... (default {model})")
    fallback = os.environ.get("SHORTS_BROWSE_FALLBACK", FALLBACK)
    record.add_argument("--fallback", default=fallback, help=f'when the model fails ("" for none; default {fallback})')

    driving = commands.add_parser("drive", help="record footage by driving Chrome a command at a time (Claude Code)")
    driving.add_argument("run", type=Path)
    steps = driving.add_subparsers(dest="step", required=True, metavar="COMMAND")

    def step(name: str, help: str, *, goal: bool = True) -> argparse.ArgumentParser:
        command = steps.add_parser(name, help=help)
        command.add_argument("--name", default="demo", help="the footage's name, as the script calls it")
        if goal:
            command.add_argument("--goal", help="what the step is for, as the steps file keeps it")
        return command

    for name, help in (("start", "open Chrome on --url and start recording"), ("serve", "(what start runs)")):
        opening = step(name, help, goal=False)
        opening.add_argument("--url", required=True, help="the page it starts on: the product's")
        opening.add_argument("--signed-in", action="store_true", help="signed in, as `signin` left the site")
        opening.add_argument("--window", type=size, default=(720, 1280), help=WINDOW)
    step("look", "the page: its tabs, its elements by number, and a screenshot", goal=False)
    clicking = step("click", "click an element")
    clicking.add_argument("number", type=int)
    typing = step("type", "type into an element (it's emptied first, unless --add)")
    typing.add_argument("number", type=int)
    typing.add_argument("text")
    typing.add_argument("--add", action="store_true", help="add to what's in it")
    for command in (clicking, typing):
        command.add_argument(
            "--spotlight", action="store_true", help="blur and dim the rest of the page meanwhile (not for a button)"
        )
    step("keys", "press keys, such as Enter or Control+a").add_argument("keys")
    scrolling = step("scroll", "scroll the page, or the element --number")
    scrolling.add_argument("direction", choices=["down", "up"])
    scrolling.add_argument("--pages", type=float, default=1.0, help="how far, in windows")
    scrolling.add_argument("--number", type=int, help="an element to scroll inside")
    step("wait", "wait, keeping only what changes on the page").add_argument("seconds", type=float)
    step("hold", "stay on the page, all of it kept: to end on the result").add_argument("seconds", type=float)
    until = step("wait-for", "wait until the page shows some text (fails if it never does)")
    until.add_argument("text")
    until.add_argument("--timeout", type=float, default=240.0, metavar="SECONDS")
    step("tab", "switch to a tab, by the id `look` shows").add_argument("tab")
    opening = step("open", "go to an address")
    opening.add_argument("url")
    opening.add_argument("--new-tab", action="store_true")
    other = step("act", "any other of browser-use's actions, such as go_back")
    other.add_argument("action_name", metavar="action")
    other.add_argument("params", nargs="?", default="{}", help="its parameters, as JSON")
    stopping = step("stop", "end the recording and bring it in as the footage", goal=False)
    stopping.add_argument("--report", default="", help="what it showed, and anything that went wrong")
    stopping.add_argument("--failed", action="store_true", help="it didn't show what it was for")

    for name, stage in STAGES.items():
        one = commands.add_parser(name, help=f"make the {stage.product}, here")
        one.add_argument("run", type=Path)
        one.add_argument("--force", action="store_true", help="make every file again, edited ones too")

    args = parser.parse_args()
    if args.command == "me":
        show_me(args)
        return
    if args.command == "signin":
        try:
            sign_in(args)
        except (NotReady, ValueError, RuntimeError) as problem:
            sys.exit(f"signin: {problem}")
        return
    if args.command == "voices":
        try:
            found = heygen_voices(args.language or None, args.gender)
        except (ValueError, RuntimeError) as problem:  # no key, or HeyGen said no
            sys.exit(f"voices: {problem}")
        for voice in found:
            about = f"{voice['name']} ({voice['language']}, {voice['gender']})"
            print(f"{voice['voice_id']}  {about}  {voice.get('preview_audio_url') or ''}")
        return
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

            options = {"url": args.url, "signed_in": args.signed_in, "window": args.window, "max_steps": args.max_steps}
            try:
                browse(
                    run, args.name, args.task.read_text(), model=args.model, fallback=args.fallback or None, **options
                )
            except RuntimeError as problem:  # Chrome couldn't open the signed-in profile: another Chrome has it
                sys.exit(f"browse: {problem}")
        elif args.command == "drive":
            drive(run, args)
        else:
            run_stage(run, args.command, force=args.force)
    except (NotReady, ValueError, FileNotFoundError) as problem:
        sys.exit(f"{args.command}: {problem}")


if __name__ == "__main__":
    main()
