"""The command line: set a video up, see where it is, and make it, a stage at a time or all that's left.

    python -m shorts me [--face PHOTO] [--music FILE] [--voice FILE]   your own files, kept for every video
                [--filmer omni|heygen|import|none] [--filmer-voice ID]   and your choices: who films you (none: no
                [--narrator elevenlabs|modal|kokoro|none] [--kokoro-voice VOICE]   avatar), and who speaks (none: no voice)
                                               (in SHORTS_HOME, ~/.config/makable-shorts: see shorts/home.py),
                                               the products' notes, where run folders go, and the keys you need
    python -m shorts keys [--open]             a line in SHORTS_HOME's .env for each key your choices need, for
                                               you to fill in (see shorts/keys.py)
    python -m shorts deploy-voice              the voice API, on your own Modal account (see shorts/deploy.py)
    python -m shorts signin --url URL          sign in to a site by hand, once, for recordings --signed-in
    python -m shorts new RUN [--face PHOTO] [--music FILE] [--language hi] [--tone hype]   a run, with your files
                [--format website]             a "useful website" Short of 20 to 30 s, with your kept sign-off
    python -m shorts trends [QUERY ...]        what's trending on YouTube Shorts, the outliers first (YOUTUBE_API_KEY;
                                               see shorts/trends.py)
    python -m shorts topics [--add SITE | --remove SITE]   the sites website Shorts were made about already
    python -m shorts sign-off [--from RUN | --clip FILE --line TEXT --language hi]   the clip of you signing off,
                                               kept for every website Short in its language
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
    python -m shorts hear RUN [--model NAME]   what Whisper hears in the narration and the clips, and the words
                                               that differ from the script, to listen to (see shorts/hear.py)

Keys and settings come from the environment, or from a .env file (KEY=value lines) for what the environment doesn't
set: the one in SHORTS_HOME, or one next to shorts/. Which keys depends on who films you and who speaks the narration
(`shorts.keys`): GOOGLE_CLOUD_PROJECT for Omni, signed in with `gcloud auth application-default login` (or, in
GitHub Actions, google-github-actions/auth), HEYGEN_API_KEY for HeyGen, and ELEVENLABS_API_KEY, or SHORTS_SPEECH_URL
and SHORTS_SPEECH_KEY for your own voice API (see .env.example). A video without an avatar, narrated by Kokoro or
with no voice, needs none.
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
from .filmers import FILMERS, heygen_voices
from .home import (
    MINE,
    choose,
    chosen,
    home,
    keep,
    keep_sign_off,
    mine,
    products,
    runs,
    sign_off,
    sign_offs,
    signed_in_sites,
    site,
)
from .keys import TRENDS, add, env_file, google_signed_in, load, needed, open_in_editor
from .orchestrator import PACKAGE_ROOT, advice, elsewhere, run_all, run_stage, shorts_in, status
from .run import FILMED_OUTRO, NARRATOR_MODELS, SCRIPT, SETTINGS, Run, Settings, file_hash, footage_file
from .script import LANGUAGES, TONES, Script, speed, tag_characters, words
from .stages import STAGES, NotReady, bring_in
from .stages.bring_in import PRODUCTS as IMPORTABLE
from .stages.bring_in import check_script
from .voice import KOKORO_VOICES

WINDOW = "the browser's window, WIDTHxHEIGHT: 720x1280 gets a site's phone layout, 1280x800 its desktop one"
HOOK_SECONDS = 4  # how long Omni films a website Short's intro, unless run.json says otherwise


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
    another = updates.get("narrator", settings.narrator) != settings.narrator
    if another and "narrator_model" not in updates:
        updates["narrator_model"] = None  # another API: its own model, not the one the last API spoke with
    if another or args.narrator_option:  # another narrator's options are its own: Kokoro takes none of an API's
        updates["narrator_options"] = {
            **({} if another else settings.narrator_options),
            **dict(args.narrator_option or []),
        }
    if args.respellings:
        updates["pronounce"] = {**(settings.pronounce or {}), **dict(args.respellings)}
    changed = settings.model_copy(update=updates)
    if changed.intro == "card" and changed.narrator in NARRATOR_MODELS and "narration_voice" not in updates:
        updates["narration_voice"] = "sample"  # no avatar to take a voice from: an API speaks in yours
    if changed.format == "website" and changed.intro_seconds is None and "intro_seconds" not in updates:
        updates["intro_seconds"] = HOOK_SECONDS
    run.save_settings(settings.model_copy(update=updates))
    if run.settings().format == "website":
        bring_in_sign_off(run)
    print(run.path(SETTINGS).read_text())


def bring_in_sign_off(run: Run) -> None:
    """In a website Short whose outro is a clip of you, brings in your sign-off in its language (`sign-off`) as the
    outro, if it isn't in already, so it's never filmed again. Without one, says the outro is filmed this time."""
    settings = run.settings()
    if settings.outro in ("card", "none"):
        return
    kept = sign_off(settings.language)
    if kept is None:
        print(
            f"There's no sign-off kept in {settings.language} yet: this video's outro is filmed ({settings.outro}), "
            f"and `{COMMAND} sign-off --from {run.folder}` keeps it for the next ones, once it's made"
        )
        return
    clip, line = kept
    there = run.path(FILMED_OUTRO)
    if settings.outro == "import" and there.exists() and file_hash(there) == file_hash(clip):
        if settings.sign_off_line != line:
            run.save_settings(settings.model_copy(update={"sign_off_line": line}))
        return
    print(f"The outro is your sign-off in {settings.language}: {line}")
    bring_in(run, "outro", [clip])
    run.save_settings(run.settings().model_copy(update={"sign_off_line": line}))


# Who can film you and who can speak the narration, for `me` to keep, as it says them.
FILMED_BY = {
    "omni": "Gemini Omni, in your Google Cloud project (about $1 a clip)",
    "heygen": "HeyGen, from your HeyGen API balance",
    "import": "clips you film elsewhere and bring in",
    "none": "no one: no avatar, the video opens on a title card",
}
NARRATED_BY = {
    "elevenlabs": "ElevenLabs",
    "modal": "your own voice API, on Modal",
    "kokoro": "Kokoro, on this machine, for nothing",
    "none": "no one: no voice, the captions say it",
}
CHOOSE = f"{COMMAND} me --filmer {'|'.join(FILMED_BY)} --narrator {'|'.join(NARRATED_BY)}"
UNASKED = ("SHORTS_SPEECH_URL", "SHORTS_SPEECH_KEY")  # the keys deploy-voice sets, not you


def show_me(args: argparse.Namespace) -> None:
    """Keeps the files and the choices given (or forgets those given as ""), then says what's kept for every video,
    and which keys the choices need (never what they are)."""
    for kind in MINE:
        file = getattr(args, kind)
        if file and not Path(file).expanduser().is_file():
            sys.exit(f"me: there's no file {file}")
        try:
            if file is not None:
                keep(kind, Path(file) if file else None)
        except ValueError as problem:
            sys.exit(f"me: {problem}")
    given = {
        "filmer": args.filmer,
        "filmer_voice": args.filmer_voice,
        "narrator": args.narrator,
        "kokoro_voice": args.kokoro_voice,
    }
    choices = choose(**given) if any(value is not None for value in given.values()) else chosen()
    kept = mine()
    print(home())
    for kind in MINE:
        print(f"  {kind:10} {kept.get(kind, '(none)')}")
    filmer, narrator = choices.get("filmer"), choices.get("narrator")
    filmed = FILMED_BY[filmer] if filmer else f"(not chosen: {COMMAND} me --filmer {'|'.join(FILMED_BY)})"
    if filmer == "heygen":
        voice = choices.get("filmer_voice")
        filmed += (
            f", in its voice {voice}" if voice else f": pick its voice ({COMMAND} voices, then me --filmer-voice ID)"
        )
    narrated = NARRATED_BY[narrator] if narrator else f"(not chosen: {COMMAND} me --narrator {'|'.join(NARRATED_BY)})"
    if narrator == "kokoro":
        voice = choices.get("kokoro_voice")
        narrated += f", in its voice {voice}" if voice else ", in its own voice for the video's language"
    elif narrator in ("elevenlabs", "modal"):
        narrated += ", in your voice sample's" if filmer == "none" else ", in your avatar's voice"
    print(f"  {'filmer':10} {filmed}")
    print(f"  {'narrator':10} {narrated}")
    notes = products() or {"(none)": ""}  # each product's notes, with where they are: in SHORTS_HOME or the project
    width = max(map(len, notes))
    for line, (name, path) in enumerate(notes.items()):
        print(f"  {'' if line else 'products':10} {name:{width}}  {path}".rstrip())
    print(f"  {'runs':10} {runs()}")
    print(f"  {'signed in':10} {', '.join(signed_in_sites()) or '(nowhere)'}")
    kept_sign_offs = sign_offs() or {"(none)": f"{COMMAND} sign-off keeps one, for website Shorts"}
    for line, (language, said) in enumerate(kept_sign_offs.items()):
        print(f"  {'' if line else 'sign-offs':10} {language}: {said}")
    trends_key = "set" if all(os.environ.get(key) for key in TRENDS) else f"not set ({COMMAND} keys --open --trends)"
    print(f"  {'trends':10} {', '.join(TRENDS)} {trends_key}")
    if not (filmer and narrator):
        print(f"  {'keys':10} (they depend on who films you and who speaks: choose them first)")
        return
    keys = needed(choices)
    unset = [key for key in keys if not os.environ.get(key)]
    print(f"  {'keys':10} set: {', '.join(key for key in keys if key not in unset) or 'none'}")
    where = f" (in {env_file()}: `{COMMAND} keys --open` adds their lines)" if unset else ""
    print(f"  {'':10} not set: {', '.join(unset) or 'none'}{where}")
    if filmer == "omni":
        signed = "signed in" if google_signed_in() else "not signed in: gcloud auth application-default login"
        print(f"  {'google':10} {signed}")


def show_keys(args: argparse.Namespace) -> None:
    """Adds a line to SHORTS_HOME's .env for each key your choices need, then says which are still empty, and with
    --open, opens it in your text editor if you've some to fill in."""
    choices = chosen()
    if not {"filmer", "narrator"} <= choices.keys() and not args.trends:
        sys.exit(f"keys: choose who films you and who speaks the narration first: {CHOOSE}")
    file, keys = env_file(), needed(choices) + (list(TRENDS) if args.trends else [])
    empty = add(keys, file)
    print(file)
    for key in keys:
        print(f"  {key:22} {'empty' if key in empty else 'set'}")
    if not keys:
        print("  (your choices need no keys)")
    if set(UNASKED) & set(empty):
        print(f"`{COMMAND} deploy-voice` deploys your voice API to Modal, and sets {' and '.join(UNASKED)}")
    if choices.get("filmer") == "omni" and not google_signed_in():
        print(
            "Google Cloud has no sign-in here yet: sign in once, in a terminal, with gcloud auth application-default login"
        )
    if args.open and set(empty) - set(UNASKED):
        print("Opened it in your text editor" if open_in_editor(file) else "Open it in a text editor to fill it in")


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
    settings = run.settings()
    intro, outro = (
        ("Title card" if settings.intro == "card" else "Hook" if settings.format == "website" else "Intro"),
        ("End card" if settings.outro == "card" else "Outro"),
    )
    print(f"{intro}, {words(script.intro_line)} words: {script.intro_line}")
    for number, scene in enumerate(script.scenes, 1):
        rate = speed(scene, silent=settings.narrator == "none")
        where = f"{scene.start:5.1f}-{scene.end:5.1f} s at {rate:.1f}x" if rate is not None else "(no stretch)"
        print(f"Scene {number}: {scene.footage} {where}, {words(scene.text)} words: {scene.text}")
    if script.outro_line:
        print(f"{outro}, {words(script.outro_line)} words: {script.outro_line}")
    if script.tags:
        print(f"Tags, {tag_characters(script.tags)} characters: {', '.join(script.tags)}")
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


