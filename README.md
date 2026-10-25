# makable Shorts

Makes a 1-minute vertical video (YouTube Shorts, Instagram Reels) about a change in makable: a 10-second intro of you filmed by Gemini Omni Flash, then a narrated screen recording, all in your cloned voice, with captions and music.

## How it's built: stages that share a folder

The video is made by six stages. Each is a program of its own (`python -m shorts <stage> RUN`) with its own packages, and they share nothing but the video's **run folder**: each reads the files the stages before it wrote there and writes its own, under fixed names. No stage calls or imports another, so each can run on a different machine (the voices on Colab's GPU, the rest anywhere), be swapped for another tool, or be skipped by bringing its files in (`python -m shorts import`).

| Stage | Makes (in the run folder) | From | With | Runs on |
|---|---|---|---|---|
| `record` | `footage/<name>.mp4` (+ `.steps.json`) | `run.json`'s `footage`: files, or pages to record | Playwright (`shorts/footage.py`) | anywhere |
| `write-script` | `script.json` | the footage's steps (or `changes`) | Gemini (`shorts/script.py`), free tier | anywhere |
| `film-intro` | `intro/filmed.mp4` | the intro line, your photo | Gemini Omni Flash (`shorts/intro.py`), **about $1** | anywhere |
| `revoice-intro` | `intro/voiced.mp4`, `intro/speech.wav` | the filmed intro, your voice sample | Demucs + Chatterbox (`shorts/voice.py`) | a GPU |
| `speak` | `narration/01.wav`, `02.wav`, … | each scene's text, your voice sample | Chatterbox or OmniVoice | a GPU |
| `assemble` | `final.mp4`, `metadata.json` | all of the above, music | ffmpeg + Pillow (`shorts/compose.py`, `shorts/captions.py`) | anywhere |

What the video is made from is the run's `run.json` (footage, voice sample, photo, music, language, tone, narrator and its settings; `python -m shorts new` writes it, and it's yours to edit). The contract, the names and formats every stage reads and writes, is in `shorts/run.py`.

**Only what changed is made again.** Each stage notes, in `.records/<product>.json`, what each of its files was made from (a fingerprint of the scene's text, the voice sample, the settings) and of the file as written. A file is out of date when what it would be made from now is different, and only that file is made again: edit one scene's text and only its narration is spoken again. A file that changed since its stage wrote it was edited by hand, and it's kept as it is (so an edited `script.json` stays, even when the tone changes); delete it, or pass `--force`, to make it again.

**The orchestrator** (`python -m shorts run RUN`, `shorts/orchestrator.py`) runs the stages that are due, in order, each in a process of its own, in the Python set for its packages (`SHORTS_VOICE_PYTHON=~/chatterbox/bin/python`, say; `SHORTS_<EXTRA>_PYTHON` for each extra in `pyproject.toml`), or its own. It knows the stages only by what they make and read. Where it can't go on (a stage whose packages this machine doesn't have, the paid intro, files you bring in), it says what's next and where that runs, and stops. `python -m shorts status RUN` shows each product's state.

**Bringing files in.** Anything a stage makes can come from elsewhere instead:

```sh
python -m shorts import RUN footage --name makable recordings/makable-tight.mp4   # with its .steps.json
python -m shorts import RUN script script.json
python -m shorts import RUN intro gemini_generated_video.mp4         # Omni's clip, in Omni's voice
python -m shorts import RUN voiced-intro intro-in-your-voice.mp4     # the intro in your voice already
python -m shorts import RUN narration ~/Downloads/download*.wav      # one audio file per scene
```

