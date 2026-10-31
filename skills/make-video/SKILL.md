---
name: make-video
description: Makes a Short, a 1-minute vertical video for YouTube Shorts and Instagram Reels, showing something the user's own web product can do, from its commits or from a prompt describing the functionality. You work out what to show, record it by driving the browser yourself, write the script from the recording, and the shorts pipeline films the user's avatar from their photo, speaks the narration and edits the video. Use when the user asks to make a video, a Short, a Reel or a product demo, or to write or redo a video's script.
argument-hint: "[product] [commits or a prompt] [--tone hype] [--language hi] [--yes]"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(makable-shorts *), Bash(git show *), Bash(git log *), Bash(git diff *), Bash(gh api *), Bash(gh search code *), Bash(git clone --depth 1 *), Bash(git -C *), Bash(ffprobe *)
---

# Making a Short about a product

The request: $ARGUMENTS

The video is made by this plugin's pipeline, the `makable-shorts` command. Its stages share a **run folder**
(`.makable-shorts/runs/<name>/` in the project), and `${CLAUDE_PLUGIN_ROOT}/shorts/run.py` describes every file in it. Your part is what needs judgment:

- what to show,
- recording it: you drive the browser, a command at a time,
- checking the recording,
- the script.

The pipeline does everything mechanical.

The finished video has three parts:

1. **Intro:** the user's avatar says a hook to the camera: filmed from their photo by Gemini Omni or HeyGen, or a
   clip they film elsewhere and bring in.
2. **The screen recording** of the product, narrated in the avatar's voice by ElevenLabs, or by the user's own voice
   API on Modal.
3. **Outro:** the avatar signs off.

The intro and outro are used as they were filmed.

Run the pipeline with `makable-shorts …`: the plugin puts it on the Bash tool's PATH. The first time, and after an
update, a command sets up its Python environments first, which takes a few minutes: give it a Bash timeout of
600000 ms. It needs uv and ffmpeg, and says how to install one that's missing: tell the user, and stop.

Keys come from the environment, or from `.env` in SHORTS_HOME, which the user fills in themselves (step 1). Never
print a key's value, never read the `.env`, and never ask the user to paste a key into the chat.

**Interactive or not.** With `--yes` (GitHub Actions), never ask anything: decide, and say what you
decided in the final report. Otherwise, ask only where this says to.

**The product's own repo** is the best place to make its videos: the user runs Claude Code there. Then you have
its code at hand, to plan the recording and write the script from. Its notes are kept in it, committed, so teammates
and the GitHub workflow share them, and the run folders go in it too, in `.makable-shorts/runs/`, which git ignores.
Anywhere else works too, from notes in SHORTS_HOME and the code on GitHub.

**Redoing a video's script.** If the request is to write or redo the script of a video already started (it names
its run, a folder in `.makable-shorts/runs/`, or it's the one just made), don't record again: go to step 6 in that run, whose footage,
steps and `changes.md` are there, with the notes of the product it's about. Then steps 7 and 8, where only what
the new script changes is made again: the narration of each scene whose text changed, and the intro or the outro
(about a dollar each) only if its line or its setting did.

## 1. The product, and the user's files

Run `makable-shorts me`. It prints where the user's own things are kept (SHORTS_HOME), and:

- `face`, `music`, `voice`: their photo, the music under their videos, a sample of their voice;
- `filmer`, `narrator`: who films their avatar and who speaks the narration, as they chose (below);
- `products`: the notes on each product, and where each is: the project's own (`.makable-shorts/products/` in
  this repo), or SHORTS_HOME's;
- `signed in`: the sites they've signed in to, for recordings that need it;
- `runs`: where this project's run folders go;
- `keys`: which of the keys their choices need are set, for step 8, and with Omni, whether Google Cloud's sign-in
  is on this machine (`google`).

**Who films the user, and who speaks.** If `me` shows `filmer` or `narrator` not chosen, ask once, in one message
(interactive):

