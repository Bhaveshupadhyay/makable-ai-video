# makable Shorts

A Claude Code plugin that makes 1-minute vertical videos of your web product, for YouTube Shorts and Instagram Reels.

## Demos

<table>
  <tr>
    <td align="center" width="50%">
      <a href="https://www.youtube.com/shorts/VWhdMEDQJ30"><img src="https://i.ytimg.com/vi/VWhdMEDQJ30/hqdefault.jpg" alt="Demo: the best free AI website builder" width="320"></a>
      <br><sub>▶ <a href="https://www.youtube.com/shorts/VWhdMEDQJ30">The best free AI website builder</a></sub>
    </td>
    <td align="center" width="50%">
      <a href="https://www.youtube.com/shorts/NhtTbSJjj_c"><img src="https://i.ytimg.com/vi/NhtTbSJjj_c/hqdefault.jpg" alt="Demo: a free business website in 3 minutes" width="320"></a>
      <br><sub>▶ <a href="https://www.youtube.com/shorts/NhtTbSJjj_c">A free business website in 3 minutes</a></sub>
    </td>
  </tr>
</table>

## Install

In Claude Code:

```
/plugin install makable-shorts --marketplace Bhaveshupadhyay/makable-ai-video
```

On Claude Code before 2.1.275, add the marketplace first:

```
/plugin marketplace add Bhaveshupadhyay/makable-ai-video
/plugin install makable-shorts@makable-shorts
```

There's nothing else to install. The first video takes a few minutes longer, while the plugin downloads what it needs: uv, its Python and packages (ffmpeg among them), and Chromium if you don't have Chrome.

### Turn on auto-update

Claude Code doesn't update plugins from a marketplace like this one by itself until you turn it on, once:

1. Run `/plugin` and open the **Marketplaces** tab.
2. Select **makable-shorts**, then **Enable auto-update**.

A new version then downloads in the background a few minutes into a session, and loads with `/reload-plugins` or the next time you start Claude Code. To update by hand instead: `claude plugin update makable-shorts@makable-shorts`.

## Make a video

Start Claude Code in your product's repo, so Claude can read its code, and ask for a video. Or:

```
/make-video "show how to share a note with a teammate"
/make-video 3f2a9c1 7be04d2                    # what these commits changed
/make-video acme-api@91c0e4a --tone hype --language hi
```

**The first time,** it asks for your product's address (and whether it needs you signed in), the [kind of video](#kinds-of-video) you want, your photo for an avatar video, and music if you'd like some. Then it opens a file for the keys your choices need: paste them there, never into the chat. A demo narrated by Kokoro, or a silent one, needs no keys.

**Then, for each video:**

1. Claude works out what to show, from the commits or your description, by reading your product's code.
2. Claude records it, driving Chrome itself.
3. Claude writes the script from the recording, and you approve it.
4. The pipeline films the intro and outro, speaks the narration, adds captions and music, and writes `final.mp4`.

Each video is in `.makable-shorts/runs/` in your product's repo, kept out of git. It can make videos from GitHub Actions too: see [From GitHub Actions](#from-github-actions).

## Kinds of video

| | AI avatar video | Narrated demo | Silent demo |
|---|---|---|---|
| Opens on | you, as an AI avatar, saying the hook | a title card: the hook over a blurred still of the recording | the same |
| The recording | narrated in your avatar's voice | narrated by Kokoro (free, on your machine), or in your own voice | each scene's words as captions |
| Ends on | your avatar signing off | an end card with the sign-off | the same |
| Needs | your photo, and keys for whoever films and speaks | nothing (Kokoro), or a sample of your voice and a key | nothing |
| Costs | about $2 (Omni), plus the narration | nothing (Kokoro) | nothing |