Narration files go in order by the numbers in their names (`download.wav`, `download (1).wav`, … `download (10).wav`, as browsers name repeated downloads; `--as-given` keeps your order), and a file that's the same as one before it, downloaded twice, is left out. Bringing a product in makes `run.json` say it's yours (`"narrator": "import"`, say), so the pipeline asks for it again (when a scene's text changes, its narration is out of date) instead of making it. For the Crumb & Co files:

```sh
python -m shorts new runs/crumb-and-co --footage makable=recordings/makable-tight.mp4
python -m shorts import runs/crumb-and-co script runs/crumb-and-co/script.json
python -m shorts import runs/crumb-and-co voiced-intro ~/Downloads/intro__gwr_video_mvp.mp4
python -m shorts import runs/crumb-and-co narration ~/Downloads/download*.wav
python -m shorts run runs/crumb-and-co      # copies the footage in, then assembles final.mp4
```

`record_with_browser_use.ipynb` makes footage from instructions: browser-use's agent does a task described in words while Chrome's screencast is recorded in real time (`shorts/browse.py`, `shorts/signin.py`; with a drawn mouse pointer gliding to each click), with each step's goal and times, and `cut_pauses` takes out the model's thinking and the parts of its waits where nothing changes on the page, plays typing 4× as fast and zooms in on each click. browser-use pins its own `google-genai` and `numpy`, so it's not a stage the orchestrator runs: name the recording it makes in `run.json`'s `footage`, and `record` copies it in with its steps.

The scripts are in English or Hindi (`--language hi`), friendly or excited like a Short (`--tone hype`). Each scene is said over its stretch of a recording, played at the speed that fits its narration, so what's said is on screen while it's said.

## Google Colab

Open `makable_shorts.ipynb` in Colab (T4 GPU) and follow it: a cell for each stage, run as on the command line (`shorts("speak", RUN)`), so each stage hands the GPU's memory back when it's done. `record_with_browser_use.ipynb` (CPU) is separate, because browser-use pins its own `google-genai` and `numpy`. `voice_from_script.ipynb` (T4 GPU) makes the voices without the rest of the video: it takes the voice from a recording (a video works, such as Omni's intro), speaks a script's scenes in it and shows how long each runs. Chatterbox reads the words in `shorts.voice.PRONOUNCE` respelled ("makable" as "makeable"), and the captions keep the script's spelling. It speaks livelier than its default (`shorts.voice.DELIVERY`). The notebook plays a sentence in a few spellings, and a scene in a few deliveries, to choose from, and puts your choice in the run's `run.json`. `omnivoice_from_script.ipynb` (T4 GPU) speaks a script with OmniVoice alone (see below). The notebooks write the `shorts` files themselves, so after changing anything in `shorts/`, rebuild them:

```sh
python3 build_notebook.py
```

`./sync_drive.sh` does that and pushes the code to `My Drive/makable-shorts/` (with [rclone](https://rclone.org), its remote named `gdrive`), to open the notebooks in Colab from there. It sends only what changed, and keeps whatever it replaces on Drive (such as a notebook Colab saved with its outputs) in `makable-shorts/.replaced/`.

## Narrating a recording with audio made elsewhere

For the whole video from scenes spoken elsewhere, bring them into a run (above). `narrate_recording.py` makes just the narrated recording: it puts a script's scenes, already spoken (one audio file per scene, in the scenes' order), over the recording the script was written from. It cuts out each scene's stretch (`start` to `end` in script.json), plays it at the speed that makes it last as long as its audio plus a short pause, and joins them. No intro, captions or music; it needs ffmpeg and the `shorts` package next to it:

```sh
python3 narrate_recording.py recordings/makable-tight.mp4 runs/crumb-and-co/script.json \
  assets/download\ \(*\).wav -o makable-tight-narrated.mp4
```

It prints each scene's stretch and speed, to check the audio files are in the right order. In Colab, `narrate_recording.ipynb` (CPU runtime) does the same: it asks you to upload the screen recording, reads the run's `script.json` from Drive, asks for the audio files (all at once: it puts them in order by the numbers in their names, `download.wav` first, and leaves out any downloaded twice) and saves the video in the run's folder.

## Putting the intro before a recording

`merge_intro.py` makes a video from the intro and a screen recording: the intro, then the recording, each with its own sound, in one 1080×1920 MP4 (`--size 1920x1080` for a wide one). A clip the frame's shape fills it; any other (a desktop recording in a vertical video) is shown whole over a blurred, darker copy of itself. The recording can be narrated already (with `narrate_recording.py`, above) or silent. Omni's clip speaks in Omni's voice, so give it the intro in yours (a run's `intro/voiced.mp4`), or pass Omni's clip with `--intro-audio` and the intro's sound in your voice. The sound is evened out to -14 LUFS. No captions or music:

```sh
python3 merge_intro.py runs/crumb-and-co/intro/voiced.mp4 makable-tight-narrated.mp4 \
  -o makable-tight-final.mp4
```

It prints each part's size and length, how it fits the frame and where its sound is from. In Colab, `merge_intro.ipynb` (CPU runtime) does the same: it asks you to upload the intro avatar video, then the screen recording (or takes them from Drive), and saves the video in the run's folder. Both scripts use the pipeline's video engine (`shorts/compose.py`), so they make what `assemble` would.

## Recording makable signed in

browser-use can't do GitHub's sign-in, so a demo user signs in with a password instead. `shorts/signin.py` asks Supabase for a session with it and gives Chrome the two cookies makable's backend sets after a GitHub sign-in (`makable_access`, `makable_refresh`), so the recording opens signed in. Every run gets a new session, so there's nothing to save between runs, and the backend doesn't change.

Set up once, in Supabase:

1. **A demo GitHub account.** Make a separate GitHub account and sign in to makable with it once. That creates the Supabase user and makable's user, with the GitHub token makable builds with. The agent really uses the site, so what it builds or publishes ends up on this account's GitHub, not yours.
2. **Give that user a password.** Copy the user's id from *Authentication → Users*, then run this with the project's secret key (*Project Settings → API Keys*; it can do anything, so keep it out of the notebook and the repo):

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
5. **Four secrets** (Colab: 🔑 in the left bar; GitHub Actions: repository secrets): `SUPABASE_URL` (`https://<ref>.supabase.co`), `SUPABASE_PUBLISHABLE_KEY` (the one makable-backend uses), `MAKABLE_DEMO_EMAIL` (the demo user's email, shown in *Authentication → Users*) and `MAKABLE_DEMO_PASSWORD`.

Then section 3 of `record_with_browser_use.ipynb` records makable signed in. `signed_in` asks makable who the session belongs to before recording, so a user makable doesn't know fails there with a clear error, instead of recording the signed-out page.

## Command line (and later GitHub Actions)

```sh
pip install -e '.[gemini,record,assemble]'   # the stages this machine runs: see the extras in pyproject.toml
gcloud auth application-default login       # once; GitHub Actions uses google-github-actions/auth instead
export GOOGLE_GENAI_USE_ENTERPRISE=true GOOGLE_CLOUD_PROJECT=<project> GOOGLE_CLOUD_LOCATION=global

python -m shorts new runs/first --changes changes.txt \
  --footage editor=recordings/editor.mp4 --footage home=https://... \
  --voice assets/voice.wav --face assets/face.jpg --music assets/music.mp3   # [--language hi] [--tone hype]
python -m shorts status runs/first
python -m shorts run runs/first --paid      # --paid: film the intro too (about $1), when it's due
python -m shorts speak runs/first           # or one stage at a time, here
```

That's Agent Platform (Vertex AI), which spends Google Cloud credits (the Free Trial's, Google AI Pro's) with no prepaid balance. With `GEMINI_API_KEY=<key>` instead, it uses the Gemini API (AI Studio), which only spends credits while a prepaid balance is above $0. The Omni model id is picked for the backend (`shorts/intro.py`).

Each stage's packages are an extra of its own (`record`, `gemini`, `voice`, `omnivoice`, `assemble`), so a machine installs only what the stages it runs need. `voice` (Chatterbox) and `omnivoice` can't share an environment (chatterbox-tts pins an older `transformers`), nor can `browse` and `voice`; uv knows (`[tool.uv] conflicts`). Everything needs ffmpeg, and `record` needs `playwright install chromium` for pages.

The tests make small videos with ffmpeg and run the stages and the orchestrator on them:

```sh
uv run --no-project --python 3.12 --with pydantic --with pillow --with pytest python -m pytest
```

## OmniVoice (instead of Chatterbox's narration)

[OmniVoice](https://github.com/k2-fsa/OmniVoice) clones a voice from a few seconds of it, in 646 languages. With `"narrator": "omnivoice"` in `run.json` (`python -m shorts new RUN --narrator omnivoice`), `speak` has it speak the scenes; it only speaks text, so Chatterbox still converts the intro. Its settings go in `narrator_options` (`--narrator-option speed=1.1`), and what's said in the voice sample in `reference_text` (Whisper writes it down without one). The voice sample works best at 3 to 10 seconds; the first scene also downloads the model (about 2.4 GB).

Where OmniVoice runs is the machine's business, not the video's, so it comes from the environment: `OMNIVOICE_ENV` is the folder of an environment of its own, `~/omnivoice-env` by default, which it installs with uv the first time (a few minutes) and runs in a process of its own (`shorts/omnivoice_worker.py`); `OMNIVOICE_ENV=here` runs it in the same Python. In Colab, `omnivoice_from_script.ipynb` speaks a run's script with it, alone (no Chatterbox there, so OmniVoice installs into Colab's own Python, `here`). `NARRATOR = "omnivoice"` in `makable_shorts.ipynb` (section 1) then makes the video with those scenes, as they are.
