"""Builds the Google Colab notebooks from the files in shorts/.

- makable_shorts.ipynb: the whole video.
- record_with_browser_use.ipynb: footage from instructions (browser-use pins its own google-genai and
  numpy, so it can't share a runtime with Chatterbox).
- voice_from_script.ipynb: the voices without the rest of the video: a voice taken from a recording (such
  as Omni's intro), a script's narration in it, and the intro converted to it.
- omnivoice_from_script.ipynb: a script's narration spoken by OmniVoice alone (no Chatterbox, so OmniVoice
  installs into Colab's own Python), where the Shorts notebook finds it.
- merge_intro.ipynb: the intro before a screen recording (merge_intro.py), on the CPU runtime.
- narrate_recording.ipynb: a screen recording narrated with scenes spoken already (narrate_recording.py), on
  the CPU runtime.

The notebooks write the same files with %%writefile, so Colab and GitHub Actions run the same code.
Run this after changing anything in shorts/:  python3 build_notebook.py
"""

import json
from pathlib import Path
from string import Template

ROOT = Path(__file__).parent
MODULES = [
    "__init__", "media", "script", "intro", "voice", "omnivoice_worker", "footage", "captions", "compose", "run",
    "speech_api", "sheet", "browse", "orchestrator", "__main__", "stages/__init__", "stages/base", "stages/record",
    "stages/write_script", "stages/film_intro", "stages/take_voice", "stages/revoice_intro", "stages/speak",
    "stages/assemble", "stages/bring_in",
]  # fmt: skip
ENGINE_MODULES = ["__init__", "media", "script", "captions", "compose"]  # merge_intro.py's and narrate_recording.py's
BROWSE_MODULES = ["__init__", "media", "browse", "signin"]
BROWSER_USE = "browser-use==0.13.11"  # browse.py uses its CDP session and events: test a newer one before moving

# The end of both Chatterbox installs. Chatterbox replaces Colab's torch with an older one, and a session that had
# loaded Colab's keeps its compiled half: the older one's Python files then fail to import against it ("cannot
# import name 'skip_code' from 'torch._C._dynamo.eval_frame'"). So that session restarts (Colab says it crashed).
RESTART_IF_STALE = """
import os
import sys
from importlib.metadata import version

def release(number):  # PyPI's torch says 2.6.0+cu124 when imported and 2.6.0 to pip
    return str(number).split("+")[0]


stale = [name for name in ("torch", "torchaudio", "transformers", "numpy")
         if name in sys.modules and release(sys.modules[name].__version__) != release(version(name))]
if stale:
    print(f"Restarting the session, which has the old {', '.join(stale)} loaded. Then go on from the next cell.", flush=True)
    os.kill(os.getpid(), 9)
"""


# The GPU notebooks run each stage as the command line does, in a process of its own (which hands the GPU's
# memory back when it's done), showing what it prints as it goes, progress bars too.
RUNNER = '''

import codecs
import subprocess


def shorts(*args):
    \"\"\"Runs `python -m shorts ARGS`: a stage, or `new` (settings), `status`, `import`, `run` (all that's due).\"\"\"
    command = [sys.executable, "-m", "shorts", *map(str, args)]
    process = subprocess.Popen(command, cwd="/content", stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = codecs.getincrementaldecoder("utf-8")(errors="replace")
    while chunk := process.stdout.read1(4096):
        print(text.decode(chunk), end="", flush=True)
    if process.wait():
        raise RuntimeError(f"python -m shorts {args[0]} stopped: see above")
'''


# Both GPU notebooks: the voice sample, made once from a recording (a video on Drive, or an upload).
# $recording is the notebook's RECORDING to start with.
VOICE_SAMPLE = Template("""
# The voice: up to 20 s of a recording's sound, from where the talking starts, made once and kept on Drive.
# RECORDING: a video or audio file (a video of you, or the intro Gemini Omni filmed), or a pattern such as
# HOME / "runs" / "*.mp4" (the newest match). None: assets/voice.wav, made the first time from the video in
# assets/ or makable-shorts/, or from a recording you upload. To make a sample again (say, from further in), delete it.
import glob

from google.colab import files

from shorts.media import duration
from shorts.voice import voice_sample

RECORDING = $recording
START = 0.0  # seconds into the recording to start from, if it doesn't start with the talking
VIDEOS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".3gp"}

VOICE_SAMPLE = ASSETS / "voice.wav"
if RECORDING is not None:
    matches = sorted(glob.glob(str(RECORDING)), key=os.path.getmtime)
    if not matches:
        raise FileNotFoundError(f"Nothing on Drive matches {RECORDING}")
    RECORDING = Path(matches[-1])
    VOICE_SAMPLE = ASSETS / f"voice-{RECORDING.stem}.wav"  # one sample per recording
if not VOICE_SAMPLE.exists():
    if RECORDING is None:
        videos = [path for folder in (ASSETS, HOME) if folder.is_dir() for path in sorted(folder.iterdir())]
        videos = [path for path in videos if path.suffix.lower() in VIDEOS]
        if len(videos) > 1:
            raise ValueError("Which video is you? Set RECORDING to one of:\\n" + "\\n".join(map(str, videos)))
        if videos:
            RECORDING = videos[0]
        else:
            print(f"No video in {ASSETS} or {HOME}. Choose a recording of you talking (any audio or video file):")
            uploads = files.upload()  # saved in /content
            if not uploads:
                raise FileNotFoundError(f"No recording: put a video of you in {ASSETS}, or set RECORDING")
            RECORDING = next(iter(uploads))
    voice_sample(Path(RECORDING), VOICE_SAMPLE, start=START)
    print(f"Made {VOICE_SAMPLE.name} from {RECORDING}")
print(f"The voice: {VOICE_SAMPLE} ({duration(VOICE_SAMPLE):.1f} s). Listen: it should be one person talking, nothing else.")
display(Audio(str(VOICE_SAMPLE)))
# The models load the first time they're needed. Chatterbox speaks LANGUAGE, reads the words in its
# shorts.voice.PRONOUNCE respelled (English "makable" as "makeable"), as lively as shorts.voice.DELIVERY says
# (exaggeration 0.7, cfg_weight 0.3). To change them: Voice(..., pronounce={"makable": "…"}, exaggeration=0.9)
voice = Voice(VOICE_SAMPLE, language=LANGUAGE)
""")


def voice_sample_cell(recording: str = "None") -> dict:
    return code(VOICE_SAMPLE.substitute(recording=recording))


def markdown(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip().splitlines(keepends=True)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": (text.strip("\n") + "\n").splitlines(keepends=True),
    }


def module_cells(names: list[str]) -> list[dict]:
    return [
        code(f"%%writefile /content/shorts/{name}.py\n" + (ROOT / "shorts" / f"{name}.py").read_text())
        for name in names
    ]