def show_trends(args: argparse.Namespace) -> None:
    """What's trending on YouTube Shorts (`shorts.trends`), the outliers first."""
    from .trends import QUERIES, YouTubeError, find, listing

    try:
        found = find(
            args.queries or list(QUERIES),
            days=args.days,
            region=args.region,
            language=args.language,
            count=args.count,
            fresh=args.fresh,
            least_views=args.least_views,
        )
    except (ValueError, YouTubeError) as problem:
        sys.exit(f"trends: {problem}")
    if args.json:
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        print(json.dumps([item.summary(now) for item in found.trends[: args.top]], indent=1, ensure_ascii=False))
    else:
        print(listing(found, top=args.top))


def show_topics(args: argparse.Namespace) -> None:
    """The topics log: the sites website Shorts were made about, so `trends` marks Shorts about them."""
    from .trends import forget_site, log_site, made_sites, topics_file

    if args.add:
        run = str(Path(args.run).resolve()) if args.run else ""
        entry = log_site(args.add, about=args.about or "", run=run)
        print(f"Logged {entry['site']}: trends marks Shorts about it as made already")
    elif args.remove:
        print(f"Took {args.remove} out of the log" if forget_site(args.remove) else f"{args.remove} isn't in the log")
    sites = made_sites()
    print(topics_file())
    for entry in sites:
        about = f" ({entry['about']})" if entry.get("about") else ""
        print(f"  {entry['made']}  {entry['site']}{about}  {entry.get('run', '')}".rstrip())
    if not sites:
        print(f"  (none yet: {COMMAND} topics --add SITE, once its Short is made)")