- **Who films their intro and outro**, from their photo:
  - **Gemini Omni** (`omni`), in their own Google Cloud project: about $1 a clip, from its billing or its credits.
    It films a new shot of them in the setting the script describes, in a voice of its own.
  - **HeyGen** (`heygen`), from their HeyGen API balance. It animates the photo as it is, background and all, in
    one of HeyGen's voices, the same every video.
  - **Their own clips** (`import`): for each video, they film the intro and the outro elsewhere (Higgsfield,
    HeyGen's site, the Gemini app) and give you the files or links. No key, and nothing paid here.
- **Who speaks the narration**, in the avatar's voice:
  - **ElevenLabs** (`elevenlabs`): an API key, on a plan that can clone a voice. Nothing to set up.
  - **Their own voice API on Modal** (`modal`): the open models that come with the plugin (OmniVoice), deployed
    once to their Modal account, which pays for the GPU by the second while it speaks. The first scene after a
    quiet spell waits a minute or two for the model to load.

Keep the answers with `makable-shorts me --filmer omni|heygen|import --narrator elevenlabs|modal`. For HeyGen, pick
its voice too: run `makable-shorts voices --gender male` (or `female`, for the person in the photo), offer two or
three with their preview links, and keep the one they pick with `me --filmer-voice VOICE_ID`. With `--yes`, if
either isn't chosen, stop and say so.

**Their keys.** If `me` says a key their choices need isn't set, set it up with them now, then run `me` again and go
on. With `--yes`, stop and say which.
- Run `makable-shorts keys --open`. It adds a line for each missing key to the `.env` that `me` names, with where to
  get it in a comment above, and opens the file in their text editor. Tell them which keys to paste in and where to
  get each, to save the file, and to tell you when they have.
- **Omni** needs the ID of their Google Cloud project in `GOOGLE_CLOUD_PROJECT`: a project with billing, and the
  Vertex AI API on (`gcloud services enable aiplatform.googleapis.com --project PROJECT_ID`). And it needs Google
  Cloud's sign-in on this machine: if `me` says `google  not signed in`, have them type
  `! gcloud auth application-default login` in the prompt, which opens their browser. If they haven't gcloud, it's
  at https://cloud.google.com/sdk/docs/install.
- **Their own voice API** comes from `makable-shorts deploy-voice`, not from them. Run it in the background: the
  first deploy builds the models' images, which takes several minutes. If Modal has no sign-in here, it opens their
  browser to sign in or make an account, and waits: tell them so. It deploys the voice API that comes with the
  plugin to their account, and writes its address and key into the `.env` itself.

**The product.** Every video is about one product, and its notes say how to record it and how to talk about it
([references/product.md](references/product.md)). Read them before anything else.
- If the request names a product, it's that one. If not, and the project has notes of its own, it's the
  project's product. Otherwise, if there are notes on only one, it's that one.
- If there are notes on several and none of that settles it, ask (interactive), or stop and say so (`--yes`).
- If there are none for it, set them up with the user as product.md says (interactive), or stop (`--yes`).

Two things every video needs, and you never go on without:

- **The product's address,** the notes' `url`, where recordings start. If the notes have none, ask for it
  (interactive), or stop and say so (`--yes`). Never guess one.
- **A photo of the user,** for whoever films the avatar. If `me` shows no `face`, ask for one: their face and
  shoulders, looking at the camera, in good light. One with the background removed is best, since Omni films the
  setting the script describes. Keep it with `makable-shorts me --face PATH`. Ask about music at the same time,
  once: a file of their own (`me --music PATH`), or none. With `--yes` and no face, stop. Only clips the user
  films elsewhere and brings in (filmer `import`) need no photo.

## 2. What the video is about

The request gives commits, a prompt, or both:

- **Commits:** a SHA, `repo@sha`, a GitHub commit URL or a range `a..b`, in the product's code (the notes'
  `code`). In the repo you're in (`code: .`), read each with `git show <sha>`, or a range with
  `git log -p <a>..<b>`: commits that aren't pushed yet too. On GitHub, use
  `gh api repos/<owner>/<repo>/commits/<sha>` (its message, files and patch), or
  `gh api repos/<owner>/<repo>/compare/<a>...<b>`. In a folder elsewhere on this machine, `git -C <folder> show <sha>`.
- **A prompt:** text describing the functionality to show, such as "show how to share a note with a teammate".
  Find it in the product's code: in the repo you're in, search it (Grep, Glob, Read); on GitHub,
  `gh search code --repo <owner>/<repo> "<words>"`, or `git clone --depth 1 https://github.com/<owner>/<repo>`
  into a temporary folder and search it. With no code, find it on the product itself, with `drive start` and
  `look`.
- **Both:** the prompt says what to focus on among the commits' changes.
- **Neither:** ask for commits or a description (interactive), or stop and say what's missing (`--yes`).

**Learn the flow from the code** before you record, whenever you have it: the route of the page it's on and the
path a user takes to it, the labels of the buttons and boxes exactly as the code writes them (in the run's
language, if the app is translated), what shows while something slow runs and once it's done (for `wait-for`),
and what it depends on (a plan, a feature flag, something that must exist first). With it, the recording works
the first time, and the script says what the product really does.

Pick the run's folder, `<runs>/<yyyy-mm-dd>-<slug>`, in the `runs` folder `me` printed, where the slug is a few
words of what the video is about: it's `RUN` in the commands below.
Write `changes.md` in it, with:
- what a user can now do, in a sentence;
- where it is in the UI, with the labels exactly as shown;
- the steps that show it;
- what the viewer should see at the end.

If nothing changed that a user can see (a refactor, a backend fix with no visible effect), say so and stop.
If a prompt is too vague to pick one flow, ask (interactive), or pick the most direct one (`--yes`).

## 3. The run

```sh
makable-shorts new <runs>/<yyyy-mm-dd>-<slug> [--tone hype] [--language hi] [--pronounce WORD=SAID ...]
```

A new run takes the user's photo, music and voice from `me`, and who films them and who speaks. The defaults are
this flow's: an outro, and narration in the avatar's voice.

- `--tone` and `--language` from the request (friendly and English by default).
- `--pronounce` for each of the notes' `pronounce` words in the run's language.
- **Another filmer, for this video only,** if the user asks for one: `--intro heygen --outro heygen
  --filmer-voice VOICE_ID` (a voice from `makable-shorts voices`), `--intro omni --outro omni`, or `--intro import
  --outro import` for clips they film elsewhere. Their keys are step 1's.

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

Then ask: film it, change something, or stop. Filming costs about two dollars with Omni (the intro and the outro,
about a dollar each), or what HeyGen takes from their balance. With their own clips (`import`), ask them instead to
film the intro line and the outro line (in the setting the script gives) and to give you the files or links.

## 8. Make it

```sh
makable-shorts run RUN --paid
```

This takes a few minutes, so run it in the background. It does everything that's due, in order:
1. films the intro and the outro (Omni or HeyGen, as `run.json` says). The user's own clips come in first instead:
   `makable-shorts import RUN intro FILE_OR_LINK` (and `outro`);
2. takes the avatar's voice from the intro;
3. has ElevenLabs, or the user's voice API, speak each scene in it (`run.json`'s `narrator`);
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
  step 8 again to film it again (about a dollar);
- notes you wrote or changed in the repo (`.makable-shorts/products/`): they're the user's to commit. In GitHub
  Actions, they're uploaded with the video.

In `--yes` mode, also say what you decided on your own.