CELLS = [
    markdown("""
# makable Shorts

Makes a 1-minute vertical video about a change in makable, a stage at a time:

1. **record**: the footage, your screen recordings (or pages of the app, recorded by Playwright).
2. **write-script**: Gemini writes the intro line, the narration and the title (a fraction of a cent).
3. **film-intro**: Gemini Omni Flash films you saying the hook, from a photo (about **$1 a clip**, paid from your Google Cloud credits). Or bring in a clip filmed already.
4. **revoice-intro** and **speak**: Demucs takes the speech out of the intro and Chatterbox converts it to your voice (same words and timing, so the lips still match), then speaks each scene in the same voice (or OmniVoice speaks them: `NARRATOR` in section 1).
5. **assemble**: ffmpeg puts the intro and the scenes together, with captions and music: `final.mp4` (1080×1920) and `metadata.json` for the upload.

Each stage is a program of its own, the same `python -m shorts <stage> RUN` as on the command line, and the stages share nothing but the run's folder on Drive: each reads the files the ones before it wrote there, under fixed names, and writes its own. So any of them can be done elsewhere and brought in, such as scenes another tool spoke: `shorts("import", RUN, "narration", *files)`. `shorts("status", RUN)` shows what's made and what's next.

**Before you start**

- *Runtime → Change runtime type →* **T4 GPU**.
- **Agent Platform (Vertex AI)**, the default: a Google Cloud project on the billing account that holds your credits (the Free Trial's $300, Google AI Pro's $10 a month from developers.google.com/program/my-benefits), with the Agent Platform API turned on. Put its ID in `PROJECT` below. There's no key: Colab asks you to sign in with your Google account.
- Or **AI Studio**: set `USE_VERTEX = False` and add the Colab secret **`GEMINI_API_KEY`** (🔑 in the left sidebar). AI Studio only spends credits while you also have a prepaid balance (at least $5) above $0, and never the Free Trial's.
- In Google Drive, make `makable-shorts/assets/` with `voice.wav` (10–20 s of you talking, clean; or put a video of you talking there, and the notebook makes `voice.wav` from its sound), `face.jpg` (a photo of you, face clearly visible: only to film a new intro, see section 4) and, if you like, `music.mp3` (`MUSIC` in section 1).

It's set up for the Crumb & Co video: its run folder (`runs/crumb-and-co`, script written), the recording browser-use made of it, the intro Omni filmed for it, and no music.

A file is made again only when what it's made from changes (the scene's text, the voice sample, a setting), so you can run a cell again, restart the runtime, or edit `script.json`, and only what changed is made again. A file you edit by hand is kept as it is: to make it again anyway, delete it.
"""),
    markdown("""
## Setup

Chatterbox installs its own torch, older than Colab's. If the session had already loaded Colab's, the install cell restarts it (Colab says the session crashed): go on from the next cell. If Colab asks to restart the session, do that too.

pip lists conflicts with packages Colab already has, such as `google-adk` and `python-fasthtml` wanting a newer `starlette`. That's expected: nothing here uses them. Chatterbox's torch is older than Colab's, so the cell also removes Colab's `torchvision`, which was built for the newer one and can stop `transformers` (which Chatterbox uses) from importing.
"""),
    code("""
!pip install -q chatterbox-tts demucs playwright -U google-genai
!pip uninstall -q -y torchvision  # built for Colab's newer torch; nothing here uses it
!playwright install --with-deps chromium > /dev/null
""" + RESTART_IF_STALE),
    code("""
import os
import sys
from pathlib import Path

from google.colab import auth, drive, userdata

USE_VERTEX = True  # Agent Platform (Vertex AI), paid from Cloud credits; False: an AI Studio key
PROJECT = "project-00523b00-4ba9-44e7-9e2"  # the Cloud project on the billing account with your credits

drive.mount("/content/drive")
if USE_VERTEX:
    auth.authenticate_user()  # signs the notebook in as you, instead of an API key
    # The stages run as programs of their own, and set their Gemini client up from these.
    os.environ.update(GOOGLE_GENAI_USE_ENTERPRISE="true", GOOGLE_CLOUD_PROJECT=PROJECT, GOOGLE_CLOUD_LOCATION="global")
else:
    os.environ["GEMINI_API_KEY"] = userdata.get("GEMINI_API_KEY")

HOME = Path("/content/drive/MyDrive/makable-shorts")
ASSETS = HOME / "assets"
LANGUAGE = "en"  # what the video's in: "en", or "hi" for Hindi (written and spoken in it)
RUN = HOME / "runs" / ("crumb-and-co" if LANGUAGE == "en" else f"crumb-and-co-{LANGUAGE}")  # one folder per video
"""),
    markdown("""
## The pipeline's code

These cells write the `shorts` package to `/content/shorts`, the same files the command line (and later GitHub Actions) runs. Run them; there's nothing to change here.
"""),
    code('os.makedirs("/content/shorts/stages", exist_ok=True)'),
    *module_cells(MODULES),
    code("""
%load_ext autoreload
%autoreload 2
sys.path.insert(0, "/content")

from IPython.display import Audio, Video, display

from shorts.run import FILMED_INTRO, FILMED_OUTRO, FINAL, METADATA, SCRIPT, VOICED_INTRO, Run, narration_file
from shorts.voice import Voice

run = Run(RUN)
""" + RUNNER),
    voice_sample_cell(),
    markdown("""
## 1. The settings

The run's `run.json` says what the video is made from. This cell writes it, changing what's set here and keeping the rest.

- `FOOTAGE` names the recordings the scenes can use: each a video file (a screen recording you put in Drive, with its `.steps.json` when browser-use made it), or a page's URL, which Playwright records in a 720×1280 window (the app's phone layout), scrolling down it.
- `TONE = "hype"` writes the script the excited way Shorts creators talk: punchy sentences, exclamation marks, "look", "wait", and a turn before the best part. It goes with the voice notebook's "hype" deliveries and a voice sample said that way.
- `NARRATOR = "omnivoice"` has [OmniVoice](https://github.com/k2-fsa/OmniVoice) speak the scenes, in an environment of its own (it can't share Chatterbox's packages: a few minutes to install, once a session). Scenes `omnivoice_from_script.ipynb` spoke, from the same voice sample and with the same settings, are used as they are. Chatterbox still converts the intro, since OmniVoice only speaks text.
"""),
    code("""
FOOTAGE = {
    "makable": HOME / "recordings" / "makable-tight.mp4",  # Crumb & Co, recorded in record_with_browser_use.ipynb
    # "home": "https://makable.tech",  # or a page to record
}
CHANGES = ""  # what changed in makable, for a script about footage without steps
TONE = "friendly"  # or "hype": excited, like a Short
NARRATOR = "chatterbox"  # or "omnivoice"
MUSIC = None  # or ASSETS / "music.mp3", played quietly under the video

settings = ["--voice", VOICE_SAMPLE, "--face", ASSETS / "face.jpg", "--music", MUSIC or ""]
settings += ["--language", LANGUAGE, "--tone", TONE, "--narrator", NARRATOR]
for name, source in FOOTAGE.items():
    settings += ["--footage", f"{name}={source}"]
if CHANGES:
    run.path("changes.txt").write_text(CHANGES)
    settings += ["--changes", run.path("changes.txt")]
shorts("new", RUN, *settings)
shorts("status", RUN)
"""),
    markdown("""
## 2. The footage

Each recording in `FOOTAGE`, copied into the run's folder (with its steps), and each page recorded.
"""),
    code('shorts("record", RUN)'),
    markdown("""
## 3. The script

Read it before the paid step. It's written from the steps of the recording browser-use made, so each scene says what's on screen and plays the stretch of the recording it's about (leaving out retries and errors); for footage without steps, it's written from `CHANGES`.

To change what's said, edit `script.json` in the run's folder: an edited script is kept as it is. To get a new one (in another tone, say), delete it and run the cell again.
"""),
    code("""
shorts("write-script", RUN)
print(run.path(SCRIPT).read_text())
"""),
    markdown("""
## 4. The intro

`INTRO` is the clip Omni filmed for Crumb & Co: it's brought in, and nothing is filmed. With `INTRO = None`, Omni films you from `face.jpg` saying `intro_line` (about $1), and films again only when the line, its setting or the photo changes. Watch it: if it said something else, delete `intro/filmed.mp4` and run the cell again (the captions show `intro_line`). Omni refuses some photos of people; if it does, try another photo.
"""),
    code("""
import glob

INTRO = HOME / "crumb-and-co" / "runs" / "intro-*.mp4"  # a clip filmed already, or a pattern (the newest match)

if INTRO is None:
    shorts("new", RUN, "--intro", "omni")
    shorts("film-intro", RUN)
else:
    clips = sorted(glob.glob(str(INTRO)), key=os.path.getmtime)
    if not clips:
        raise FileNotFoundError(f"Nothing on Drive matches {INTRO}: set INTRO to Omni's clip, or None to film one")
    shorts("import", RUN, "intro", clips[-1])
display(Video(str(run.path(FILMED_INTRO)), embed=True, width=270))
"""),
    markdown("""
### The outro

With `OUTRO = True`, Omni also films you saying the script's `outro_line` (about $1), in the intro's setting, and the video ends on it, as filmed. A script without an `outro_line` (one written before outros) has none to film.
"""),
    code("""
OUTRO = False

if OUTRO:
    shorts("new", RUN, "--outro", "omni")
    shorts("film-outro", RUN)
    display(Video(str(run.path(FILMED_OUTRO)), embed=True, width=270))
"""),
    markdown("""
## 5. The voices

The intro's speech in your voice (with the clip's background sound under it), then each scene's narration. Only the scenes whose text, voice sample or narrator settings changed are spoken again.
"""),
    code("""
shorts("revoice-intro", RUN)
shorts("speak", RUN)
display(Video(str(run.path(VOICED_INTRO)), embed=True, width=270))
for index in range(len(run.script().scenes)):
    display(Audio(str(run.path(narration_file(index)))))
"""),
    markdown("""
## 6. The video
"""),
    code("""
shorts("assemble", RUN)
display(Video(str(run.path(FINAL)), embed=True, width=270))
print(run.path(METADATA).read_text())
"""),
    markdown("""
## All that's left, in one go

What the cells above do, a stage after another: every file that's missing or out of date, and nothing else. It never films the intro on its own, since that costs money: `shorts("run", RUN, "--paid")` does.
"""),
    code('shorts("run", RUN)'),
    markdown("""
## Later: GitHub Actions

The `shorts` package goes into a repo of its own, and the job runs the same commands:

```sh
python -m shorts new runs/<commit> --changes changes.txt --footage editor=… --voice assets/voice.wav --face assets/face.jpg
python -m shorts run runs/<commit> --paid
```

GitHub's runners have no GPU, so Chatterbox and Demucs run on the CPU there (slower, to be measured), or `revoice-intro` and `speak` run here and the job brings their files in.
"""),
]


