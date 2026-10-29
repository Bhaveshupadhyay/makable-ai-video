# makable Shorts

Makes a 1-minute vertical video (YouTube Shorts, Instagram Reels) about something makable can do. The video has three parts, with captions and music:

1. A 10-second intro of you, filmed from your photo by Gemini Omni Flash or HeyGen ([Who films you](#who-films-you)).
2. A screen recording, narrated in the voice of the avatar in that intro.
3. An outro, filmed the same way.

## With Claude Code: `/make-video`

The usual way to make one. In Claude Code, in this repo:

```
/make-video 3f2a9c1 7be04d2                 # what these commits (in Bhaveshupadhyay/makable) changed
/make-video "show how to ask for a change to a site and see it in the preview"
/make-video makable-backend@91c0e4a --tone hype --language hi
```

The skill (`.claude/skills/make-video/`) does what needs judgment, and the pipeline below does the rest:

1. **What to show.** Claude reads the commits, or looks up the functionality you describe in makable's code. It writes `changes.md`: what a user can do, where it is, and the labels on the page.
2. **The recording.** Claude drives Chrome itself with `python -m shorts drive`, a command at a time, signed in as the demo user, while the pipeline records the screen. It needs no model or key of its own: Claude is the model. Claude looks at the recording's steps and frames. If the recording doesn't show the change, Claude records it again. (Or browser-use's agent records it from a task in plain words, `python -m shorts browse`, if you ask for that.)
3. **The script.** Claude writes it from what's on screen when (`references/script.md`). `python -m shorts check-script` checks each scene's stretch and pace before the script comes in.
4. **The video.** You approve the script (filming costs about $2). Then `python -m shorts run --paid`:
   - films the intro and the outro with Omni, and uses them as filmed;
   - takes the avatar's voice from the intro;
   - has the voice API speak the narration in that voice;
   - assembles `final.mp4`.

With `--yes`, the skill asks nothing, for GitHub Actions. `.github/workflows/make-video.yml` runs it from the Actions tab (`gh workflow run make-video.yml -f commits=3f2a9c1`), with Claude Code on your subscription, and uploads the video. Its header lists the secrets it needs.

To run it locally, it needs:

- **`assets/face.jpg`:** a photo of you. `assets/` and `recordings/` stay out of git.
- **The keys in `.env`:** copy `.env.example`. The environment wins over the file.

## How it's built: stages that share a folder

The video is made by six stages. Each is a program of its own (`python -m shorts <stage> RUN`) with its own packages.

The stages share nothing but the video's **run folder**. Each reads the files the stages before it wrote there, and writes its own, under fixed names. No stage calls or imports another. So each can run on a different machine, be swapped for another tool, or be skipped by bringing its files in (`python -m shorts import`).

| Stage | Makes (in the run folder) | From | With |
|---|---|---|---|
| `record` | `footage/<name>.mp4` (+ `.steps.json`) | `run.json`'s `footage`: the recordings `drive` or `browse` made | a copy |
| `film-intro` | `intro/filmed.mp4` | the intro line, your photo | run.json's `intro`: Gemini Omni Flash or HeyGen (`shorts/filmers.py`), **about $1** |
| `film-outro` | `outro/filmed.mp4` | the outro line, your photo | the same, in the intro's setting, **about $1** |
| `take-voice` | `voice/avatar.wav` | the filmed intro | ffmpeg: the avatar's voice, for the narration |
| `speak` | `narration/01.wav`, `02.wav`, … | each scene's text, the avatar's voice | the voice API (`shorts/speech_api.py`) |
| `assemble` | `final.mp4`, `metadata.json` | all of the above, music | ffmpeg + Pillow (`shorts/compose.py`, `shorts/captions.py`) |

**The script** (`script.json`) is made by no stage. Claude writes it, and it comes in with `python -m shorts import RUN script FILE`, which checks it first (`shorts/script.py`).

**The settings.** What the video is made from is the run's `run.json`:
- the footage, your photo and the music;
- the language and the tone;
- the narrator's model and its settings.

`python -m shorts new` writes it, and it's yours to edit. The defaults are the flow above. The contract, the names and formats every stage reads and writes, is in `shorts/run.py`.

**Only what changed is made again.** Each stage notes, in `.records/<product>.json`, two things for each of its files: a fingerprint of what the file was made from (the scene's text, the voice, the settings), and a fingerprint of the file as written.
- **Out of date:** a file is out of date when what it would be made from now is different, and only that file is made again. Edit one scene's text and only its narration is spoken again.
- **Edited by hand:** a file that changed since its stage wrote it is kept as it is. Delete it, or pass `--force`, to make it again.

**The orchestrator** (`python -m shorts run RUN`, `shorts/orchestrator.py`) runs the stages that are due, in order, each in a process of its own. Each runs in the Python set for its packages (`SHORTS_<EXTRA>_PYTHON`, for each extra in `pyproject.toml`), or in the orchestrator's own Python. The orchestrator knows the stages only by what they make and read. Where it can't go on, it says what's next and where that runs, and stops: a stage whose packages this machine doesn't have, a paid clip, files you bring in. `python -m shorts status RUN` shows each product's state.

**Bringing files in.** Anything a stage makes can come from elsewhere instead:

```sh
python -m shorts import RUN footage --name makable recordings/makable-tight.mp4   # with its .steps.json
python -m shorts import RUN intro gemini_generated_video.mp4         # a clip filmed in the Gemini app, HeyGen's, Higgsfield's…
python -m shorts import RUN outro https://example.com/outro.mp4      # or a link to it: the file's own link, not a page
python -m shorts import RUN narration ~/Downloads/download*.wav      # one audio file per scene
```

Narration files go in order by the numbers in their names (`download.wav`, `download (1).wav`, … `download (10).wav`, as browsers name repeated downloads); `--as-given` keeps your order. A file that's the same as one before it (downloaded twice) is left out.

Bringing a product in makes `run.json` say it's yours (`"narrator": "import"`, say). From then on the pipeline asks you for it again instead of making it: when a scene's text changes, its narration is out of date.

The scripts are in English or Hindi (`--language hi`), and friendly or excited like a Short (`--tone hype`). Each scene is said over its stretch of a recording, played at the speed that fits its narration, so what's said is on screen while it's said.

## Who films you

run.json's `intro` and `outro` say who films each clip from your photo (`python -m shorts new RUN --intro heygen --outro heygen`):

| | `omni` (the default) | `heygen` |
|---|---|---|
| What it is | Gemini Omni Flash films a new shot of you, in the script's `intro_setting` | HeyGen's photo to video animates your photo as it is |
| The voice | Omni's own, a new one each clip | one of HeyGen's, the same every clip: run.json's `filmer_voice` (`python -m shorts new RUN --filmer-voice ID`) |
| Keys | `GEMINI_API_KEY` (AI Studio's prepaid balance), or Agent Platform on Google Cloud credits (below) | `HEYGEN_API_KEY`, from HeyGen's API balance |
| Packages | the `gemini` extra | the `heygen` extra |

`python -m shorts voices --gender male` lists HeyGen's voices, each with a link to hear it. The narration is spoken in the intro's voice either way, so the video sounds like one person.

Anything else (Higgsfield, HeyGen's own site, the Gemini app) works too: film the clips there and bring them in, a file or a link to one (`python -m shorts import RUN intro CLIP`). A service with an API is one more `Filmer` in `shorts/filmers.py`: what it's made from, for knowing when to film again, and how it films a line.

## Recording by driving Chrome (`python -m shorts drive`)

This is how Claude Code records, in `/make-video`. Chrome runs in a process of its own that stays open, recording, and each command does one thing in it and prints the page as it is after it:

```sh
python -m shorts drive RUN start --signed-in        # opens makable, signed in as the demo user, and prints the page
python -m shorts drive RUN click 12 --goal "Open the site menu"
python -m shorts drive RUN type 9 "A one-page website for …" --goal "Describe the site"
python -m shorts drive RUN wait-for "Live preview" --timeout 240
python -m shorts drive RUN stop --report "what it showed"
```

- **The page.** `start`, `look` and every step print the tabs, the page's elements with a number each (what `click`, `type` and `scroll --number` take), and the path of a screenshot. They're browser-use's own, the ones its agent's model is shown.
- **The steps.** Each command is a step, kept with its `--goal`, what it did and when, in the same steps file `browse` writes. The other commands are `keys`, `scroll`, `wait`, `tab`, `open` and `act` (any other of browser-use's actions); `python -m shorts drive RUN --help` lists them.
- **Afterwards.** `stop` cuts out the time between commands and the still parts of the waits, as `browse` does, and brings the tight recording in as the footage.

It needs no model and no key: whoever sends the commands is the model, Claude Code here. The commands talk to the Chrome process on a local port with a token (`RUN/recordings/<name>.driving.json`, there while it records), so only that process needs browser-use (`SHORTS_BROWSE_PYTHON`, below). Its log is `RUN/recordings/<name>.drive.log`. A driver that's sent nothing for 30 minutes stops by itself, keeping what it recorded.

## Recording from a task (`python -m shorts browse`)

```sh
python -m shorts browse RUN --name demo --task task.md --signed-in
```

This has browser-use's agent do the task in `task.md` on makable, signed in as the demo user. The task is in plain words: what to do and show.

- **While it records:** Chrome's screencast is recorded in real time (`shorts/browse.py`), with a drawn mouse pointer gliding to each click, and each step's goal and times are kept.
- **Afterwards:** `cut_pauses` takes out the model's thinking, and the parts of its waits where nothing changes on the page. It plays typing 4× as fast, and zooms in on each click.
- **In the run:** the tight recording comes in as the footage `demo`, with its steps. The recordings, and what they were made with, stay in `RUN/recordings/`.

`python -m shorts frames RUN demo` makes contact sheets of the recording's frames, labelled with their times, to see what's on screen when.

The agent's model is `provider:model`, from `--model`, from `SHORTS_BROWSE_MODEL`, or the default `google:gemini-3.6-flash`:

| Prefix | Model | Key |
|---|---|---|
| `google:` | Gemini, through the Gemini API (the default) | `GEMINI_API_KEY` |
| `vertex:` | Gemini on Agent Platform | `GOOGLE_CLOUD_PROJECT` |
| `anthropic:` | Claude | `ANTHROPIC_API_KEY` |
| `openai:` | GPT, or any provider with OpenAI's API | `OPENAI_API_KEY`, plus `OPENAI_BASE_URL` for another provider |

A model that fails (429, 5xx) hands the rest of the run to `--fallback`.

browser-use pins its own packages, so it lives in an environment of its own. `browse` runs itself there when this environment doesn't have it, and `drive start` runs Chrome's process there:

```sh
uv venv ~/browse-env --python 3.12 && uv pip install --python ~/browse-env -e '.[browse]'
export SHORTS_BROWSE_PYTHON=~/browse-env/bin/python     # or in .env
```

## Recording makable signed in

browser-use can't do GitHub's sign-in, so a demo user signs in with a password instead. `shorts/signin.py` asks Supabase for a session for that user. It then gives Chrome the two cookies makable's backend sets after a GitHub sign-in (`makable_access`, `makable_refresh`), so the recording opens signed in. Every run gets a new session, so there's nothing to save between runs, and the backend doesn't change.

Set up once, in Supabase:

1. **A demo GitHub account.** Make a separate GitHub account and sign in to makable with it once. That creates the Supabase user and makable's user, with the GitHub token makable builds with. The agent really uses the site, so what it builds or publishes ends up on this account's GitHub, not yours.
2. **Give that user a password.** Copy the user's id from *Authentication → Users*. Then run this with the project's secret key (*Project Settings → API Keys*). That key can do anything, so keep it out of the repo:

   ```sh
   curl -X PUT "https://<ref>.supabase.co/auth/v1/admin/users/<user-id>" \
     -H "apikey: <secret key>" -H "Content-Type: application/json" \
     -d '{"password": "<a long random password>"}'
   ```

   With the legacy `service_role` key, also add `-H "Authorization: Bearer <service_role key>"`.
3. **Turn on the Email provider** (*Authentication → Sign In / Providers → Email*). Supabase refuses password sign-in without it.
4. **Allow only GitHub sign-ups.** With Email on, anyone can also sign up with an email and a password. makable wouldn't let them in (the backend only knows users who signed in with GitHub, so they'd get a 401), but they'd fill up your users and get confirmation emails. In the *SQL Editor*:

   ```sql
   create or replace function public.only_github_signups(event jsonb)
   returns jsonb
   language plpgsql
   as $$
   begin
     if event->'user'->'app_metadata'->>'provider' = 'github' then
       return '{}'::jsonb;
     end if;
     return jsonb_build_object('error', jsonb_build_object('http_code', 403, 'message', 'Sign up with GitHub.'));
   end;
   $$;

   grant execute on function public.only_github_signups to supabase_auth_admin;
   revoke execute on function public.only_github_signups from authenticated, anon, public;
   ```

   Then, in *Authentication → Hooks*, add a **Before User Created** hook of type Postgres that runs `public.only_github_signups`. Don't turn off *Allow new users to sign up* instead: that stops new GitHub users too.
5. **Four settings**, in `.env` locally and as repository secrets for GitHub Actions:
   - `SUPABASE_URL`: `https://<ref>.supabase.co`
   - `SUPABASE_PUBLISHABLE_KEY`: the one makable-backend uses
   - `MAKABLE_DEMO_EMAIL`: the demo user's email, shown in *Authentication → Users*
   - `MAKABLE_DEMO_PASSWORD`

Then `drive start --signed-in` and `browse --signed-in` record makable signed in. `signed_in` asks makable who the session belongs to before recording. A user makable doesn't know fails there with a clear error, instead of recording the signed-out page.

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

## Setting up, and the command line

```sh
uv venv --python 3.12 .venv && uv pip install --python .venv -e '.[gemini,assemble,speech]'
cp .env.example .env      # and fill it in
```

Each stage's packages are an extra of its own (`gemini`, `assemble`, `speech`; `browse` in its own environment), so a machine installs only what the stages it runs need. Everything needs ffmpeg.

Omni films with `GEMINI_API_KEY`, through the Gemini API (AI Studio), which only spends credits while a prepaid balance is above $0. Or it can film on Agent Platform (Vertex AI), which spends Google Cloud credits (the Free Trial's, Google AI Pro's) with no prepaid balance:

```sh
gcloud auth application-default login       # once; GitHub Actions uses google-github-actions/auth instead
export GOOGLE_GENAI_USE_ENTERPRISE=true GOOGLE_CLOUD_PROJECT=<project> GOOGLE_CLOUD_LOCATION=global
```

The Omni model id is picked for the backend (`shorts/intro.py`). Without Claude Code, a video is made like this:

```sh
.venv/bin/python -m shorts new runs/first --face assets/face.jpg --music assets/music.mp3   # [--language hi] [--tone hype]
.venv/bin/python -m shorts browse runs/first --name demo --task task.md --signed-in
.venv/bin/python -m shorts import runs/first script script.json   # checked first: check-script shows the problems
.venv/bin/python -m shorts status runs/first
.venv/bin/python -m shorts run runs/first --paid      # --paid: film the intro and outro too (about $1 each)
.venv/bin/python -m shorts speak runs/first           # or one stage at a time, here
```

The tests make small videos with ffmpeg and run the stages, the orchestrator and the voice API on them:

```sh
uv run --isolated --no-project --python 3.12 --with pydantic --with pillow --with pytest \
  --with fastapi --with python-multipart --with httpx python -m pytest   # without the last three, the API's tests are skipped
```