You choose who films your avatar and who speaks the narration: see [Who films you](#who-films-you) and [Who speaks the narration](#who-speaks-the-narration).

---

## How `/make-video` works

The skill (`skills/make-video/`, `/makable-shorts:make-video` in full) does what needs judgment, and the pipeline does the rest:

1. **What to show.** Claude reads the commits, or looks up the functionality you describe in your product's code, or on the product itself. From the code, it learns the flow before recording: the page's route, the labels as the code writes them, what shows while something slow runs. It writes `changes.md`: what a user can do, where it is, and the labels on the page.
2. **The recording.** Claude drives Chrome itself with `makable-shorts drive`, a command at a time, signed in if your product needs it, while the pipeline records the screen. It needs no model or key of its own: Claude is the model. Claude looks at the recording's steps and frames. If the recording doesn't show the change, Claude records it again.
3. **The script.** Claude writes it from what's on screen when (`references/script.md`). `makable-shorts check-script` checks each scene's stretch and pace before the script comes in.
4. **The video.** You approve the script (filming with Omni costs about $2; a demo narrated by Kokoro, or a silent one, costs nothing). Then `makable-shorts run --paid`:
   - films the intro and the outro with Omni or HeyGen (or takes the clips you bring in), and uses them as filmed;
   - takes the avatar's voice from the intro;
   - has ElevenLabs, or your own voice API, speak the narration in that voice, or Kokoro in its own, in a demo;
   - assembles `final.mp4`.

**Your product's notes.** The first time, the skill asks about your product and keeps notes on it (`references/product.md`): its address, whether recordings need you signed in, where its code is (for videos from commits), and what the outro asks viewers to do. In the product's repo, they're kept in it, `.makable-shorts/products/<name>.md`, for you to commit, so your teammates and the GitHub workflow use them too. Every video needs the product's address, and an avatar video your photo, unless you bring in clips you film yourself (`--filmer import`): the skill doesn't go on without them. A demo needs no photo, and one in your own voice needs a sample of it instead (`me --voice`). `makable-shorts me` shows what's kept, and where.

Each video's run folder goes in the repo too, in `.makable-shorts/runs/`, and keeps itself out of git (a `.gitignore` of its own), since its recordings and clips are big.

**Your choices, and your keys.** The first time, the skill asks which kind of video you want, then who films your avatar (Gemini Omni in your own Google Cloud project, HeyGen, clips you film yourself, or no one, for a demo) and who speaks the narration (ElevenLabs, your own voice API on Modal, Kokoro, or no one), and keeps your answers:

| | `makable-shorts me` |
|---|---|
| AI avatar video | `--filmer omni\|heygen\|import --narrator elevenlabs\|modal` |
| Narrated demo | `--filmer none --narrator kokoro\|elevenlabs\|modal` |
| Silent demo | `--filmer none --narrator none` |

Then `makable-shorts keys --open` writes the keys those need into `~/.config/makable-shorts/.env`, each with where to get it, and opens the file in your text editor: you paste the keys in there, never into the chat (`.env.example` lists them all; the environment wins over the files). Your own voice API needs none from you: `makable-shorts deploy-voice` deploys it to your Modal account and writes its address and key there itself. Your photo and music are `makable-shorts me --face PHOTO [--music FILE]`. A photo with its background removed works best with Omni, which films the setting the script describes.

**Your own things** are kept in SHORTS_HOME, `~/.config/makable-shorts` unless that's set (`shorts/home.py`): your photo, music and voice (`me/`), who films you and who speaks (`choices.json`), the sites you've signed in to (`sites/`), a `.env`, and the notes on products whose code isn't where you make their videos (`products/<name>.md`). A new run takes a copy of your photo, music and voice from there (in its own `me/`), and your choices, unless it's given others, so changing yours later leaves the videos made before as they were. **The product's repo** holds the rest, in `.makable-shorts/`: its notes (`products/`, committed) and its videos (`runs/`, ignored).

**Kinds, in run.json.** A demo's `intro` and `outro` are `card`, and a silent one's `narrator` is `none` (`makable-shorts new RUN --intro card --outro card --narrator none`, for one video). The cards are drawn by `assemble` (`shorts/cards.py`). The narrator says their lines too (`narration/intro.wav`, `outro.wav`), so a narrated demo's cards stay up while they're said, and a silent one's for as long as they take to read. `metadata.json`'s `containsSyntheticMedia`, for YouTube's "altered or synthetic content", is true for an avatar or a cloned voice, and false for Kokoro's voice or no voice.

**The `makable-shorts` command** is `bin/makable-shorts`. The plugin puts it on Claude's PATH, not your shell's: in your own terminal, use it from a checkout of the repo (`export PATH="$PWD/bin:$PATH"` there), or ask Claude to run it. The first time it runs, it sets up its own Python environments with uv, in `~/.cache/makable-shorts/envs`, which takes a few minutes; it does again after an update changes its packages. It uses your uv if you have one, or else downloads its own into `~/.cache/makable-shorts/uv`, leaving your shell's profile alone. Its ffmpeg is one of those packages ([imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg)'s static build), and browser-use downloads Chromium when there's no Chrome, so it needs nothing installed by hand.

### From GitHub Actions