BROWSE_CELLS = [
    markdown("""
# Record the app from instructions (browser-use)

You say what to show in plain words, and [browser-use](https://github.com/browser-use/browser-use)'s agent does it in Chromium while the screen is recorded. At each step the model gets the page (its elements and a screenshot) and picks the next clicks and typing. It needs no selectors, and it copes when the page changes.

You get two videos, each with its steps:

- `<name>.mp4`: the whole run in real time, including the seconds the model spends thinking between steps (the page sits still).
- `<name>-tight.mp4`: the same without those pauses. Each step runs from just before its actions to when the page settles, typing plays 4× as fast, and it zooms in on each click (1.5×) and back out. While the agent waits (30 s at a time while makable builds), only what changes on the page is kept, from half a second before each change to a second after.
- `<name>.steps.json` for each: every step's goal, what it did ("Clicked button Add"), when, in seconds into that video, and where it clicked. The Shorts notebook writes the script from these (section 2): each scene says what's on screen over the stretch of the recording it's about.

**Before you start**

- A **CPU** runtime is enough (no GPU).
- This is a separate notebook because browser-use pins its own `google-genai` and `numpy`, and the Shorts notebook (Chatterbox, Omni) can't use those.
- The model is `MODEL`, as provider:model: Gemini through its API (`google:…`, with the `GEMINI_API_KEY` secret), on **Agent Platform** (`vertex:…`, with the Shorts notebook's project and sign-in), Claude (`anthropic:…`, `ANTHROPIC_API_KEY`) or GPT (`openai:…`, `OPENAI_API_KEY`). Each step sends the page and a screenshot (several thousand tokens), so a 10-step recording costs cents on Flash.
- The page has to be reachable from Colab. Section 3 records makable signed in, as a demo user with a password instead of GitHub (set up once: see the README's *Recording makable signed in*).
"""),
    markdown("""
## Setup

browser-use pins versions of packages Colab already has, so pip lists conflicts with Colab's own (`google-colab`, `bigframes`, `google-adk`, `huggingface-hub`). That's expected; this notebook doesn't use those. After the install, restart the session (*Runtime → Restart session*) so no old versions stay loaded, then go on from the next cell.
"""),
    code(f"""
!pip install -q {BROWSER_USE} playwright
!playwright install --with-deps chromium > /dev/null  # browser-use runs Playwright's Chromium
"""),
    code("""
import os
from pathlib import Path

from google.colab import auth, drive, userdata

MODEL = "google:gemini-3.6-flash"  # provider:model: google (the Gemini API), vertex, anthropic or openai
FALLBACK_MODEL = "google:gemini-3-flash-preview"  # for the rest of a run once MODEL answers 429 or 5xx
PROJECT = "project-00523b00-4ba9-44e7-9e2"  # for vertex: Agent Platform, paid from Cloud credits

drive.mount("/content/drive")
KEYS = {"google": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
for spec in (MODEL, FALLBACK_MODEL):
    provider = spec.partition(":")[0]
    if provider == "vertex":
        auth.authenticate_user()
        os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT
    elif provider in KEYS:
        os.environ[KEYS[provider]] = userdata.get(KEYS[provider])

OUT = Path("/content/drive/MyDrive/makable-shorts/recordings")
"""),
    code('os.makedirs("/content/shorts", exist_ok=True)'),
    *module_cells(BROWSE_MODULES),
    code("""
%load_ext autoreload
%autoreload 2
import sys

sys.path.insert(0, "/content")

from IPython.display import Video, display

from shorts.browse import chat_model, cut_pauses, record_task
from shorts.signin import signed_in

llm, fallback = chat_model(MODEL), chat_model(FALLBACK_MODEL)
print("model:", llm.model, "| fallback:", fallback.model)


def show(video, steps):
    display(Video(str(video), embed=True, width=270))
    for step in steps:
        print(f"{step.start:5.1f}-{step.end:5.1f}s  {step.goal}")
        for did in step.did:
            print(f"               {did}")
"""),
    markdown("""
## 1. Record

Say what to show, in order, the way you'd tell a person. The recording starts with the page in `URL` already open, in a 720×1280 window (the phone layout). Watch the log: each step prints what the model saw and decided.
"""),
    code('''
URL = "https://demo.playwright.dev/todomvc"
TASK = """
Add three todos, one at a time: "Buy flour", "Bake sourdough" and "Open the shop".
Then mark "Bake sourdough" as done, and show only the active todos.
"""

video, steps = await record_task(TASK, OUT / "todo.mp4", llm, fallback=fallback, url=URL)
show(video, steps)
'''),
    markdown("""
## 2. Without the model's pauses
"""),
    code("""
tight, tight_steps = cut_pauses(video, steps, OUT / "todo-tight.mp4")
show(tight, tight_steps)
"""),
    markdown("""
## 3. makable, signed in as the demo user

browser-use can't do GitHub's sign-in, so the demo user also has a password in Supabase. `signed_in` asks Supabase for a new session with it and gives Chrome the two cookies makable sets after a GitHub sign-in, so the recording opens signed in. It first asks makable who that is, so a wrong setup fails here instead of recording the signed-out page.

It reads four Colab secrets (🔑 in the left bar): `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `MAKABLE_DEMO_EMAIL` and `MAKABLE_DEMO_PASSWORD`.

The agent really uses the site: a site it builds or publishes is made on the demo account's GitHub.
"""),
    code('''
APP_URL = "https://makable.tech"
TASK = """
You're testing makable, an AI website builder, in a phone-sized window. You're already signed in as a demo user.
Build a new website from start to finish and check that each part works.

1. Start a new site. If the page has a box that says "Describe the site you want to build…", use it.
   If one of your sites opens instead (a chat with a preview of a site under it), first open the menu
   with the site's name at the top of the chat and choose "New site".
   Type this into the box as one line (a line break presses Enter, which sends it), then send it:
   "A one-page website for Crumb & Co, a small neighbourhood bakery: a hero with the bakery's name and a short tagline, a menu of 6 breads and pastries with prices, opening hours, and a contact section with an address and a phone number."

2. makable starts building the site in a chat. If it asks for the site's name, type "Crumb & Co" in the
   chat's box and send it (or click it, if it's one of the suggested names). Answer any other question
   with a short, sensible answer that fits a bakery. If makable says it needs an AI model or an API key,
   stop and report that.

3. Building takes a few minutes. While it works, the chat shows its progress steps and a timer counting
   the seconds. Wait for it: use the wait action for 30 seconds at a time, then look at the page again.
   Don't reload the page, and don't click Stop, Cancel or anything else while it's building.
   Give up if the progress steps haven't moved for 5 minutes, or after 10 minutes in all.

4. When it's done, the chat is at the top and a live preview of the site is under it. Wait until the
   preview's toolbar says "Live preview" (not "Building preview…" or "Preview error"). Check that the
   preview shows the bakery's name, the menu with prices, the opening hours and the contact section.
   Scroll inside the preview to see all of it.

5. Ask for one change in the chat's box ("Ask for a change to your site…"), typed as one line:
   "Make the hero background a warm cream colour and add an 'Order for pickup' button."
   Wait for it the same way (give up after 5 minutes), then check that the preview shows the change.

Don't publish the site, don't change any settings, don't click Undo and don't sign out.

At the end, call done with success true only if every step worked. In its text, report whether each step
worked, anything that looked broken (an error message, a blank or empty preview, a step that never
finished), and roughly how long the build and the change each took (from the chat's timer).
"""


def demo_cookies():  # a new session for each recording (the site rotates its refresh token as it goes)
    return signed_in(
        APP_URL,
        userdata.get("SUPABASE_URL"),
        userdata.get("SUPABASE_PUBLISHABLE_KEY"),
        userdata.get("MAKABLE_DEMO_EMAIL"),
        userdata.get("MAKABLE_DEMO_PASSWORD"),
    )


# Each 30 s wait is a step, and a build takes minutes: 25 steps (the default) runs out before the change.
video, steps = await record_task(
    TASK, OUT / "makable.mp4", llm, fallback=fallback, url=APP_URL, cookies=demo_cookies(), max_steps=60
)
show(video, steps)
tight, tight_steps = cut_pauses(video, steps, OUT / "makable-tight.mp4")
show(tight, tight_steps)
'''),
]


