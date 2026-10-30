---
name: make-video
description: Makes a Short, a 1-minute vertical video for YouTube Shorts and Instagram Reels, showing something the user's own web product can do, from its commits or from a prompt describing the functionality. You work out what to show, record it by driving the browser yourself, write the script from the recording, and the shorts pipeline films the user's avatar from their photo, speaks the narration and edits the video. Use when the user asks to make a video, a Short, a Reel or a product demo, or to write or redo a video's script.
argument-hint: "[product] [commits or a prompt] [--tone hype] [--language hi] [--yes]"
allowed-tools: Read, Write, Edit, Bash(makable-shorts *), Bash(gh api *), Bash(gh search code *), Bash(git clone --depth 1 *), Bash(git -C *), Bash(ffprobe *)
---

# Making a Short about a product

The request: $ARGUMENTS

The video is made by this plugin's pipeline, the `makable-shorts` command. Its stages share a **run folder**
(`runs/<name>/`, in the working directory), and `${CLAUDE_PLUGIN_ROOT}/shorts/run.py` describes every file in it. Your part is what needs judgment:

- what to show,
- recording it: you drive the browser, a command at a time,
- checking the recording,
- the script.

The pipeline does everything mechanical.

The finished video has three parts:

1. **Intro:** the user's avatar (filmed from their photo by Gemini Omni, or HeyGen) says a hook to the camera.
2. **The screen recording** of the product, narrated in the avatar's voice by the voice API.
3. **Outro:** the avatar signs off.

The intro and outro are used as they were filmed.

Run the pipeline with `makable-shorts …`: the plugin puts it on the Bash tool's PATH. The first time, and after an
update, a command sets up its Python environments first, which takes a few minutes: give it a Bash timeout of
600000 ms. It needs uv and ffmpeg, and says how to install one that's missing: tell the user, and stop.

Keys come from the environment, or from `.env` in SHORTS_HOME: `${CLAUDE_PLUGIN_ROOT}/.env.example` lists them, and
where to get each. Never print their values, and never ask the user to paste one into the chat.

**Interactive or not.** With `--yes` (GitHub Actions), never ask anything: decide, and say what you
decided in the final report. Otherwise, ask only where this says to.

**Redoing a video's script.** If the request is to write or redo the script of a video already started (it names
its run, `runs/<…>`, or it's the one just made), don't record again: go to step 6 in that run, whose footage,
steps and `changes.md` are there, with the notes of the product it's about. Then steps 7 and 8, where only what
the new script changes is made again: the narration of each scene whose text changed, and the intro or the outro
(about a dollar each) only if its line or its setting did.

## 1. The product, and the user's files

Run `makable-shorts me`. It prints where the user's own things are kept (SHORTS_HOME), and:

- `face`, `music`, `voice`: their photo, the music under their videos, a sample of their voice;
- `products`: the products there are notes on (`products/<name>.md` there);
- `signed in`: the sites they've signed in to, for recordings that need it;
- `keys`: which keys are set, for step 8. Filming needs the key of whoever films the user (step 3): for Omni, the
  default, `GEMINI_API_KEY` (or `GOOGLE_CLOUD_PROJECT`, for Google Cloud); for HeyGen, `HEYGEN_API_KEY`; none for
  clips the user brings in. The narration needs `SHORTS_SPEECH_URL` and `SHORTS_SPEECH_KEY`. If one this video needs
  is missing, tell the user now which, and to add it to the `.env` that `me` names (copying
  `${CLAUDE_PLUGIN_ROOT}/.env.example`), then go on. With `--yes`, stop.

**The product.** Every video is about one product, and its notes say how to record it and how to talk about it
([references/product.md](references/product.md)). Read them before anything else.
- If the request names a product, or there are notes on only one, it's that one.
- If there are notes on several and the request doesn't say which, ask (interactive), or stop and say so (`--yes`).
- If there are none for it, set them up with the user as product.md says (interactive), or stop (`--yes`).

**The photo.** Whoever films the avatar needs a photo of the user. If `me` shows no `face`, ask for one: their
face and shoulders, looking at the camera, in good light. One with the background removed is best, since Omni
films the setting the script describes. Keep it with `makable-shorts me --face PATH`. Ask about
music at the same time, once: a file of their own (`me --music PATH`), or none. With `--yes` and no face, stop.

## 2. What the video is about

The request gives commits, a prompt, or both:

- **Commits:** a SHA, `repo@sha`, a GitHub commit URL or a range `a..b`, in the product's code (the notes'
  `code`). Read each commit with `gh api repos/<owner>/<repo>/commits/<sha>` (its message, files and patch), or
  a range with `gh api repos/<owner>/<repo>/compare/<a>...<b>`. For code in a folder on this machine, use
  `git -C <folder> show <sha>`, or `git -C <folder> log -p <a>..<b>`.
- **A prompt:** text describing the functionality to show, such as "show how to share a note with a teammate".
  Find it in the product's code: `gh search code --repo <owner>/<repo> "<words>"`, or
  `git clone --depth 1 https://github.com/<owner>/<repo>` into a temporary folder and search it. With no code,
  find it on the product itself, with `drive start` and `look`. Find the page it's on, the path a user takes to
  it, and the exact labels of the buttons and boxes.
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

