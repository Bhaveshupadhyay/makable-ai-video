# makable Shorts

Makes a 1-minute vertical video (YouTube Shorts, Instagram Reels) showing something your web product can do: a demo of a feature, narrated, with you on camera. The video has three parts, with captions and music:

1. A 10-second intro of you, filmed from your photo by Gemini Omni Flash or HeyGen ([Who films you](#who-films-you)).
2. A screen recording, narrated in the voice of the avatar in that intro.
3. An outro, filmed the same way.

## Installing it, as a Claude Code plugin

```
/plugin install makable-shorts --marketplace Bhaveshupadhyay/makable-ai-video
```

Or, on Claude Code before 2.1.275: `/plugin marketplace add Bhaveshupadhyay/makable-ai-video`, then `/plugin install makable-shorts@makable-shorts`.

It needs [uv](https://docs.astral.sh/uv) and ffmpeg on your machine (`brew install uv ffmpeg` on a Mac), and Chrome, or browser-use downloads Chromium. The plugin's command is `makable-shorts` (`bin/makable-shorts`). The plugin puts it on Claude's PATH, not your shell's: in your own terminal, use it from a checkout of the repo (`export PATH="$PWD/bin:$PATH"` there), or ask Claude to run it. The first time it runs, it sets up its own Python environments with uv, in `~/.cache/makable-shorts/envs`, which takes a few minutes; it does again after an update changes its packages.

Your keys go in `~/.config/makable-shorts/.env` (copy `.env.example`): Gemini's for Omni, and the voice API's for the narration. The skill tells you which are missing.

## With Claude Code: `/make-video`

The usual way to make one. In Claude Code, with the plugin installed, ask for a video, or:

```
/make-video 3f2a9c1 7be04d2                 # what these commits (in your product's code) changed
/make-video "show how to share a note with a teammate"
/make-video acme-api@91c0e4a --tone hype --language hi
```

**The first time,** the skill asks about your product and keeps notes on it (`references/product.md`): its address, whether recordings need you signed in, where its code is (for videos from commits), and what the outro asks viewers to do. It asks for your photo too, and music if you want some. They're all kept for every video after, outside the repo (`makable-shorts me` shows them).

The skill (`skills/make-video/`, `/makable-shorts:make-video` in full) does what needs judgment, and the pipeline below does the rest:

1. **What to show.** Claude reads the commits, or looks up the functionality you describe in your product's code, or on the product itself. It writes `changes.md`: what a user can do, where it is, and the labels on the page.
2. **The recording.** Claude drives Chrome itself with `makable-shorts drive`, a command at a time, signed in if your product needs it, while the pipeline records the screen. It needs no model or key of its own: Claude is the model. Claude looks at the recording's steps and frames. If the recording doesn't show the change, Claude records it again. (Or browser-use's agent records it from a task in plain words, `makable-shorts browse`, if you ask for that.)
3. **The script.** Claude writes it from what's on screen when (`references/script.md`). `makable-shorts check-script` checks each scene's stretch and pace before the script comes in.
4. **The video.** You approve the script (filming costs about $2). Then `makable-shorts run --paid`:
   - films the intro and the outro with Omni, and uses them as filmed;
   - takes the avatar's voice from the intro;
   - has the voice API speak the narration in that voice;
   - assembles `final.mp4`.

With `--yes`, the skill asks nothing, for GitHub Actions. `.github/workflows/make-video.yml` runs it from the Actions tab (`gh workflow run make-video.yml -f commits=3f2a9c1`), with Claude Code on your subscription, and uploads the video. Its header lists the secrets it needs.

To run it locally, it needs:

- **Your photo**, and music if you want it: `makable-shorts me --face PHOTO [--music FILE]`, or the skill asks for them. A photo with its background removed works best with Omni, which films the setting the script describes.
- **The keys:** copy `.env.example` to `~/.config/makable-shorts/.env` (or `.env` here), and fill it in. The environment wins over the files.

**Your own things** are kept in SHORTS_HOME, `~/.config/makable-shorts` unless that's set (`shorts/home.py`): your photo, music and voice (`me/`), each product's notes (`products/<name>.md`), the sites you've signed in to (`sites/`), and a `.env`. A new run takes a copy of your photo, music and voice from there (in its own `me/`), unless it's given others, so changing yours later leaves the videos made before as they were.

## How it's built: stages that share a folder

The video is made by six stages. Each is a program of its own (`makable-shorts <stage> RUN`) with its own packages.

The stages share nothing but the video's **run folder**. Each reads the files the stages before it wrote there, and writes its own, under fixed names. No stage calls or imports another. So each can run on a different machine, be swapped for another tool, or be skipped by bringing its files in (`makable-shorts import`).

| Stage | Makes (in the run folder) | From | With |
|---|---|---|---|
| `record` | `footage/<name>.mp4` (+ `.steps.json`) | `run.json`'s `footage`: the recordings `drive` or `browse` made | a copy |
| `film-intro` | `intro/filmed.mp4` | the intro line, your photo | run.json's `intro`: Gemini Omni Flash or HeyGen (`shorts/filmers.py`), **about $1** |
| `film-outro` | `outro/filmed.mp4` | the outro line, your photo | the same, in the intro's setting, **about $1** |
| `take-voice` | `voice/avatar.wav` | the filmed intro | ffmpeg: the avatar's voice, for the narration |
| `speak` | `narration/01.wav`, `02.wav`, … | each scene's text, the avatar's voice | the voice API (`shorts/speech_api.py`) |
| `assemble` | `final.mp4`, `metadata.json` | all of the above, music | ffmpeg + Pillow (`shorts/compose.py`, `shorts/captions.py`) |

**The script** (`script.json`) is made by no stage. Claude writes it, and it comes in with `makable-shorts import RUN script FILE`, which checks it first (`shorts/script.py`).

**The settings.** What the video is made from is the run's `run.json`:
- the footage, your photo and the music;
- the language and the tone;
- the narrator's model and its settings.

`makable-shorts new` writes it, and it's yours to edit. The defaults are the flow above. The contract, the names and formats every stage reads and writes, is in `shorts/run.py`.

**Only what changed is made again.** Each stage notes, in `.records/<product>.json`, two things for each of its files: a fingerprint of what the file was made from (the scene's text, the voice, the settings), and a fingerprint of the file as written.
- **Out of date:** a file is out of date when what it would be made from now is different, and only that file is made again. Edit one scene's text and only its narration is spoken again.
- **Edited by hand:** a file that changed since its stage wrote it is kept as it is. Delete it, or pass `--force`, to make it again.

**The orchestrator** (`makable-shorts run RUN`, `shorts/orchestrator.py`) runs the stages that are due, in order, each in a process of its own. Each runs in the Python set for its packages (`SHORTS_<EXTRA>_PYTHON`, for each extra in `pyproject.toml`), or in the orchestrator's own Python. The orchestrator knows the stages only by what they make and read. Where it can't go on, it says what's next and where that runs, and stops: a stage whose packages this machine doesn't have, a paid clip, files you bring in. `makable-shorts status RUN` shows each product's state.

**Bringing files in.** Anything a stage makes can come from elsewhere instead:

```sh
makable-shorts import RUN footage --name demo recordings/demo-tight.mp4   # with its .steps.json
makable-shorts import RUN intro gemini_generated_video.mp4         # a clip filmed in the Gemini app, HeyGen's, Higgsfield's…
makable-shorts import RUN outro https://example.com/outro.mp4      # or a link to it: the file's own link, not a page
makable-shorts import RUN narration ~/Downloads/download*.wav      # one audio file per scene
```

Narration files go in order by the numbers in their names (`download.wav`, `download (1).wav`, … `download (10).wav`, as browsers name repeated downloads); `--as-given` keeps your order. A file that's the same as one before it (downloaded twice) is left out.

Bringing a product in makes `run.json` say it's yours (`"narrator": "import"`, say). From then on the pipeline asks you for it again instead of making it: when a scene's text changes, its narration is out of date.

The scripts are in English or Hindi (`--language hi`), and friendly or excited like a Short (`--tone hype`). Each scene is said over its stretch of a recording, played at the speed that fits its narration, so what's said is on screen while it's said.

## Who films you

run.json's `intro` and `outro` say who films each clip from your photo (`makable-shorts new RUN --intro heygen --outro heygen`):

| | `omni` (the default) | `heygen` |
|---|---|---|
| What it is | Gemini Omni Flash films a new shot of you, in the script's `intro_setting` | HeyGen's photo to video animates your photo as it is |
| The voice | Omni's own, a new one each clip | one of HeyGen's, the same every clip: run.json's `filmer_voice` (`makable-shorts new RUN --filmer-voice ID`) |
| Keys | `GEMINI_API_KEY` (AI Studio's prepaid balance), or Agent Platform on Google Cloud credits (below) | `HEYGEN_API_KEY`, from HeyGen's API balance |
| Packages | the `gemini` extra | the `heygen` extra |

`makable-shorts voices --gender male` lists HeyGen's voices, each with a link to hear it. The narration is spoken in the intro's voice either way, so the video sounds like one person.

Anything else (Higgsfield, HeyGen's own site, the Gemini app) works too: film the clips there and bring them in, a file or a link to one (`makable-shorts import RUN intro CLIP`). A service with an API is one more `Filmer` in `shorts/filmers.py`: what it's made from, for knowing when to film again, and how it films a line.

## Recording by driving Chrome (`makable-shorts drive`)

This is how Claude Code records, in `/make-video`. Chrome runs in a process of its own that stays open, recording, and each command does one thing in it and prints the page as it is after it:

```sh
makable-shorts drive RUN start --url https://app.example.com --signed-in   # opens it, and prints the page
makable-shorts drive RUN click 12 --goal "Open the share menu"
makable-shorts drive RUN type 9 "My teammate's email" --goal "Add a teammate"
makable-shorts drive RUN wait-for "Shared" --timeout 240
makable-shorts drive RUN stop --report "what it showed"
```

- **The window** is 720×1280 unless `start --window` says otherwise: a site's phone layout, which fills the vertical video. A product without one records at `--window 1280x800`, and the video shows it whole over a blurred copy.
- **The page.** `start`, `look` and every step print the tabs, the page's elements with a number each (what `click`, `type` and `scroll --number` take), and the path of a screenshot. They're browser-use's own, the ones its agent's model is shown.
- **The steps.** Each command is a step, kept with its `--goal`, what it did and when, in the same steps file `browse` writes. The other commands are `keys`, `scroll`, `wait`, `tab`, `open` and `act` (any other of browser-use's actions); `makable-shorts drive RUN --help` lists them.
- **The spotlight.** It's off unless asked for: Claude adds it only when you ask. `click` and `type` take `--spotlight`: the rest of the page blurs and dims, and the element stands out in a ring with a shadow, so it looks raised. Buttons are never spotlit, even with `--spotlight`: on a small one it's a ring round a speck. It comes on half a second before the pointer moves to the element, and goes as the click lands, or once the typing's done. It's drawn in the page while it records, like the pointer, and follows the element as it moves or grows. A text field without a border of its own, such as a chat app's prompt, lights the box it's in.
- **Afterwards.** `stop` cuts out the time between commands and the still parts of the waits, as `browse` does, and brings the tight recording in as the footage.

It needs no model and no key: whoever sends the commands is the model, Claude Code here. The commands talk to the Chrome process on a local port with a token (`RUN/recordings/<name>.driving.json`, there while it records), so only that process needs browser-use (in its own environment, below). Its log is `RUN/recordings/<name>.drive.log`. A driver that's sent nothing for 30 minutes stops by itself, keeping what it recorded.

## Recording from a task (`makable-shorts browse`)

```sh
makable-shorts browse RUN --url https://app.example.com --name demo --task task.md --signed-in
```

This has browser-use's agent do the task in `task.md` on your product, signed in as you left it (`signin`). The task is in plain words: what to do and show.

- **While it records:** Chrome's screencast is recorded in real time (`shorts/browse.py`), with a drawn mouse pointer gliding to each click and fading out 2 s after it, and each step's goal and times are kept.
- **Afterwards:** `cut_pauses` takes out the model's thinking, and the parts of its waits where nothing changes on the page. It plays typing 4× as fast (only the typing: the pointer gliding to the field plays at its own speed), and zooms in on each click.
- **In the run:** the tight recording comes in as the footage `demo`, with its steps. The recordings, and what they were made with, stay in `RUN/recordings/`.

`makable-shorts frames RUN demo` makes contact sheets of the recording's frames, labelled with their times, to see what's on screen when.

The agent's model is `provider:model`, from `--model`, from `SHORTS_BROWSE_MODEL`, or the default `google:gemini-3.6-flash`:

| Prefix | Model | Key |
|---|---|---|
| `google:` | Gemini, through the Gemini API (the default) | `GEMINI_API_KEY` |
| `vertex:` | Gemini on Agent Platform | `GOOGLE_CLOUD_PROJECT` |
| `anthropic:` | Claude | `ANTHROPIC_API_KEY` |
| `openai:` | GPT, or any provider with OpenAI's API | `OPENAI_API_KEY`, plus `OPENAI_BASE_URL` for another provider |

A model that fails (429, 5xx) hands the rest of the run to `--fallback`.

browser-use pins its own packages, so it lives in an environment of its own, which `makable-shorts` makes the first time a command needs a browser. `browse` and `signin` run themselves there, and `drive start` runs Chrome's process there: the Python `SHORTS_BROWSE_PYTHON` names, in a checkout of the repo (see Working on it).

## Recording signed in (`makable-shorts signin`)

Most of what's worth showing is behind a sign-in, and every product signs people in its own way (a password, Google, GitHub, a code by email). So you sign in once, by hand:

```sh
makable-shorts signin --url https://app.example.com    # Chrome opens: sign in, then close the window
```

Chrome opens on the page in a profile of the site's own (`SHORTS_HOME/sites/<host>`). Once you close the window, the profile keeps what the site saved: its cookies, local storage and IndexedDB. `drive start --signed-in` and `browse --signed-in` then record headless in that profile, so they start signed in. A site that refreshes its session as it's used saves the new one there too, so it stays signed in from one recording to the next. When a session runs out, sign in again; `--forget` deletes the profile. A site is its host, with or without `www.`.

- **Use a demo account** if you can: the recordings show it, and what they make stays in it.
- **One Chrome at a time** per site: a recording can't use the profile while the sign-in window is open, and says so.
- **GitHub Actions** can't sign in by hand, so recordings there are signed out.

It's the Chrome browser-use records with (`shorts/signin.py`), so the profile suits it.

## The voice API (`services/voice`, on Modal)

`speak` sends each scene to a text-to-speech API, in a voice cloned from the avatar's, so the narration needs no GPU where the video is made.

Our API runs OmniVoice and Chatterbox on Modal's GPUs (`services/voice/models.py`). It has the shape of ElevenLabs' API (the same paths, `xi-api-key` header and formats), so the client (`shorts/speech_api.py`) talks to either:

| | Our API on Modal | ElevenLabs |
|---|---|---|
| `SHORTS_SPEECH_URL` | `https://<workspace>--makable-voice-web.modal.run` | `https://api.elevenlabs.io` |
| `SHORTS_SPEECH_KEY` | the `VOICE_API_KEY` you set (below) | your ElevenLabs key |
| run.json's `narrator_model` | `omnivoice` (the default) or `chatterbox` | `eleven_multilingual_v2`, say |
| `narrator_options` (its `voice_settings`) | `speed=1.1` (OmniVoice), `exaggeration=0.7` (Chatterbox) | `stability=0.5`, … |

The voice is cloned when the first scene is spoken, and deleted once they're all spoken. Each scene is a request of its own, so only the scenes whose text changed are spoken again.

Set up our API once (with `pip install modal` and `modal setup`):

```sh
modal secret create makable-voice VOICE_API_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
modal deploy -m services.voice.app     # from the repo's root: prints the URL
curl https://<workspace>--makable-voice-web.modal.run/health
```

What it costs, and how long the first request waits:
- **GPU:** each model runs on a T4 of its own (`GPU` in `services/voice/app.py`).
- **Containers:** at most one at a time per model, and each stops two minutes after its last request. You pay for the GPU while it speaks, and a little while after.
- **Cold starts:** the first request after a while waits for the container to start and load the model. The models download only once, into a Volume.

## Working on it: a checkout of the repo

The repo is the plugin and its marketplace (`.claude-plugin/`). `claude --plugin-dir .` loads your working copy as the plugin for a session (`/reload-plugins` picks up changes), so `makable-shorts` and the skill are the ones you're editing. `claude plugin validate .` checks it.

`makable-shorts` is `python -m shorts` in its own environments. In a checkout, you can also run the module in one of your own:

```sh
uv venv --python 3.12 .venv && uv pip install --python .venv -e '.[gemini,assemble,speech,heygen]'
uv venv --python 3.12 ~/browse-env && uv pip install --python ~/browse-env -e '.[browse]'   # SHORTS_BROWSE_PYTHON
mkdir -p ~/.config/makable-shorts && cp .env.example ~/.config/makable-shorts/.env          # and fill it in
.venv/bin/python -m shorts status runs/first
```

Each stage's packages are an extra of its own (`gemini`, `assemble`, `speech`, `heygen`; `browse` in its own environment), so a machine installs only what the stages it runs need. Everything needs ffmpeg.

Omni films with `GEMINI_API_KEY`, through the Gemini API (AI Studio), which only spends credits while a prepaid balance is above $0. Or it can film on Agent Platform (Vertex AI), which spends Google Cloud credits (the Free Trial's, Google AI Pro's) with no prepaid balance:

```sh
gcloud auth application-default login       # once; GitHub Actions uses google-github-actions/auth instead
export GOOGLE_GENAI_USE_ENTERPRISE=true GOOGLE_CLOUD_PROJECT=<project> GOOGLE_CLOUD_LOCATION=global
```

The Omni model id is picked for the backend (`shorts/intro.py`). Without Claude Code, a video is made like this, in a checkout of the repo:

```sh
export PATH="$PWD/bin:$PATH"     # makable-shorts, in this shell: the plugin puts it only on Claude's PATH
makable-shorts me --face ~/Pictures/me.png --music ~/Music/calm.mp3   # once: kept for every video
makable-shorts signin --url https://app.example.com                    # once, if it needs signing in
makable-shorts new runs/first      # [--language hi] [--tone hype] [--pronounce Acme=akmee]
makable-shorts browse runs/first --url https://app.example.com --name demo --task task.md --signed-in
makable-shorts import runs/first script script.json   # checked first: check-script shows the problems
makable-shorts status runs/first
makable-shorts run runs/first --paid      # --paid: film the intro and outro too (about $1 each)
makable-shorts speak runs/first           # or one stage at a time, here
```

The tests make small videos with ffmpeg and run the stages, the orchestrator and the voice API on them:

```sh
uv run --isolated --no-project --python 3.12 --with pydantic --with pillow --with pytest \
  --with fastapi --with python-multipart --with httpx python -m pytest   # without the last three, the API's tests are skipped
```