VOICE_CELLS = [
    markdown("""
# makable Shorts: the voices

The voices without the rest of the video, made in the run's folder on Drive, where the Shorts notebook (and `python -m shorts`) use them as they are:

1. **The voice**: taken from a recording's sound, such as the intro Gemini Omni filmed, or a video of you. Chatterbox clones it.
2. **The narration** (the `speak` stage): Chatterbox speaks each scene of a script in that voice, `narration/01.wav` and on. Use it to hear a script before making the video, say one written from a recording's steps, and to try Chatterbox's settings (section 2), which then go in the run's `run.json`.
3. **The intro, when the voice came from another recording** (`revoice-intro`): Omni's clip has Omni's voice. Its speech is separated from the background (Demucs) and converted to the cloned voice, keeping the words and timing so the lips still match: `intro/voiced.mp4`.

**Before you start**

- *Runtime → Change runtime type →* **T4 GPU**.
- The recording to take the voice from, on Google Drive. In the voice's cell, `RECORDING` is its path, or a pattern like `…/intro-*.mp4` (the newest match). It's set to the Crumb & Co intro.
- `LANGUAGE` in the setup cell: `"en"` or `"hi"` for Hindi. Hindi is spoken by Chatterbox's multilingual model (its first run downloads it), and its runs get a folder of their own.
"""),
    markdown("""
## Setup

Chatterbox installs its own torch, older than Colab's. If the session had already loaded Colab's, the install cell restarts it (Colab says the session crashed): go on from the next cell. If Colab asks to restart the session, do that too.

pip lists conflicts with packages Colab already has, such as `google-adk` and `python-fasthtml` wanting a newer `starlette`. That's expected: nothing here uses them. Chatterbox's torch is older than Colab's, so the cell also removes Colab's `torchvision`, which was built for the newer one and can stop `transformers` (which Chatterbox uses) from importing.
"""),
    code("""
!pip install -q chatterbox-tts demucs
!pip uninstall -q -y torchvision  # built for Colab's newer torch; nothing here uses it
""" + RESTART_IF_STALE),
    code("""
import os
import sys
from pathlib import Path

from google.colab import drive

drive.mount("/content/drive")

HOME = Path("/content/drive/MyDrive/makable-shorts")
ASSETS = HOME / "assets"
LANGUAGE = "en"  # what the script and narration are in: "en", or "hi" for Hindi
# One folder per video (and language): the Shorts notebook's RUN, to go on there.
RUN = HOME / "runs" / ("crumb-and-co" if LANGUAGE == "en" else f"crumb-and-co-{LANGUAGE}")
"""),
    code('os.makedirs("/content/shorts/stages", exist_ok=True)'),
    *module_cells(MODULES),
    code("""
%load_ext autoreload
%autoreload 2
sys.path.insert(0, "/content")

from IPython.display import Audio, Video, display

from shorts.run import FILMED_INTRO, VOICED_INTRO, Run, file_hash, fingerprint, narration_file
from shorts.script import WORDS_PER_SECOND
from shorts.voice import Voice

run = Run(RUN)
TRIES = run.folder / "tries"  # takes to choose from (section 2), apart from the video's own files


def take(voice, text):
    \"\"\"`voice` saying `text`: said once, and kept in TRIES.\"\"\"
    out = TRIES / f"{fingerprint(voice.settings, voice.spoken(text), file_hash(voice.reference))}.wav"
    if not out.exists():
        TRIES.mkdir(parents=True, exist_ok=True)
        voice.say(text, out)
    return out
""" + RUNNER),
    markdown("""
## The voice

From `RECORDING`'s sound: up to 20 s, from where the talking starts, saved in `assets/` as `voice-<recording>.wav`. Listen to it: it should be one person talking and nothing else, because Chatterbox copies the room and any background sound along with the voice. With `RECORDING = None`, the voice is `assets/voice.wav`, the Shorts notebook's.
"""),
    voice_sample_cell('HOME / "crumb-and-co" / "runs" / "intro-*.mp4"'),
    markdown("""
## 1. The script

Paste a script's JSON (a `script.json` the Shorts notebook wrote, or one written from a recording's steps), or set `SCRIPT` to a script.json on Drive. These two were written from `makable-tight.steps.json`, in English and in Hindi; `LANGUAGE` picks one.

If the run's folder has no `script.json` yet, the script is brought in there, so the Shorts notebook goes on with it. The voice sample goes in the run's `run.json`, for the narration.
"""),
    code('''
SCRIPTS = {
    "en": """
{
  "intro_line": "Watch me build and customize a complete bakery website with an AI builder in under one minute.",
  "intro_setting": "A bright modern kitchen with morning sunlight streaming through large windows, framed in a medium close-up.",
  "scenes": [
    {"text": "We open Makable, click New Site, and start building a website for a local bakery.", "footage": "makable", "start": 0.0, "end": 5.8},
    {"text": "We type our prompt for a hero banner, six priced pastries, opening hours, and contact info.", "footage": "makable", "start": 5.8, "end": 11.6},
    {"text": "We name the bakery Crumb and Co Shop, and Makable gets straight to work generating the layout step by step.", "footage": "makable", "start": 18.8, "end": 27.5},
    {"text": "The live preview loads up with six priced pastries from sourdough to croissants, opening hours, and bakery contact info.", "footage": "makable", "start": 27.5, "end": 36.8},
    {"text": "To refine the look, we ask the chat to switch the hero background to warm cream and add a pickup button.", "footage": "makable", "start": 54.0, "end": 62.9},
    {"text": "The preview updates with our warm cream header and new order button. Head over and try Makable today.", "footage": "makable", "start": 62.9, "end": 69.5}
  ],
  "title": "Building a Bakery Website with AI in Seconds",
  "description": "See how Makable builds a complete bakery website from a single prompt with menu pricing, hours, and contact info. Watch us refine the design with a custom color palette and order button. Try Makable today to create your own website."
}
""",
    "hi": """
{
  "intro_line": "क्या एआई सच में सिर्फ एक प्रॉम्प्ट से पूरी बेकरी वेबसाइट तैयार कर सकता है? चलिए आज लाइव देखते हैं!",
  "intro_setting": "Modern studio desk with warm ambient lighting and soft neon accents, framed in a tight vertical shot.",
  "scenes": [
    {"text": "सबसे पहले मेन्यू से न्यू साइट चुनते हैं और प्रॉम्प्ट में अपनी बेकरी का पूरा मेन्यू, टाइमिंग और कॉन्टैक्ट डिटेल्स लिखकर एंटर करते हैं।", "footage": "makable", "start": 0.6, "end": 10.1},
    {"text": "साइट का नाम सिलेक्ट करते ही बिल्डिंग प्रोसेस शुरू हो गया।", "footage": "makable", "start": 10.1, "end": 14.0},
    {"text": "सिर्फ छत्तीस सेकंड में makable ने पूरी वेबसाइट तैयार कर दी! लाइव प्रीव्यू में क्रंब एंड को का हीरो सेक्शन, छह बेकरी आइटम्स के साथ उनके प्राइसेस, दुकान की टाइमिंग और फोन नंबर सब कुछ बिल्कुल परफेक्ट दिख रहा है।", "footage": "makable", "start": 18.8, "end": 36.2},
    {"text": "अब इसमें थोड़ा बदलाव करते हैं। हमने चैट में लिखा कि हीरो बैकग्राउंड क्रीम कलर का कर दो और पिकअप बटन जोड़ दो।", "footage": "makable", "start": 54.5, "end": 62.9},
    {"text": "और देखिए, क्रीम बैकग्राउंड के साथ नया बटन भी आ गया! आप भी makable पर अपनी वेबसाइट जरूर बनाइए।", "footage": "makable", "start": 62.9, "end": 69.5}
  ],
  "title": "AI से मिनटों में बेकरी वेबसाइट कैसे बनाएं? makable रिव्यू",
  "description": "देखिए कैसे makable ने सिर्फ एक प्रॉम्प्ट में पूरी बेकरी वेबसाइट तैयार कर दी। इसमें मेन्यू, प्राइसेस और टाइमिंग के साथ लाइव कस्टमाइजेशन भी चुटकियों में हो गया। आप भी makable ट्राई करके अपनी वेबसाइट आसानी से बना सकते हैं।",
  "language": "hi"
}
""",
}
SCRIPT = SCRIPTS[LANGUAGE]  # or a file: SCRIPT = HOME / "runs" / "first-test" / "script.json"

if not run.path("script.json").exists():
    if not isinstance(SCRIPT, Path):
        Path("/content/script.json").write_text(SCRIPT)
        SCRIPT = Path("/content/script.json")
    shorts("import", RUN, "script", SCRIPT)
shorts("new", RUN, "--voice", VOICE_SAMPLE, "--language", LANGUAGE)
script = run.script()
for index, scene in enumerate(script.scenes, 1):
    print(f"{index}. {scene.text}")
'''),
    markdown("""
## 2. How it's said

Two things to choose by ear before the whole script is spoken: how Chatterbox says makable, and how lively it sounds.

### Saying makable

Chatterbox has no pronunciation setting, so a word it says wrong is respelled in what it reads; the captions keep the script's spelling. This says one sentence with a few spellings. Put the one that sounds right in the run's settings, `shorts("new", RUN, "--pronounce", "makable=…")`, or in `PRONOUNCE` in `shorts/voice.py` for every video.
"""),
    code("""
WORD = "makable"
SPELLINGS = {  # add your own
    "en": ["makeable", "make-a-bull", "may-kuh-bul", "mayk-uh-bul", "make-able"],
    "hi": ["मेकेबल", "मेकएबल", "मेक-एबल", "मेकबल", "makeable"],
}[LANGUAGE]
SENTENCE = {"en": "Head over and try makable today.", "hi": "आज ही makable ट्राई कीजिए।"}[LANGUAGE]

for spelling in SPELLINGS:
    trial = Voice(VOICE_SAMPLE, LANGUAGE, pronounce={**voice.pronounce, WORD: spelling}, **voice.tts_options)
    print(trial.spoken(SENTENCE))
    display(Audio(str(take(trial, SENTENCE))))
"""),
    markdown("""
### The delivery

How lively the narration sounds comes from three things:

- **The voice sample.** Chatterbox copies how it's said along with the voice, so a flat sample gives a flat narration. A sample said upbeat and with a smile, not shouted, gives you that. For the "hype" tries, record one said like a Short: fast, without stopping between sentences, your voice going up on the words that matter.
- **Two dials.** `exaggeration` is how much feeling (Chatterbox's default is 0.5; higher is livelier, and faster). `cfg_weight` is how closely it keeps to the sample's pace (default 0.5; lower is slower and looser, which balances a high exaggeration). `shorts.voice.DELIVERY` sets 0.7 and 0.3, Chatterbox's own suggestion for expressive speech. The "hype" tries keep `cfg_weight` at 0.5, since a Short is fast, and go higher on `exaggeration`: too high, and it slurs and drifts from your voice.
- **The words.** Short sentences, and an exclamation mark where something good happens, tend to be said with more lift.

For Hindi from an English voice sample (or any sample in another language), Chatterbox can carry the sample's accent over; its fix is `cfg_weight` 0, the last try.

This speaks one scene a few ways. Put the one you like in the run's settings, `shorts("new", RUN, "--narrator-option", "exaggeration=0.9", "--narrator-option", "cfg_weight=0.3")` (or in `DELIVERY` in `shorts/voice.py`, for every video), then run the narration.
"""),
    code("""
SCENE = len(script.scenes)  # the scene to try, from 1: the last one, the payoff, is a good test
DELIVERIES = {
    "Chatterbox's default": {"exaggeration": 0.5, "cfg_weight": 0.5},
    "warm": {"exaggeration": 0.6, "cfg_weight": 0.4},
    "lively": {"exaggeration": 0.7, "cfg_weight": 0.3},
    "excited": {"exaggeration": 0.9, "cfg_weight": 0.3},
    "hype": {"exaggeration": 1.0, "cfg_weight": 0.5},  # fast and excited, like a Short
    "hype, more": {"exaggeration": 1.3, "cfg_weight": 0.5},
    "lively, no accent carried over": {"exaggeration": 0.7, "cfg_weight": 0.0},  # a sample in another language
}

text = script.scenes[SCENE - 1].text
print(text)
for name, delivery in DELIVERIES.items():
    wav = take(Voice(VOICE_SAMPLE, LANGUAGE, pronounce=voice.pronounce, **delivery), text)
    print(f"{name}, {delivery}: {duration(wav):.1f} s")
    display(Audio(str(wav)))
"""),
    markdown("""
## 3. The narration

The `speak` stage, with the run's settings. The first time, Chatterbox downloads its models (a minute or two); then each scene takes a few seconds. Scenes already spoken with the same text, voice sample and settings aren't spoken again.

Under each scene: how long it's spoken and how fast, and for a script written from steps, how long its stretch of the recording is. The video plays the stretch at the speed that fits the scene's narration, so a scene spoken much longer or shorter than its stretch plays it slow or fast. If the speed is far from what the script assumes, change `WORDS_PER_SECOND` in `script.py`.
"""),
    code("""
shorts("speak", RUN)
script = run.script()
spoken = 0.0
for index, scene in enumerate(script.scenes):
    wav = run.path(narration_file(index))
    seconds = duration(wav)
    spoken += seconds
    stretch = f", over {scene.end - scene.start:.1f} s of {scene.footage}" if scene.start is not None else ""
    print(f"{index + 1}. {seconds:.1f} s, {len(scene.text.split()) / seconds:.1f} words a second{stretch}: {scene.text}")
    display(Audio(str(wav)))
words = sum(len(scene.text.split()) for scene in script.scenes)
print(f"In all: {spoken:.1f} s, {words / spoken:.2f} words a second (the script assumes {WORDS_PER_SECOND:g})")
"""),
    markdown("""
## 4. The intro in the cloned voice

Only when the voice came from another recording than the intro: if it came from the intro, the intro already has it, so skip this (and set `shorts("new", RUN, "--intro-voice", "as-filmed")`, for the video to use the clip as it is).

The `revoice-intro` stage: it takes the sound out of Omni's clip, separates the speech from the background (Demucs, about a minute), converts the speech to the cloned voice and puts the background back under it, quieter. Below: the clip as Omni made it, then in the cloned voice, to check that the lips still match. A clip that's been done with this voice sample already isn't done again.
"""),
    code("""
INTRO = HOME / "crumb-and-co" / "runs" / "intro-*.mp4"  # Omni's clip, or a pattern (the newest match); None: the run's

if INTRO is not None:
    clips = sorted(glob.glob(str(INTRO)), key=os.path.getmtime)
    if not clips:
        raise FileNotFoundError(f"Nothing on Drive matches {INTRO}: set INTRO to Omni's clip")
    shorts("import", RUN, "intro", clips[-1])
shorts("revoice-intro", RUN)
print("As Omni made it:")
display(Video(str(run.path(FILMED_INTRO)), embed=True, width=270))
print("In the cloned voice:")
display(Video(str(run.path(VOICED_INTRO)), embed=True, width=270))
"""),
]