def keep_sign_off_from(args: argparse.Namespace) -> None:
    """Keeps a clip of you signing off, for every website Short in its language: a run's outro, or a file."""
    if args.source:
        run = Run(args.source)
        clip = run.path(FILMED_OUTRO)
        if not clip.exists():
            sys.exit(f"sign-off: {run.folder} has no outro clip yet ({FILMED_OUTRO})")
        script = run.script() if run.path(SCRIPT).exists() else None
        line = args.line or (script.outro_line if script else "")
        language = args.language or (script.language if script else run.settings().language)
    elif args.clip:
        clip, line, language = Path(args.clip).expanduser(), args.line or "", args.language or ""
        if not clip.is_file():
            sys.exit(f"sign-off: there's no file {clip}")
        if not language:
            sys.exit("sign-off: say which language it's in: --language hi")
    else:
        for language, line in (sign_offs() or {}).items():
            print(f"{language}: {line}  ({home() / 'sign-offs' / f'{language}.mp4'})")
        if not sign_offs():
            print(f"No sign-off kept: {COMMAND} sign-off --from RUN keeps a run's outro, for every website Short")
        return
    try:
        kept = keep_sign_off(language, clip, line)
    except ValueError as problem:
        sys.exit(f"sign-off: {problem}")
    print(f"Kept {kept}: every website Short in {language} ends on it, saying: {line.strip()}")


