---
name: make-video
description: Makes a makable Short, a 1-minute vertical video for YouTube Shorts and Instagram Reels, about something makable can do, from commits or from a prompt describing the functionality. You work out what to show, brief browser-use to record it, write the script from the recording, and the shorts pipeline films the avatar, speaks the narration and edits the video. Use when the user asks to make a video, a Short, a Reel or a demo of makable, or to write or redo a video's script.
argument-hint: "[commits or a prompt] [--tone hype] [--language hi] [--yes]"
allowed-tools: Read, Write, Edit, Bash(.venv/bin/python -m shorts:*), Bash(gh api:*), Bash(gh search code:*), Bash(git clone --depth 1:*), Bash(ffprobe:*)
---

# Making a makable Short

The request: $ARGUMENTS

The video is made by the `python -m shorts` pipeline in this repo. Its stages share a **run folder**
(`runs/<name>/`), and `shorts/run.py` describes every file in it. Your part is what needs judgment:

- what to show,
- the browser-use task,
- checking the recording,
- the script.

The pipeline does everything mechanical.

The finished video has three parts:

1. **Intro:** the avatar (Gemini Omni, filmed from the user's photo) says a hook to the camera.
2. **The screen recording:** narrated in the avatar's voice by the voice API.
3. **Outro:** the avatar signs off.

The intro and outro are used as Omni filmed them.

Run the pipeline with `.venv/bin/python -m shorts …`. If `.venv` is missing, set it up once:
`uv venv --python 3.12 .venv && uv pip install --python .venv -e '.[gemini,record,assemble,speech]'`.
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
Write `changes.md` in it (step 2 reads it into the run's settings), with:
- what a user can now do, in a sentence;
- where it is in the UI, with the labels exactly as shown;
- the steps that show it;
- what the viewer should see at the end.

If nothing changed that a user can see (a refactor, a backend fix with no visible effect), say so and stop.
If a prompt is too vague to pick one flow, ask (interactive), or pick the most direct one (`--yes`).

## 2. The run

```sh
.venv/bin/python -m shorts new runs/<yyyy-mm-dd>-<slug> --changes runs/<…>/changes.md \
  --script import --outro omni --intro-voice as-filmed --narration-voice intro --narrator api \
  --face assets/face.jpg [--music assets/music.mp3] [--tone hype] [--language hi]
```

- `--music` only if that file exists.
- `--tone` and `--language` from the request (friendly and English by default).
- If `assets/face.jpg` is missing, ask for the user's photo (interactive), or stop (`--yes`).

## 3. Record it

Write the task to `RUN/task.md`, following [references/task.md](references/task.md). Then record. It takes
several minutes (makable builds while it records), so run it in the background and wait for it to finish:

```sh
.venv/bin/python -m shorts browse RUN --name demo --task RUN/task.md --signed-in
```

It uses `SHORTS_BROWSE_MODEL` (default `google:gemini-3.6-flash`; `--model provider:model` for another),
and brings the tight recording into the run as the footage `demo`, with its steps. It prints the agent's
final report.

## 4. Check the recording

- **The steps:** read `RUN/footage/demo.steps.json`.
- **The frames:** run `.venv/bin/python -m shorts frames RUN demo` and look at every sheet in
  `RUN/frames/`. For small text, look again with `--at <seconds> … --width 720`.

Does it show what `changes.md` says, through to the result? The agent's report can be wrong, so trust the
frames over it.

If the recording doesn't show the change (the agent failed, ran out of steps or did something else),
improve the task and record again, at most twice more. If it still doesn't, stop and report what went
wrong. An error that was retried and then worked is fine: the script skips it.

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

Then ask: film it, change something, or stop. Filming costs about $2 (the intro and the outro, about $1
each).

## 7. Make it

```sh
.venv/bin/python -m shorts run RUN --paid
```

This takes a few minutes, so run it in the background. It does everything that's due, in order:
1. films the intro and the outro (Omni);
2. takes the avatar's voice from the intro;
3. has the voice API speak each scene in it (`SHORTS_SPEECH_URL` and `SHORTS_SPEECH_KEY`);
4. assembles `RUN/final.mp4` with captions and music.

If it stops, it says why and what's next. Fix that and run it again: only what's missing or out of date
is made again. Never delete `intro/filmed.mp4` or `outro/filmed.mp4` without asking, since each costs about
$1 to film again.

## 8. Report

Tell the user:
- the video's path and length (`RUN/metadata.json` has its seconds, title and description);
- the scenes as they were made;
- anything to check by eye or ear: Omni sometimes says a line a little differently, and the outro's voice
  can differ from the intro's, since each clip is a separate take. If one is off, delete that clip and run
  step 7 again to film it again (about $1).

In `--yes` mode, also say what you decided on your own.