OMNIVOICE_CELLS = [
    markdown("""
# makable Shorts: the narration by OmniVoice

[OmniVoice](https://github.com/k2-fsa/OmniVoice) speaks each scene of a script in your voice, cloned from a few seconds of it: the `speak` stage with OmniVoice as the narrator, and all the scenes joined into one file. That's all this notebook does. There's no Chatterbox here, so OmniVoice installs straight into Colab.

The scenes go in the run's `narration/` folder on Drive: with `NARRATOR = "omnivoice"` in the Shorts notebook (section 1), the video uses them as they are.

**Before you start**

- *Runtime → Change runtime type →* **T4 GPU**.
- On Google Drive: the voice sample, `makable-shorts/assets/voice.wav`, and the run's `script.json` (the Crumb & Co one is there).
"""),
    markdown("""
## Setup

Installs OmniVoice into Colab's own Python, with the `transformers` of its release (it uses transformers' internals). pip may list conflicts with packages Colab already has; nothing here uses them.
"""),
    code("""
!pip install -q omnivoice==0.2.1 transformers==5.14.1
"""),
    code("""
import os
import sys
from pathlib import Path

from google.colab import drive

drive.mount("/content/drive")

HOME = Path("/content/drive/MyDrive/makable-shorts")
ASSETS = HOME / "assets"
LANGUAGE = "en"  # what the script is in: "en", or "hi" for Hindi
# The video's folder, with its script.json: the Shorts notebook's RUN.
RUN = HOME / "runs" / ("crumb-and-co" if LANGUAGE == "en" else f"crumb-and-co-{LANGUAGE}")
"""),
    code('os.makedirs("/content/shorts/stages", exist_ok=True)'),
    *module_cells(MODULES),
    code("""
%load_ext autoreload
%autoreload 2
sys.path.insert(0, "/content")
os.environ["OMNIVOICE_ENV"] = "here"  # OmniVoice is installed in this Python, not in an environment of its own

from IPython.display import Audio, display

from shorts.compose import GAP
from shorts.media import duration, ffmpeg
from shorts.run import SCRIPT, Run, file_hash, fingerprint, narration_file
from shorts.script import WORDS_PER_SECOND

run = Run(RUN)
""" + RUNNER),
    markdown("""
## 1. The voice and the script

OmniVoice copies how the sample is said along with the voice, and clones best from 3 to 10 s of clean speech. A longer sample works, a little less well: `voice_sample(VOICE_SAMPLE, ASSETS / "voice-10s.wav", length=10)` (from `shorts.voice`) cuts a 10-second one. `REFERENCE_TEXT` is what's said in the sample, word for word; without it, Whisper writes it down (one more download).

The script is the run's `script.json`. To change what's said, edit it and run the cells again. The narrator and the voice sample go in the run's `run.json`.
"""),
    code("""
VOICE_SAMPLE = ASSETS / "voice.wav"
REFERENCE_TEXT = None  # what's said in VOICE_SAMPLE, word for word; None: Whisper writes it down

if not run.path(SCRIPT).exists():
    raise FileNotFoundError(f"No script.json in {RUN}: write one in the Shorts or the voice notebook first")
settings = ["--narrator", "omnivoice", "--voice", VOICE_SAMPLE]
if REFERENCE_TEXT:
    settings += ["--reference-text", REFERENCE_TEXT]
shorts("new", RUN, *settings)
script = run.script()
print(f"The voice: {VOICE_SAMPLE.name} ({duration(VOICE_SAMPLE):.1f} s)")
display(Audio(str(VOICE_SAMPLE)))
for index, scene in enumerate(script.scenes, 1):
    print(f"{index}. {scene.text}")
"""),
    markdown("""
## 2. The narration

The first scene takes a few minutes, while OmniVoice downloads its model (about 2.4 GB) and loads it; after that, each scene takes seconds. Scenes already spoken with the same voice sample and settings aren't spoken again, so after you change a setting or a scene's text, only what changed is spoken.

- Its settings go in the run's settings: `shorts("new", RUN, "--narrator-option", "speed=1.1")` speaks faster, and `num_step=16` is quicker to make and a little worse (the default is 32).
- It reads `makable` respelled as "makeable" (`shorts.voice.PRONOUNCE`). For English, phonemes in brackets work too: `shorts("new", RUN, "--pronounce", "makable=[M EY1 K AH0 B AH0 L]")`.
- Hindi: it learned it from far less speech than English (117 hours to 206,000), so listen closely.

Under each scene: how long it's spoken and how fast, and for a script written from steps, how long its stretch of the recording is. The video plays the stretch at the speed that fits the scene's narration.
"""),
    code("""
shorts("speak", RUN)
narration = [run.path(narration_file(index)) for index in range(len(script.scenes))]
spoken = 0.0
for index, (scene, wav) in enumerate(zip(script.scenes, narration, strict=True), 1):
    seconds = duration(wav)
    spoken += seconds
    stretch = f", over {scene.end - scene.start:.1f} s of {scene.footage}" if scene.start is not None else ""
    print(f"{index}. {seconds:.1f} s, {len(scene.text.split()) / seconds:.1f} words a second{stretch}: {scene.text}")
    display(Audio(str(wav)))
words = sum(len(scene.text.split()) for scene in script.scenes)
print(f"In all: {spoken:.1f} s, {words / spoken:.2f} words a second (the script assumes {WORDS_PER_SECOND:g})")
"""),
    markdown("""
## 3. The whole narration in one file

The scenes one after another, with the video's pause after each, as `narration-omnivoice-….wav` in the run's folder on Drive.
"""),
    code("""
whole = run.folder / f"narration-omnivoice-{fingerprint(*(file_hash(wav) for wav in narration))}.wav"
if not whole.exists():
    inputs = [part for wav in narration for part in ("-i", wav)]
    padded = "".join(f"[{i}:a]apad=pad_dur={GAP}[a{i}];" for i in range(len(narration)))
    joined = "".join(f"[a{i}]" for i in range(len(narration)))
    ffmpeg(*inputs, "-filter_complex", f"{padded}{joined}concat=n={len(narration)}:v=0:a=1", whole)
print(f"{whole} ({duration(whole):.1f} s)")
display(Audio(str(whole)))
"""),
]