def show_heard(run: Run, args: argparse.Namespace) -> None:
    """What Whisper hears in the run's narration and clips (`shorts.hear`), in the Python with faster-whisper."""
    if importlib.util.find_spec("faster_whisper") is None:
        python = os.path.expanduser(os.environ.get("SHORTS_WHISPER_PYTHON", ""))
        if not python or os.environ.get("SHORTS_WHISPER_SENT"):
            raise NotReady(
                "faster-whisper isn't installed here: pip install 'makable-shorts[whisper]', or set "
                "SHORTS_WHISPER_PYTHON to the Python of an environment that has it"
            )
        paths = [str(PACKAGE_ROOT), *filter(None, [os.environ.get("PYTHONPATH")])]
        environment = {**os.environ, "PYTHONPATH": os.pathsep.join(paths), "SHORTS_WHISPER_SENT": "1"}
        sys.exit(subprocess.run([python, "-m", "shorts", *sys.argv[1:]], env=environment).returncode)
    from .hear import hear, report

    print(report(run, hear(run, model=args.model)))


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
    for env in (env_file(), PACKAGE_ROOT / ".env"):  # first: the options' defaults come from the environment too
        load(env)
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
    setup.add_argument("--intro", choices=[*FILMERS, "import", "card"], help="who films the intro, or a title card")
    setup.add_argument(
        "--outro", choices=[*FILMERS, "import", "card", "none"], help="who films the outro, a card, or none"
    )
    setup.add_argument("--filmer-voice", help=f"the filmer's voice, for HeyGen: a voice_id ({COMMAND} voices)")
    setup.add_argument("--narrator", choices=[*NARRATOR_MODELS, "kokoro", "import", "none"], help="who speaks, or none")
    setup.add_argument("--narration-voice", choices=["intro", "sample"], help="the intro's voice, or --voice's")
    setup.add_argument("--kokoro-voice", help=f"Kokoro's voice: {', '.join(KOKORO_VOICES.values())}, am_michael, ...")
    models = ", ".join(f"{model!r} on {narrator}" for narrator, model in NARRATOR_MODELS.items())
    setup.add_argument("--narrator-model", help=f"the voice API's model, if not its own ({models})")
    setup.add_argument("--narrator-option", type=option, action="append", metavar="KEY=VALUE")
    setup.add_argument("--pronounce", dest="respellings", type=respelling, action="append", metavar="WORD=SAID")
    setup.add_argument("--reference-text", help="what's said in the voice sample, for OmniVoice")
    setup.add_argument("--size", type=size, help="the video's width x height (default 1080x1920)")
    setup.add_argument("--captions", action=argparse.BooleanOptionalAction)
    setup.add_argument(
        "--format", choices=["demo", "website"], help='a demo of your product, or a "useful website" Short'
    )
    setup.add_argument(
        "--intro-seconds", type=int, help=f"how long Omni films the intro, 3 to 10 (website: {HOOK_SECONDS})"
    )

    me = commands.add_parser("me", help="your own files and choices, kept for every video, and the keys you need")
    for kind, what in (
        ("face", "a photo of you, for whoever films you"),
        ("music", "music to play quietly under your videos"),
        ("voice", "a sample of you talking, 3 to 10 seconds, to narrate in your voice"),
    ):
        me.add_argument(f"--{kind}", metavar="FILE", help=f'{what} ("" to forget it)')
    me.add_argument("--filmer", choices=FILMED_BY, help="who films your intro and outro, from your photo")
    me.add_argument("--filmer-voice", metavar="ID", help=f"HeyGen's voice to film you in ({COMMAND} voices)")
    me.add_argument("--narrator", choices=NARRATED_BY, help="who speaks the narration, or none")
    me.add_argument("--kokoro-voice", metavar="VOICE", help='Kokoro\'s voice, such as am_michael ("" for its own)')

    keyed = commands.add_parser("keys", help="add the keys your choices need to your .env, for you to fill in")
    keyed.add_argument("--open", action="store_true", help="open it in your text editor, if there's a key to fill in")
    keyed.add_argument("--trends", action="store_true", help="and the key trends needs (YOUTUBE_API_KEY)")

    trending = commands.add_parser("trends", help="what's trending on YouTube Shorts, the outliers first")
    trending.add_argument(
        "queries", nargs="*", metavar="QUERY", help='what to search for (default: "useful website", ...)'
    )
    trending.add_argument("--days", type=int, default=14, help="posted in the last this many days")
    trending.add_argument("--region", default="IN", help="the country's YouTube to search: IN, US, ...")
    trending.add_argument("--language", default="hi", help="the language they're in: hi, en, ...")
    trending.add_argument("--count", type=int, default=25, help="how many Shorts each search finds, at most 50")
    trending.add_argument("--top", type=int, default=20, help="how many to show")
    trending.add_argument("--least-views", type=int, default=10_000, help="leave out Shorts with fewer views")
    trending.add_argument("--fresh", action="store_true", help="search again, though it was searched today")
    trending.add_argument("--json", action="store_true", help="as JSON, with each one's description and tags")

    topics = commands.add_parser("topics", help="the sites website Shorts were made about already")
    topics.add_argument("--add", metavar="SITE", help="log a site, once its Short is made")
    topics.add_argument("--about", help='the words it\'s about, comma-separated: "text to handwriting"')
    topics.add_argument("--run", help="the run folder it was made in")
    topics.add_argument("--remove", metavar="SITE", help="take a site out of the log")

    signing_off = commands.add_parser("sign-off", help="keep a clip of you signing off, for every website Short")
    signing_off.add_argument("--from", dest="source", type=Path, metavar="RUN", help="a run's outro, with its line")
    signing_off.add_argument("--clip", help="or a file: a clip of you saying the sign-off")
    signing_off.add_argument("--line", help="what it says (a run's: its script's outro line)")
    signing_off.add_argument("--language", help="the language it's in (a run's: its script's)")

    hearing = commands.add_parser("hear", help="what Whisper hears in the narration and the clips, against the script")
    hearing.add_argument("run", type=Path)
    hearing.add_argument("--model", default="large-v3-turbo", help="Whisper's model, as faster-whisper names it")

    commands.add_parser("deploy-voice", help="deploy the voice API to your own Modal account, and keep its key")

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
    if args.command == "keys":
        show_keys(args)
        return
    if args.command == "trends":
        show_trends(args)
        return
    if args.command == "topics":
        show_topics(args)
        return
    if args.command == "sign-off":
        keep_sign_off_from(args)
        return
    if args.command == "deploy-voice":
        from .deploy import deploy_voice, health

        try:
            address = deploy_voice()
        except (RuntimeError, FileNotFoundError) as problem:  # Modal said no, or there's no uv to run it with
            sys.exit(f"deploy-voice: {problem}")
        print(
            f"Your voice API is at {address}, speaking with {health(address)}: its address and key are in {env_file()}"
        )
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
    if args.command not in ("status", "check-script", "hear"):  # the rest write to it (hear, only once it's heard)
        run.make()
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
        elif args.command == "hear":
            show_heard(run, args)
        elif args.command == "drive":
            drive(run, args)
        elif python := elsewhere(run, args.command):  # in the Python with its packages
            sys.exit(shorts_in(python, *sys.argv[1:]))
        else:
            run_stage(run, args.command, force=args.force)
    except (NotReady, ValueError, FileNotFoundError) as problem:
        sys.exit(f"{args.command}: {problem}")


if __name__ == "__main__":
    main()