With `--yes`, the skill asks nothing, for GitHub Actions. Copy `.github/workflows/make-video.yml` into your product's repo: it runs the skill there from the Actions tab (`gh workflow run make-video.yml -f commits=3f2a9c1`), with Claude Code on your subscription and the notes committed in the repo, and uploads the video. Its header lists the secrets and variables it needs: who films you and who speaks are repository variables there, and Omni signs in to Google Cloud with `google-github-actions/auth`.

## How it's built: stages that share a folder

The video is made by six stages. Each is a program of its own (`makable-shorts <stage> RUN`) with its own packages.

The stages share nothing but the video's **run folder**. Each reads the files the stages before it wrote there, and writes its own, under fixed names. No stage calls or imports another. So each can run on a different machine, be swapped for another tool, or be skipped by bringing its files in (`makable-shorts import`).

| Stage | Makes (in the run folder) | From | With |
|---|---|---|---|
| `record` | `footage/<name>.mp4` (+ `.steps.json`) | `run.json`'s `footage`: the recordings `drive` made | a copy |
| `film-intro` | `intro/filmed.mp4` | the intro line, your photo | run.json's `intro`: Gemini Omni Flash or HeyGen (`shorts/filmers.py`), **about $1** |
| `film-outro` | `outro/filmed.mp4` | the outro line, your photo | the same, in the intro's setting, **about $1** |
| `take-voice` | `voice/avatar.wav` | the filmed intro | ffmpeg: the avatar's voice, for the narration |
| `speak` | `narration/01.wav`, `02.wav`, … (and `intro.wav`, `outro.wav` for cards) | each scene's text, the avatar's voice | run.json's `narrator`: ElevenLabs, or your voice API on Modal (`shorts/speech_api.py`), or Kokoro (`shorts/voice.py`) |
| `assemble` | `final.mp4`, `metadata.json` | all of the above, music | ffmpeg + Pillow (`shorts/compose.py`, `shorts/captions.py`, and `shorts/cards.py` for a demo's cards) |

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
makable-shorts import RUN narration ~/Downloads/download*.wav      # one audio file per scene (and per card, first and last)
```

Narration files go in order by the numbers in their names (`download.wav`, `download (1).wav`, … `download (10).wav`, as browsers name repeated downloads); `--as-given` keeps your order. A file that's the same as one before it (downloaded twice) is left out.

Bringing a product in makes `run.json` say it's yours (`"narrator": "import"`, say). From then on the pipeline asks you for it again instead of making it: when a scene's text changes, its narration is out of date.

The scripts are in English or Hindi (`--language hi`), and friendly or excited like a Short (`--tone hype`). Each scene is said over its stretch of a recording, played at the speed that fits its narration, so what's said is on screen while it's said.

## Who films you

`makable-shorts me --filmer` says who films your clips from your photo, for every run after: run.json's `intro` and `outro` (`makable-shorts new RUN --intro heygen --outro heygen`, for one run):

| | `omni` | `heygen` | `import` |
|---|---|---|---|
| What it is | Gemini Omni Flash films a new shot of you, in the script's `intro_setting` | HeyGen's photo to video animates your photo as it is | clips you film elsewhere, brought in |
| The voice | Omni's own, a new one each clip | one of HeyGen's, the same every clip: `me --filmer-voice ID` | the clip's |
| What it needs | your Google Cloud project's ID in `GOOGLE_CLOUD_PROJECT` (with billing, and the Vertex AI API on), and `gcloud auth application-default login` once | `HEYGEN_API_KEY` | `makable-shorts import RUN intro CLIP` (and `outro`): a file or a link |
| What it costs | about $1 a clip, from the project's billing or its credits | HeyGen's API balance | nothing here |
| Packages | the `gemini` extra | the `heygen` extra | none |

Omni films on Agent Platform (Vertex AI), not through a Gemini API key, so it's paid from Google Cloud: its billing account, or credits (the Free Trial's, Google AI Pro's).

`makable-shorts voices --gender male` lists HeyGen's voices, each with a link to hear it. The narration is spoken in the intro's voice either way, so the video sounds like one person.

With `import`, anything works (Higgsfield, HeyGen's own site, the Gemini app): film the clips there and bring them in. A service with an API is one more `Filmer` in `shorts/filmers.py`: what it's made from, for knowing when to film again, and how it films a line.

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
- **The page.** `start`, `look` and every step print the tabs, the page's elements with a number each (what `click`, `type` and `scroll --number` take), and the path of a screenshot. They're browser-use's own.
- **The steps.** Each command is a step, kept with its `--goal`, what it did and when, in the recording's steps file. The other commands are `keys`, `scroll`, `wait`, `tab`, `open` and `act` (any other of browser-use's actions); `makable-shorts drive RUN --help` lists them.
- **The spotlight.** It's off unless asked for: Claude adds it only when you ask. `click` and `type` take `--spotlight`: the rest of the page blurs and dims, and the element stands out in a ring with a shadow, so it looks raised. Buttons are never spotlit, even with `--spotlight`: on a small one it's a ring round a speck. It comes on half a second before the pointer moves to the element, and goes as the click lands, or once the typing's done. It's drawn in the page while it records, like the pointer, and follows the element as it moves or grows. A text field without a border of its own, such as a chat app's prompt, lights the box it's in.
- **Afterwards.** `stop` cuts out the time between commands and the still parts of the waits, plays typing 4× as fast and zooms in on each click, and brings the tight recording in as the footage `demo`, with its steps. The recordings stay in `RUN/recordings/`.

It needs no model and no key: whoever sends the commands is the model, Claude Code here. The commands talk to the Chrome process on a local port with a token (`RUN/recordings/<name>.driving.json`, there while it records), so only that process needs browser-use (in its own environment, below). Its log is `RUN/recordings/<name>.drive.log`. A driver that's sent nothing for 30 minutes stops by itself, keeping what it recorded.

`makable-shorts frames RUN demo` makes contact sheets of the recording's frames, labelled with their times, to see what's on screen when.

browser-use pins its own packages, so it lives in an environment of its own, which `makable-shorts` makes the first time a command needs a browser. `signin` runs itself there, and `drive start` runs Chrome's process there: the Python `SHORTS_BROWSE_PYTHON` names, in a checkout of the repo (see Working on it).

## Recording signed in (`makable-shorts signin`)

Most of what's worth showing is behind a sign-in, and every product signs people in its own way (a password, Google, GitHub, a code by email). So you sign in once, by hand:

```sh
makable-shorts signin --url https://app.example.com    # Chrome opens: sign in, then close the window
```

Chrome opens on the page in a profile of the site's own (`SHORTS_HOME/sites/<host>`). Once you close the window, the profile keeps what the site saved: its cookies, local storage and IndexedDB. `drive start --signed-in` then records headless in that profile, so it starts signed in. A site that refreshes its session as it's used saves the new one there too, so it stays signed in from one recording to the next. When a session runs out, sign in again; `--forget` deletes the profile. A site is its host, with or without `www.`.

- **Use a demo account** if you can: the recordings show it, and what they make stays in it.
- **One Chrome at a time** per site: a recording can't use the profile while the sign-in window is open, and says so.
- **GitHub Actions** can't sign in by hand, so recordings there are signed out.

It's the Chrome browser-use records with (`shorts/signin.py`), so the profile suits it.

## Who speaks the narration

`speak` sends each scene to a text-to-speech API, in a voice cloned from the avatar's (or from your voice sample, in a demo), so the narration needs no GPU where the video is made. Or Kokoro speaks it on your own machine, for nothing (below). `makable-shorts me --narrator` says whose, for every run after (run.json's `narrator`):

| | `elevenlabs` | `modal`: your own voice API |
|---|---|---|
| What it is | ElevenLabs' API | the voice API in `services/voice` (OmniVoice and Chatterbox), on your own Modal account's GPUs |
| Keys | `ELEVENLABS_API_KEY`, on a plan that can clone a voice | `SHORTS_SPEECH_URL` and `SHORTS_SPEECH_KEY`, which `makable-shorts deploy-voice` sets |
| run.json's `narrator_model` | `eleven_multilingual_v2`, unless it names another | `omnivoice`, unless it names another (`chatterbox`) |
| `narrator_options` (its `voice_settings`) | `stability=0.5`, … | `speed=1.1` (OmniVoice), `exaggeration=0.7` (Chatterbox) |

Our API has the shape of ElevenLabs' (the same paths, `xi-api-key` header and formats), so one client (`shorts/speech_api.py`) talks to either. The voice is cloned when the first scene is spoken, and deleted once they're all spoken. Each scene is a request of its own, so only the scenes whose text changed are spoken again.

### Kokoro, on your own machine, for nothing

`kokoro` speaks the narration on your own machine's CPU, with [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M): a small open text-to-speech model (82M parameters, Apache-2.0). It needs no key, no account and no GPU, and costs nothing. It can't clone a voice, so it's for demos without an avatar, in one of its own voices: run.json's `kokoro_voice` (`me --kokoro-voice`), or by default `af_heart` in English and `hf_alpha` in Hindi. Others: `am_michael`, `bf_emma`, `bm_george`, `hm_omega`, and the rest of [its list](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md) for American and British English and Hindi. `narrator_options` takes its `speed` (1 by default).

It lives in an environment of its own, with torch for the CPU, which `makable-shorts` makes the first time a run Kokoro narrates is made or spoken (about 1 GB, a few minutes). The model downloads from Hugging Face the first time it speaks (about 330 MB). After that, a Short's narration takes well under a minute: about 55 s of speech took 28 s on an M-series Mac.

### Your own, on Modal (`makable-shorts deploy-voice`)

```sh
makable-shorts deploy-voice
```

It runs Modal's own command through uv, so there's nothing to install. If Modal has no sign-in on this machine, it opens your browser to sign in, or make an account, and waits until you have. Then it keeps the API's key in a Modal secret (`makable-voice`), deploys the API from the plugin's own folder, and writes its address and key into `~/.config/makable-shorts/.env`, without printing the key. The first deploy builds the models' images, which takes several minutes. Run it again after an update to deploy the new version: it keeps the key, so a `.env` elsewhere with it stays right.

By hand, from a checkout of the repo (with `pip install modal` and `modal setup`):

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
.venv/bin/python -m shorts status .makable-shorts/runs/first
```

Each stage's packages are an extra of its own (`gemini`, `assemble`, `speech`, `heygen`; `browse` and `kokoro` in environments of their own), so a machine installs only what the stages it runs need. Every environment gets ffmpeg from imageio-ffmpeg (`IMAGEIO_FFMPEG_EXE` names another), with no ffprobe: a file's length and streams are read from what ffmpeg prints about it (`shorts/media.py`). For Kokoro, in a checkout: `uv venv --python 3.12 ~/kokoro-env && UV_TORCH_BACKEND=cpu uv pip install --python ~/kokoro-env -e '.[kokoro]'`, and `SHORTS_KOKORO_PYTHON=~/kokoro-env/bin/python`.

Omni films in your own Google Cloud project, on Agent Platform (Vertex AI). Once:

```sh
gcloud auth application-default login       # GitHub Actions uses google-github-actions/auth instead
gcloud services enable aiplatform.googleapis.com --project <project>
```

and `GOOGLE_CLOUD_PROJECT=<project>` in the `.env` (Omni is at the `global` location, whatever `GOOGLE_CLOUD_LOCATION` says). Without Claude Code, a video is made like this, in a checkout of the repo:

```sh
export PATH="$PWD/bin:$PATH"     # makable-shorts, in this shell: the plugin puts it only on Claude's PATH
makable-shorts me --face ~/Pictures/me.png --music ~/Music/calm.mp3   # once: kept for every video
makable-shorts me --filmer omni --narrator elevenlabs                  # once: who films you, and who speaks
#                 (or --filmer none --narrator kokoro: a demo with no avatar, narrated for nothing, with no keys)
makable-shorts keys --open                                             # once: the keys those need, to fill in
makable-shorts signin --url https://app.example.com                    # once, if it needs signing in
makable-shorts new .makable-shorts/runs/first      # [--language hi] [--tone hype] [--pronounce Acme=akmee]
makable-shorts drive .makable-shorts/runs/first start --url https://app.example.com --signed-in   # prints the page
makable-shorts drive .makable-shorts/runs/first click 12 --goal "Open the share menu"   # a step at a time
makable-shorts drive .makable-shorts/runs/first stop --report "what it showed"   # in as the footage demo
makable-shorts frames .makable-shorts/runs/first demo   # what's on screen when, in RUN/frames/
# script.json is yours to write, from the recording's steps and frames (skills/make-video/references/script.md)
makable-shorts import .makable-shorts/runs/first script script.json   # checked first: check-script shows the problems
makable-shorts status .makable-shorts/runs/first
makable-shorts run .makable-shorts/runs/first --paid      # --paid: film the intro and outro too (about $1 each)
makable-shorts speak .makable-shorts/runs/first           # or one stage at a time, here
```

The tests make small videos with ffmpeg and run the stages, the orchestrator and the voice API on them:

```sh
uv run --isolated --no-project --python 3.12 --with pydantic --with pillow --with imageio-ffmpeg==0.6.0 --with pytest --with numpy \
  --with soundfile --with fastapi --with python-multipart --with httpx python -m pytest   # without the last three, the API's tests are skipped
```

## License

[MIT](LICENSE)