# Both CPU notebooks: each file they need, from Drive or uploaded from your computer.
CHOOSE = """

def chosen(setting, what):
    \"\"\"A file: `setting` itself, the newest file matching it (a pattern), or one you upload (None).\"\"\"
    if setting is None:
        print(f"Choose {what} to upload:")
        uploads = files.upload()  # saved in /content
        if not uploads:
            raise FileNotFoundError(f"No {what}: upload one, or set it to a file on Drive")
        return Path(next(iter(uploads))).resolve()
    if Path(setting).exists():
        return Path(setting)
    matches = sorted(glob.glob(str(setting)), key=os.path.getmtime)
    if not matches:
        raise FileNotFoundError(f"Nothing on Drive matches {setting}")
    return Path(matches[-1])
"""

MERGE_CELLS = [
    markdown("""
# makable Shorts: the intro and the recording, joined

The whole video from two files: the intro (Omni's clip of you, in your voice), then a screen recording (narrated, or silent), each with its own sound, in one 1080×1920 MP4. A clip the frame's shape fills it; any other (a desktop recording in a vertical video) is shown whole over a blurred, darker copy of itself. The sound is evened out to -14 LUFS. No captions or music: the Shorts notebook adds those.

It runs `merge_intro.py` and the video engine it uses (`shorts.compose`), the same files as on the command line. They need only ffmpeg, so the CPU runtime is enough.

**Before you start**, have the two videos on your computer (or on Drive):

1. The intro avatar video, in your voice: section 4 of `voice_from_script.ipynb` makes it, as `intro/voiced.mp4` in the run's folder. Or Omni's own clip, with its sound in your voice as `INTRO_AUDIO`.
2. The screen recording, narrated or silent. `narrate_recording.ipynb` narrates a recording with scenes spoken already.

Section 1 asks you to upload the intro, section 2 the screen recording, and section 3 joins them. An upload stays in this session only; the video goes on Drive, in `RUN`.
"""),
    markdown("""
## Setup
"""),
    code("""
import glob
import os
import sys
from pathlib import Path

from google.colab import drive, files
from IPython.display import Video, display

drive.mount("/content/drive")

HOME = Path("/content/drive/MyDrive/makable-shorts")
RUN = HOME / "runs" / "crumb-and-co"  # the video's folder: the intro in your voice is its intro/voiced.mp4
"""),
    code('os.makedirs("/content/shorts", exist_ok=True)'),
    *module_cells(ENGINE_MODULES),
    code("%%writefile /content/merge_intro.py\n" + (ROOT / "merge_intro.py").read_text()),
    code("""
%load_ext autoreload
%autoreload 2
sys.path.insert(0, "/content")

from merge_intro import duration, frame_size, merge
""" + CHOOSE),
    markdown("""
## 1. The intro avatar video

Run the cell, then choose the intro on your computer. Or set `INTRO` to a file on Drive, such as `RUN / "intro" / "voiced.mp4"`, or a pattern (the newest match), and nothing is uploaded.
"""),
    code("""
INTRO = None  # None: upload it; or a file on Drive (such as RUN / "intro" / "voiced.mp4"), or a pattern
INTRO_AUDIO = None  # with Omni's own clip as INTRO: its sound in your voice (a WAV), in place of the clip's

intro = chosen(INTRO, "the intro avatar video")
intro_audio = chosen(INTRO_AUDIO, "the intro's sound") if INTRO_AUDIO else None
print(f"The intro: {intro.name} ({duration(intro):.1f} s)")
display(Video(str(intro), embed=True, width=270))
"""),
    markdown("""
## 2. The screen recording

Run the cell, then choose the screen recording on your computer (or set `RECORDING` to a file on Drive).
"""),
    code("""
RECORDING = None  # None: upload it; or a file on Drive, e.g. HOME / "recordings" / "makable-tight-narrated.mp4"

recording = chosen(RECORDING, "the screen recording")
width, height = frame_size(recording)
print(f"The screen recording: {recording.name} ({duration(recording):.1f} s, {width}x{height})")
"""),
    markdown("""
## 3. The whole video

The intro, then the screen recording. `SIZE = (1920, 1080)` makes a wide video.
"""),
    code("""
SIZE = (1080, 1920)  # the video's width and height: (1920, 1080) for a wide one

out = RUN / f"{recording.stem}-with-intro.mp4"
out.parent.mkdir(parents=True, exist_ok=True)
merge(intro, recording, out, intro_audio=intro_audio, size=SIZE)
print(f"Made {out} ({duration(out):.1f} s)")
display(Video(str(out), embed=True, width=270))
"""),
]


