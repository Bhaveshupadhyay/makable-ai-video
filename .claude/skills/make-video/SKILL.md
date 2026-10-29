---
name: make-video
description: Makes a makable Short, a 1-minute vertical video for YouTube Shorts and Instagram Reels, about something makable can do, from commits or from a prompt describing the functionality. You work out what to show, record it by driving the browser yourself, write the script from the recording, and the shorts pipeline films the avatar, speaks the narration and edits the video. Use when the user asks to make a video, a Short, a Reel or a demo of makable, or to write or redo a video's script.
argument-hint: "[commits or a prompt] [--tone hype] [--language hi] [--yes]"
allowed-tools: Read, Write, Edit, Bash(.venv/bin/python -m shorts:*), Bash(gh api:*), Bash(gh search code:*), Bash(git clone --depth 1:*), Bash(ffprobe:*)
---

# Making a makable Short

The request: $ARGUMENTS

The video is made by the `python -m shorts` pipeline in this repo. Its stages share a **run folder**
(`runs/<name>/`), and `shorts/run.py` describes every file in it. Your part is what needs judgment:

- what to show,
- recording it: you drive the browser, a command at a time,
- checking the recording,
- the script.

The pipeline does everything mechanical.

The finished video has three parts:

1. **Intro:** the avatar (filmed from the user's photo by Gemini Omni, or HeyGen) says a hook to the camera.
2. **The screen recording:** narrated in the avatar's voice by the voice API.
3. **Outro:** the avatar signs off.

The intro and outro are used as Omni filmed them.

Run the pipeline with `.venv/bin/python -m shorts …`. If `.venv` is missing, set it up once:
`uv venv --python 3.12 .venv && uv pip install --python .venv -e '.[gemini,assemble,speech]'`.
Chrome's process for the recording (`drive`) runs in browser-use's own environment, the Python that
`SHORTS_BROWSE_PYTHON` names (`.env.example` says `~/browse-env/bin/python`). If it's missing, set it up once:
`uv venv --python 3.12 ~/browse-env && uv pip install --python ~/browse-env -e '.[browse]'`.
Keys come from `.env` (see `.env.example`) or the environment. Never print their values.

**Interactive or not.** With `--yes` (GitHub Actions), never ask anything: decide, and say what you
decided in the final report. Otherwise, ask only where this says to.

## 1. What the video is about

The request gives commits, a prompt, or both:

- **Commits:** a SHA, `repo@sha`, a GitHub commit URL or a range `a..b`. The repo is
  `Bhaveshupadhyay/makable` (the app) unless named; `makable-backend@<sha>` is the backend. Read each commit
  with `gh api repos/<owner>/<repo>/commits/<sha>` (its message, files and patch), or a range with
  `gh api repos/<owner>/<repo>/compare/<a>...<b>`.
- **A prompt:** text describing the functionality to show, such as "show how to ask for a change and see it
  in the preview". Find it in the app's code: `gh search code --repo Bhaveshupadhyay/makable "<words>"`,
  or `git clone --depth 1 https://github.com/Bhaveshupadhyay/makable` into a temporary folder and search it.
  Find the page it's on, the path a user takes to it, and the exact labels of the buttons and boxes.
- **Both:** the prompt says what to focus on among the commits' changes.
- **Neither:** ask for commits or a description (interactive), or stop and say what's missing (`--yes`).

Pick the run's folder, `runs/<yyyy-mm-dd>-<slug>`, where the slug is a few words of what the video is about.
Write `changes.md` in it, with:
- what a user can now do, in a sentence;
- where it is in the UI, with the labels exactly as shown;
- the steps that show it;
- what the viewer should see at the end.

If nothing changed that a user can see (a refactor, a backend fix with no visible effect), say so and stop.
If a prompt is too vague to pick one flow, ask (interactive), or pick the most direct one (`--yes`).

## 2. The run

```sh
.venv/bin/python -m shorts new runs/<yyyy-mm-dd>-<slug> --face assets/face.jpg [--music assets/music.mp3] \
  [--tone hype] [--language hi]
```

The defaults are this flow's: an outro, and narration in the avatar's voice through the voice API.

- `--music` only if that file exists.
- `--tone` and `--language` from the request (friendly and English by default).
- If `assets/face.jpg` is missing, ask for the user's photo (interactive), or stop (`--yes`).
- **Who films the user** (README's Who films you): Omni by default. If the user asks for HeyGen, add
  `--intro heygen --outro heygen --filmer-voice VOICE_ID`. To pick the voice, run
  `.venv/bin/python -m shorts voices --gender male` (or `female`, for the person in the photo): offer two or
  three, with their preview links (interactive), or take the first (`--yes`). If the user films the clips
  somewhere else (Higgsfield, HeyGen's site, the Gemini app), they come in at step 7 instead, from a file or a
  link: `.venv/bin/python -m shorts import RUN intro FILE_OR_LINK` (and `outro`).

## 3. Record it

You drive the recording yourself, in a Chrome that the pipeline records, following
[references/drive.md](references/drive.md). Plan the steps from `changes.md` first, then:

```sh
.venv/bin/python -m shorts drive RUN start --signed-in       # opens makable signed in, and prints the page
.venv/bin/python -m shorts drive RUN click 12 --goal "Open the site menu"   # each prints the page after it
.venv/bin/python -m shorts drive RUN wait-for "Live preview" --timeout 240
.venv/bin/python -m shorts drive RUN stop --report "…"       # brings it in as the footage demo, with its steps
```

The time you spend thinking between commands is cut out of the footage, and so are the still parts of
the waits.

**Or browser-use's agent**, if the user asks for it: write the task to `RUN/task.md`, following
[references/task.md](references/task.md), and run
`.venv/bin/python -m shorts browse RUN --name demo --task RUN/task.md --signed-in` in the background. It
needs a model's key: `SHORTS_BROWSE_MODEL` (default `google:gemini-3.6-flash`, with `GEMINI_API_KEY`), or
`--model provider:model`.

## 4. Check the recording

- **The steps:** read `RUN/footage/demo.steps.json`.
- **The frames:** run `.venv/bin/python -m shorts frames RUN demo` and look at every sheet in
  `RUN/frames/`. For small text, look again with `--at <seconds> … --width 720`.

Does it show what `changes.md` says, through to the result? Trust the frames over the report.

If the recording doesn't show the change, record it again (a new `start` replaces the footage), at most
twice more. If it still doesn't, stop and report what went wrong. An error that was retried and then
worked is fine: the script skips it.

## 5. The script

Follow [references/script.md](references/script.md). Write it to `RUN/drafts/script.json`. Then run:

```sh
.venv/bin/python -m shorts check-script RUN RUN/drafts/script.json
```

Fix every error, and every warning unless there's a reason not to. When it's clean, run
`.venv/bin/python -m shorts import RUN script RUN/drafts/script.json`.

## 6. Approval (skip with `--yes`)

Filming costs money, so show the user:
- the intro line, each scene (its stretch, its speed from `check-script` and its text), the outro line,
  the title and the description;
- anything you left out of the recording, and why.

Then ask: film it, change something, or stop. Filming costs about two dollars (the intro and the outro,
about a dollar each).

## 7. Make it

```sh
.venv/bin/python -m shorts run RUN --paid
```

This takes a few minutes, so run it in the background. It does everything that's due, in order:
1. films the intro and the outro (Omni or HeyGen, as `run.json` says);
2. takes the avatar's voice from the intro;
3. has the voice API speak each scene in it (`SHORTS_SPEECH_URL` and `SHORTS_SPEECH_KEY`);
4. assembles `RUN/final.mp4` with captions and music.

If it stops, it says why and what's next. Fix that and run it again: only what's missing or out of date
is made again. Never delete `intro/filmed.mp4` or `outro/filmed.mp4` without asking, since each costs about
a dollar to film again.

## 8. Report

Tell the user:
- the video's path and length (`RUN/metadata.json` has its seconds, title and description);
- the scenes as they were made;
- anything to check by eye or ear: Omni sometimes says a line a little differently, and the outro's voice
  can differ from the intro's, since each clip is a separate take. If one is off, delete that clip and run
  step 7 again to film it again (about a dollar).

In `--yes` mode, also say what you decided on your own.
