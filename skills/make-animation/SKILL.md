---
name: make-animation
description: Makes an animated explainer Short (3D-style animation, a fact or a "what if" question) for YouTube Shorts and Instagram Reels. It designs consistent characters, draws each shot, animates it with Omni and narrates it in your cloned voice. Use when the user asks for an animated video, an explainer, a "what happens if" Short, or a video that isn't about their product.
argument-hint: "[topic or question] [--language hi] [--tone hype] [--yes] [--paid]"
allowed-tools: Read, Write, Edit, Glob, Bash(makable-shorts *), Bash(ffprobe *), WebSearch
---

# Making an animated Short

The request: $ARGUMENTS

This is the other kind of video the plugin makes. `/make-video` records the user's product. This one draws a short
animated explainer from a topic: a fact, a comparison, a "what happens if". Each shot is a **still image** first, and
a video model only animates a still once the user has approved it. So the characters look the same in every shot,
and the cheap images are checked before the paid clips are made.

```
script ──► cast ──► stills ──► (approve) ──► speak ──► animate ──► (choose) ──► assemble
          cents     cents                   voice      $0.07/s
```

If the request could be either kind ("make me a video"), ask once which: a demo of their product (`/make-video`), or
an animated Short about a topic (this one). With `--yes`, a request that names no product is this one.

The pipeline is the `makable-shorts` command, the same one `/make-video` uses. Its stages share a **run folder**
(`.makable-shorts/runs/<name>/`), and `${CLAUDE_PLUGIN_ROOT}/shorts/run.py` and
`${CLAUDE_PLUGIN_ROOT}/shorts/stages/animate.py` describe every file in it. Your part is what needs judgment: the
story, the storyboard, looking at the pictures, and the choices. The first command sets up its Python environments,
which takes a few minutes: give it a Bash timeout of 600000 ms. Never print or read a key, and never ask for one in
the chat.

**Interactive or not.** With `--yes`, the approvals at steps 5 and 6 are yours to make, and you say what you decided
in the report. Animating (step 8) costs real money, so it happens only after the user's yes in the chat, or with
`--paid` given too.

## 1. Choices, once

Run `makable-shorts me`. If it shows no `images` or `animator` line, ask once (interactive), in one message:

- **What draws the characters and stills**, in their Google Cloud project, the one Omni uses:
  - Nano Banana 2.1 (`gemini-nano-banana-2.1`): about 3 ¢ an image. The default.
  - Nano Banana Pro (`gemini-3-pro-image`): about 13 ¢ an image, with better faces.
- **Who animates the stills:**
  - Gemini Omni (`omni`): $0.07 a second of video, about $2 for a 30-second Short.
  - Themselves (`import`): they animate each still on the Gemini website, for free, and give you the clips.

Keep them with `makable-shorts me --image-model MODEL --animator omni|import`. The narrator is the same choice as
for `/make-video` (`me --narrator`), and so is their voice sample (`me --voice`). An animated Short has no avatar,
so an API narrates in their own voice, from the sample. If they have neither, Kokoro (`--narrator kokoro`) speaks
for free, or `none` gives captions only. With `--yes`, if anything isn't chosen, stop and say so.

The image model and Omni need `GOOGLE_CLOUD_PROJECT` and Google Cloud's sign-in, as `/make-video`'s step 1 sets up
(`makable-shorts keys --open`, and `! gcloud auth application-default login`). `keys` needs a narrator chosen first.

## 2. The topic

Take it from the request. If the user asks for ideas, suggest three in the channel's style, and let them pick.

Check the key fact with a web search before writing a word, and keep the source: it goes in the description.
[references/story.md](references/story.md) says how to turn a fact into a 25 to 35 second story, and what to leave
out (myths that everyone repeats, numbers no one can source).

## 3. The run

```
makable-shorts new .makable-shorts/runs/<date>-<topic> --kind animated --language hi
```

Name the run by the date and the topic (`2026-11-24-coconut-skull`). `--kind animated` makes it open on its first
shot, with no intro or outro, and narrate in the user's voice.

## 4. The storyboard

Write `script.json` as [references/script.md](references/script.md) says, with the shots
[references/shots.md](references/shots.md) describes:

- the `style`, one sentence every image starts with;
- the `characters`, each with a `look`;
- 4 to 6 scenes, each with its narration (`text`, with emotion tags if the narrator performs them), its footage name
  (`shot-01`, …), and its `shot`: the `still`, the `motion`, who's in it, and whether it `follows` the shot before;
- three versions of the opening line in `hooks` (`H1`, `H2`, `H3`), and the one used in `hook`.

Check it before bringing it in, and fix every error and every warning you can:

```
makable-shorts check-script RUN drafts/script.json
makable-shorts import RUN script drafts/script.json
```

Show the user the storyboard: each shot's narration, still and motion, as a short list (interactive). Go on once
they're happy with it.

## 5. The characters

```
makable-shorts cast RUN
```

It draws each character's sheet (front, three-quarter and side views) in `cast_takes` takes (3, unless `new
--cast-takes` says otherwise): `cast/<name>-take-1.png`, …, using take 1 until another is chosen. Look at every
take yourself (Read the images). A good sheet matches the look, has the same face, body and clothes in all three
views, and has nothing else in it ([references/characters.md](references/characters.md)).

Show the user the best one or two and ask which (interactive), then `makable-shorts choose RUN <name> <take>`. A
character they'll use again (a channel mascot) can be kept for every Short: `makable-shorts me --character
<name>=RUN/cast/<name>.png`. Then `cast` uses it as it is. If they say "use my mascot", it's that one.

## 6. The stills

```
makable-shorts stills RUN
```

Each still is drawn with the sheets of its characters, the first still (for the style), and the shot before when
the shot `follows` it. It writes `stills/<shot>.png`, and all of them side by side in `stills/sheet.png`.

**Look at the sheet before the user does.** Redraw a still where:
- a character drifted: another face, clothes or colours, or one too many people;
- the style drifted: another background or light than the other stills;
- there's text, a logo or a watermark in it;
- it doesn't show what the narration says at that moment.

To redraw, change that shot's `still` in the script (be more exact: "the same cyan gradient background as the
other shots", "he wears grey shorts"), bring it in again, and run `stills` again. Only stills whose prompt or
references changed are drawn again. To redraw one as it is, delete its file first. Then show the user
`stills/sheet.png`, and go on once they approve it (interactive).

## 7. The voice

```
makable-shorts speak RUN
```

The narration is spoken before animating, so each clip is asked for only as long as its shot needs (4, 6 or 8
seconds), and paid for by the second.

## 8. Animate

**With Omni:** run `makable-shorts status RUN`, and tell the user what animating costs: each shot's clip length
from the narration (4, 6 or 8 s), the seconds in all, and × $0.07. Wait for their yes (interactive), or go on only
with `--paid` (with `--yes`). Then:

```
makable-shorts animate RUN
```

It writes each clip to `footage/<shot>.mp4`, and to `animations/omni-1.2/` as the take it is. To compare versions
or takes on the first few videos, `makable-shorts animate RUN --with omni-1.1,omni-1.2` (or `animate RUN --with omni-1.2 --takes 2`, two takes of one) makes more,
at the same price each: ask before that too.

**Animating it themselves (`import`):** run `makable-shorts prompts RUN`. It lists each still, its length and its
motion prompt. Give them that list, to paste each into the Gemini website with its still. Then bring each clip in:
`makable-shorts import RUN footage --name shot-01 CLIP` (a file, or a link to one).

## 9. Choose, and make the video

With more than one take, `makable-shorts compare RUN` puts them side by side in `animations/compare.mp4`, a shot
after another. Look at it yourself first: `makable-shorts frames RUN shot-01` shows a shot's clip as frames with
their times (the one in `footage/`, so after choosing too). Show it to the user, and choose per shot (`makable-shorts choose RUN shot-02 omni-1.1`) or for all
(`choose RUN all omni-1.2`).

Then `makable-shorts run RUN`: it makes `final.mp4` and `metadata.json`.

## 10. Report

- the video (`final.mp4`), and how long it is;
- what it cost: the images (count × the image model's price), and the seconds animated × $0.07;
- the title and description (with the fact's source);
- the hook used (`hook`) and the others (`hooks`), so they can upload another version and `/review-video` can
  compare them;
- anything you decided for them (`--yes`), and anything that didn't come out well.