NARRATE_CELLS = [
    markdown("""
# makable Shorts: a screen recording, narrated

Puts a script's scenes, spoken already (one audio file per scene), over the screen recording the script was written from. Each scene's stretch of the recording (`start` to `end` in `script.json`) plays at the speed that makes it last as long as its audio, plus a short pause, so what's said is on screen while it's said. What no scene uses (retries, errors, waits) is left out. The picture stays the recording's size, and the voice is evened out to -14 LUFS. No intro, captions or music: `merge_intro.ipynb` puts the intro before it.

It runs `narrate_recording.py` and the video engine it uses (`shorts.compose`), the same files as on the command line. They need only ffmpeg, so the CPU runtime is enough.

**Before you start**, have these on your computer (or on Drive):

1. The screen recording the script was written from, such as `makable-tight.mp4`.
2. The script: a run's `script.json`, its scenes with `start` and `end`. The Crumb & Co one is on Drive, in `runs/crumb-and-co/`.
3. The audio: one file per scene, such as `download.wav`, `download (1).wav`, `download (2).wav` and so on.

Section 1 asks you to upload the recording, section 2 reads the script from Drive, section 3 asks for the audio files (all of them at once), and section 4 makes the video. An upload stays in this session only; the video goes on Drive, in `RUN`.
"""),
    markdown("""
## Setup
"""),
    code("""
import glob
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from google.colab import drive, files
from IPython.display import Audio, Video, display

drive.mount("/content/drive")

HOME = Path("/content/drive/MyDrive/makable-shorts")
RUN = HOME / "runs" / "crumb-and-co"  # the video's folder: its script.json is here, and the video goes here
"""),
    code('os.makedirs("/content/shorts", exist_ok=True)'),
    *module_cells(ENGINE_MODULES),
    code("%%writefile /content/narrate_recording.py\n" + (ROOT / "narrate_recording.py").read_text()),
    code("""
%load_ext autoreload
%autoreload 2
sys.path.insert(0, "/content")

from narrate_recording import duration, narrate
""" + CHOOSE),
    markdown("""
## 1. The screen recording

Run the cell, then choose the screen recording on your computer (or set `RECORDING` to a file on Drive).
"""),
    code("""
RECORDING = None  # None: upload it; or a file on Drive, e.g. HOME / "recordings" / "makable-tight.mp4"

recording = chosen(RECORDING, "the screen recording")
print(f"The screen recording: {recording.name} ({duration(recording):.1f} s)")
"""),
    markdown("""
## 2. The script

The run's `script.json` on Drive (`SCRIPT = None` uploads one instead). Below: each scene, and its stretch of the recording in seconds.
"""),
    code("""
SCRIPT = RUN / "script.json"  # or None: upload it

script = chosen(SCRIPT, "the script (script.json)")
scenes = json.loads(script.read_text())["scenes"]
for index, scene in enumerate(scenes, 1):
    print(f"{index}. {scene.get('start')} to {scene.get('end')} s: {scene['text']}")
"""),
    markdown("""
## 3. The audio

Run the cell, then choose every scene's audio file at once (⌘- or Ctrl-click them). They're put in order by the numbers in their names, `download.wav`, `download (1).wav`, … `download (10).wav`, so the first scene's is the one without a number. A file that's the same as another (downloaded twice) is left out. Under each scene is its audio: listen, to check they're in the right order.

`AUDIO` can also be a pattern on Drive, such as `HOME / "assets" / "download*.wav"`, or a list of files in the scenes' order.
"""),
    code("""
AUDIO = None  # None: upload them; or a pattern on Drive, or a list of files in the scenes' order


def in_order(paths):
    \"\"\"By the numbers in their names: download.wav, download (1).wav, …, download (10).wav.\"\"\"

    def key(path):
        return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\\d+)", path.stem)]

    return sorted(paths, key=key)


if AUDIO is None:
    print("Choose the audio files, one per scene, all at once:")
    audio = in_order(Path(name).resolve() for name in files.upload())  # saved in /content
elif isinstance(AUDIO, (list, tuple)):
    audio = [Path(path) for path in AUDIO]
else:
    audio = in_order(Path(path) for path in glob.glob(str(AUDIO)))
kept, seen = [], {}
for path in audio:
    first = seen.setdefault(hashlib.sha256(path.read_bytes()).digest(), path)
    if first is path:
        kept.append(path)
    else:
        print(f"Leaving out {path.name}: it's the same as {first.name}")
audio = kept
if len(audio) != len(scenes):
    raise ValueError(f"The script has {len(scenes)} scenes, but there are {len(audio)} audio files")
for index, (scene, speech) in enumerate(zip(scenes, audio), 1):
    print(f"{index}. {speech.name} ({duration(speech):.1f} s): {scene['text']}")
    display(Audio(str(speech)))
"""),
    markdown("""
## 4. The narrated recording

Each scene's stretch, at the speed that fits its audio (printed below), one after another.
"""),
    code("""
out = RUN / f"{recording.stem}-narrated.mp4"
out.parent.mkdir(parents=True, exist_ok=True)
narrate(recording, script, audio, out)
print(f"Made {out} ({duration(out):.1f} s)")
print(f'To put the intro before it: merge_intro.ipynb, with RECORDING = Path("{out}")')
display(Video(str(out), embed=True, width=270))
"""),
]


def write(name: str, cells: list[dict], gpu: bool) -> None:
    notebook = {
        "cells": cells,
        "metadata": {
            **({"accelerator": "GPU"} if gpu else {}),
            "colab": {"provenance": [], **({"gpuType": "T4"} if gpu else {})},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 0,
    }
    (ROOT / name).write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n")
    print("wrote", name)


write("makable_shorts.ipynb", CELLS, gpu=True)
write("record_with_browser_use.ipynb", BROWSE_CELLS, gpu=False)
write("voice_from_script.ipynb", VOICE_CELLS, gpu=True)
write("omnivoice_from_script.ipynb", OMNIVOICE_CELLS, gpu=True)
write("merge_intro.ipynb", MERGE_CELLS, gpu=False)
write("narrate_recording.ipynb", NARRATE_CELLS, gpu=False)