## 3. The run

```sh
makable-shorts new runs/<yyyy-mm-dd>-<slug> [--tone hype] [--language hi] [--pronounce WORD=SAID ...]
```

A new run takes the user's photo, music and voice from `me`. The defaults are this flow's: an outro, and
narration in the avatar's voice through the voice API.

- `--tone` and `--language` from the request (friendly and English by default).
- `--pronounce` for each of the notes' `pronounce` words in the run's language.
- **Who films the user** (`${CLAUDE_PLUGIN_ROOT}/README.md`'s Who films you): Omni by default. If the user asks for HeyGen, add
  `--intro heygen --outro heygen --filmer-voice VOICE_ID`. HeyGen animates the photo as it is, background and
  all. To pick the voice, run `makable-shorts voices --gender male` (or `female`, for the person
  in the photo): offer two or three, with their preview links (interactive), or take the first (`--yes`).
  If the user films the clips somewhere else (Higgsfield, HeyGen's site, the Gemini app), they come in at
  step 8 instead, from a file or a link: `makable-shorts import RUN intro FILE_OR_LINK` (and `outro`).

## 4. Record it

You drive the recording yourself, in a Chrome that the pipeline records, following
[references/drive.md](references/drive.md) and the notes' recording tips. Plan the steps from `changes.md` first.

**Signed in.** If the notes say `signed_in`, the recording starts with `--signed-in`, in the session the user
left when they signed in by hand. If `me` doesn't list the site under `signed in`, have them sign in first: run
`makable-shorts signin --url <url>` in the background, and tell them "Chrome is open on <url>: sign
in there, then close the window." It finishes when they close it. Do the same if a recording opens on the
sign-in page: the session has run out. With `--yes`, stop and say the site needs signing in first.

```sh
makable-shorts drive RUN start --url <url> --signed-in --window 720x1280   # prints the page
makable-shorts drive RUN click 12 --goal "Open the share menu"              # each prints the page after it
makable-shorts drive RUN type 9 "My teammate's email" --goal "Add a teammate"
makable-shorts drive RUN wait-for "Shared" --timeout 240
makable-shorts drive RUN stop --report "…"    # brings it in as the footage demo, with its steps
```

`<url>` is the notes' `url`, or a page deeper in where the flow starts, and the window is the notes'.
The time you spend thinking between commands is cut out of the footage, and so are the still parts of
the waits. The spotlight (`--spotlight` on a `click` or a `type`, blurring the rest of the page while it
happens) is off: use it only when the user asks for it, and never on a button.

**Or browser-use's agent**, if the user asks for it: write the task to `RUN/task.md`, following
[references/task.md](references/task.md), and run
`makable-shorts browse RUN --url <url> --name demo --task RUN/task.md [--signed-in] [--window …]` in
the background. It needs a model's key: `SHORTS_BROWSE_MODEL` (default `google:gemini-3.6-flash`, with
`GEMINI_API_KEY`), or `--model provider:model`.

## 5. Check the recording

- **The steps:** read `RUN/footage/demo.steps.json`.
- **The frames:** run `makable-shorts frames RUN demo` and look at every sheet in
  `RUN/frames/`. For small text, look again with `--at <seconds> … --width 720`.

Does it show what `changes.md` says, through to the result? Trust the frames over the report.

If the recording doesn't show the change, record it again (a new `start` replaces the footage), at most
twice more. If it still doesn't, stop and report what went wrong. An error that was retried and then
worked is fine: the script skips it.

Then add what the next recording should know to the notes' recording tips (product.md says how).

## 6. The script

Follow [references/script.md](references/script.md). Write it to `RUN/drafts/script.json`. Then run:

```sh
makable-shorts check-script RUN RUN/drafts/script.json
```

Fix every error, and every warning unless there's a reason not to. When it's clean, run
`makable-shorts import RUN script RUN/drafts/script.json`.

## 7. Approval (skip with `--yes`)

Filming costs money, so show the user:
- the intro line, each scene (its stretch, its speed from `check-script` and its text), the outro line,
  the title and the description;
- anything you left out of the recording, and why.

Then ask: film it, change something, or stop. Filming costs about two dollars (the intro and the outro,
about a dollar each).

## 8. Make it

```sh
makable-shorts run RUN --paid
```

This takes a few minutes, so run it in the background. It does everything that's due, in order:
1. films the intro and the outro (Omni or HeyGen, as `run.json` says);
2. takes the avatar's voice from the intro;
3. has the voice API speak each scene in it (`SHORTS_SPEECH_URL` and `SHORTS_SPEECH_KEY`);
4. assembles `RUN/final.mp4` with captions and music.

If it stops, it says why and what's next. Fix that and run it again: only what's missing or out of date
is made again. Never delete `intro/filmed.mp4` or `outro/filmed.mp4` without asking, since each costs about
a dollar to film again.

## 9. Report

Tell the user:
- the video's path and length (`RUN/metadata.json` has its seconds, title and description);
- the scenes as they were made;
- anything to check by eye or ear: Omni sometimes says a line a little differently, and the outro's voice
  can differ from the intro's, since each clip is a separate take. If one is off, delete that clip and run
  step 8 again to film it again (about a dollar).

In `--yes` mode, also say what you decided on your own.
