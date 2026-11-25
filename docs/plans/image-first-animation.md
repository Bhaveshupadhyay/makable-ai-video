# Plan: image-first animated Shorts (consistent characters, any video model)

**Goal.** For animated fact Shorts like the coconut one:
1. Design the characters once.
2. Draw every shot as a still image with those same characters.
3. Then let a video model animate each still.

It's a new skill, `/make-animation`, in the same plugin as `/make-video` (Phase 6). You see and approve the cheap images before paying for the expensive video. Because every model can start from the same still, a new model can be added later and compared side by side.

**Models in this plan:**
- **Gemini Omni** on Google Cloud (Agent Platform), the model you already use.
- **Your own clips** from the Gemini website, brought in with `import`, for free.
- **Not now:**
  - Veo: Omni is the newer model, and Veo on Google Cloud isn't confirmed.
  - fal.ai (Kling, Seedance, Hailuo, …): no key yet.

  The design leaves a slot for both, so either is one new file later.

## Why this works (and what it fixes)

| Today | Image-first |
|---|---|
| Omni invents the character in every clip, so it drifts (face, clothes, proportions) | The character is drawn once and passed in as a reference to every still |
| One way to make a clip | The still is the shared input, so models are swappable and comparable (Omni today, others later) |
| You only see the result after paying $0.07 a second (about $0.56 for an 8 s clip) | Stills cost about 3–13 ¢ each. You fix the look before animating |
| A failed clip means re-rolling blind | Re-roll the still (cheap) or only the motion (same still, new clip) |

**What's needed from the models is available today** (Google's docs, read 23 Nov 2026):

- **Nano Banana 2.1** (`gemini-nano-banana-2.1`):
  - takes up to 4 images of characters "to maintain character consistency", plus objects, with 14 references in all
  - about $0.034 per 1K image
- **Nano Banana Pro** (`gemini-3-pro-image`):
  - takes up to 5 character images and 3 style-reference images
  - about $0.134 per image
- **Gemini Omni:**
  - already takes an image and a prompt and returns 9:16 video (`shorts/intro.py`)
  - $0.07 per second of video
  - the docs name a newer `gemini-omni-1.2-flash`; the code uses 1.1

## How it fits the pipeline you have

Nothing downstream changes. Today a scene is said over a recording (`footage/<name>.mp4`), and `assemble` cuts, re-times and captions it. An animated shot simply becomes footage: `footage/shot-01.mp4`, `footage/shot-02.mp4`… The OmniVoice narration with its tags, the captions, the speed-fitting and the insights all work unchanged.

New stages go **before** `assemble`, following the pattern that `film-intro` uses for "paid, never runs on its own":

```
script ──► cast ──► stills ──► (you approve) ──► speak ──► animate ──► (you choose) ──► assemble
          cheap      cheap                        voice      paid
```

Narration is spoken **before** animating, so each shot's clip length can be chosen to fit what's said over it. Because Omni charges by the second, this also saves money: a 5.4 s line gets a 6 s clip, not an 8 s one.

## The plan

### Phase 0: a test with one shot (half a day, no pipeline code)

1. Draw the coconut man's character sheet and the hook still (shot 1) with Nano Banana 2.1, by hand in a script.
2. Animate that one still with Omni 1.1 and with Omni 1.2.
3. Send you the clips side by side, with what each cost and how long it took.

This answers the questions that shape everything else before any of it is built:
- Does Omni keep the still's exact look, or treat it as loose inspiration?
- Does 1.2 do it better than 1.1?
- Can Omni be given an end frame as well? If it can't, `end_still` waits for a model that can.

Optionally, you animate the same still on the Gemini website (free) and I add your clip to the comparison.

### Phase 1: the storyboard in the script (`shorts/script.py`)

Claude already writes `script.json`. For an animated Short it also writes:

```json
"style": "Stylized 3D medical-explainer CGI, glossy, soft studio light, cyan-to-white gradient background",
"characters": [
  {"name": "man", "look": "bald cartoon man, round face, plain blue t-shirt, grey shorts, barefoot"}
],
"scenes": [
  {
    "text": "[surprise-wa] अगर पच्चीस मीटर ऊँचे पेड़ से…",
    "footage": "shot-01",
    "shot": {
      "still": "The man sits at the foot of a tall coconut palm, eyes closed, smiling; low angle",
      "motion": "Camera tilts up the trunk; a coconut snaps loose and falls toward him; freeze just above his head",
      "characters": ["man"],
      "end_still": null
    }
  }
]
```

- `style` and `characters` are written once. Every image prompt starts with them, so the look can't wander.
- `still` is what the image shows. `motion` is what the video model is told to do with it.
- `end_still` is optional, and is used only by models that take a last frame (Phase 0 tells us whether Omni does). A second still gives full control of where the shot ends, for example the crack on the skull.
- **Check rules:**
  - a shot names only characters that exist
  - no text, logos or watermarks in prompts (the "no logos" rule from before)
  - each shot has 4–8 s of narration, which fits the clip lengths Omni makes

### Phase 2: `cast`, the characters (new stage, cheap)

- For each character, Nano Banana draws a **character sheet**: front, three-quarter and side views on a plain background, in the `style`.
  - Saved to `cast/<name>.png`.
  - Several takes are made (`--takes 3`), and you choose one.
- The chosen sheet is **locked**. It is the reference for every still from then on, in this video and later ones. A recurring mascot lives in your `me/` folder like your photo and voice (`shorts.home`), so every Short has the same character.

### Phase 3: `stills`, one image per shot (new stage, cheap)

- **Each still** is drawn from:
  - the shot's `still` text
  - the style line
  - the locked sheets of the characters in it
  - the first approved still, as a style reference

  It's saved to `stills/shot-01.png`, plus `shot-01-end.png` if the shot has an end still.
- **Continuity:** when shots follow on in the same place, the previous still also goes in as a reference, so the room, light and props match.
- **A consistency check before any money is spent:** a contact sheet `stills/sheet.png` (all stills in a grid) is made. Claude looks at it and redraws the ones where the character drifted. Then you approve the sheet.
- Like every stage, only a still whose prompt or references changed is redrawn (the existing fingerprint system).

### Phase 4: `animate` (new stage, paid)

- **`shorts/animators.py`:** an `Animator` with the same shape as today's `Filmer`. It takes a still, an optional end still, the motion text and a length, and returns a 9:16 MP4. It starts with:

  | Animator | What it uses | Key |
  |---|---|---|
  | `omni` | image + motion prompt on Agent Platform; the model version is a setting (1.1 / 1.2) | already set up |
  | `import` | you animate on the Gemini website for free and bring the clip in with `python -m shorts import RUN footage --name shot-01 clip.mp4` | none |

  Adding fal.ai later is one more entry here plus `FAL_KEY`. Nothing else changes.

- **Length:** each shot asks for the shortest clip that covers its narration plus a pause, since Omni charges per second.
- **Paid, so explicit:** `python -m shorts animate RUN`. Before spending, it prints the estimate (seconds × $0.07), as `film-intro` does. `run --paid` includes it.
- **Model audio is dropped.** The narration plus optional music is the only sound. Sound effects are a later option.

### Phase 5: compare and choose

- `python -m shorts animate RUN --with omni-1.1,omni-1.2` (or two takes of the same model) animates each shot into `animations/<name>/shot-01.mp4`.
- `compare` puts them side by side, one row per shot and one column per take or model, in `animations/compare.mp4`.
- You choose per shot (`python -m shorts choose RUN shot-01 omni-1.2`) or for all of them. The chosen clip is copied to `footage/shot-01.mp4`, and `assemble` takes it from there.
- Each pick and its model are noted in the run. When more models are added, the insights command can show which model's videos held viewers better.

### Phase 6: a new skill, `/make-animation`

Animated Shorts get **their own skill** in the same plugin, next to `/make-video`. The two share the pipeline but not the instructions:

| | `/make-video` (unchanged) | `/make-animation` (new) |
|---|---|---|
| Starts from | a product's repo, commits, notes | a topic or a question ("can a coconut break a skull?") |
| Claude does | drives Chrome and records the product | researches the fact, writes the storyboard, designs characters, draws stills |
| Needs | the product's address, sign-in, product notes | an image model and Omni (both on your Google Cloud) |
| Footage | `record` | `cast` → `stills` → `animate` |

Each skill's description tells Claude Code which one fits a request, so:
- "make a demo of my login page" → `/make-video`
- "make an animated Short about coconuts" → `/make-animation`

Only a request that could be either ("make me a video") gets one question.

#### 6.1 The pipeline learns two kinds: run.json `kind`

- `kind: "demo"` (the default, so existing runs don't change) or `"animated"`.
- `python -m shorts new RUN --kind animated` sets it.
- The pipeline then knows which stages make the footage:
  - for a demo: `record` / `drive`
  - for animated: `cast`, `stills`, `animate`

  `speak`, `assemble`, captions, music, `insights` and `/review-video` are the same for both.
- `check_script` applies the storyboard rules (Phase 1) only to `animated` runs, and the recording rules only to `demo` runs.

#### 6.2 The skill's files

```
skills/make-animation/
  SKILL.md                 the steps (below), in the same shape as make-video's
  references/
    story.md               turning a fact into a 25–35 s Short: hook question → fact with a number →
                           comparison → twist → sign-off; checking facts, and leaving out myths
                           (like the "150 coconut deaths a year" one)
    shots.md               writing `style`, `characters`, `still` and `motion`: one action per shot,
                           camera move named, no text/logos/brands, when an `end_still` helps
    characters.md          character sheets: what makes one reusable; mascots kept in me/
    script.md              the script.json format for animated runs (tags, Hindi, word counts per shot)
```

**`SKILL.md` frontmatter:**
- `name: make-animation`
- `description`: "Makes an animated explainer Short (3D-style animation, a fact or a 'what if' question) for YouTube Shorts and Instagram Reels: designs consistent characters, draws each shot, animates it with Omni and narrates it in your cloned voice. Use when the user asks for an animated video, an explainer, a 'what happens if' Short, or a video that isn't about their product."
- `argument-hint: "[topic or question] [--language hi] [--tone hype] [--yes]"`
- `allowed-tools`: the same `makable-shorts *` command, plus WebSearch, to check facts.

#### 6.3 The steps in `SKILL.md`

1. **Choices, once.** On first use, ask and save in `choices.json` (`me --image-model --animator`):
   - **Image model:** Nano Banana 2.1 (cheap) or Pro (better faces)
   - **Animator:** `omni` (paid) or `import` (you animate on the Gemini website for free)

   The narrator choice is shared with `/make-video`, and so is your voice sample in `me/`.
2. **The topic.** From the request, or Claude suggests 3 topics in the channel's style if asked. It checks the key fact with a web search and notes the source in the run.
3. **The run.** `makable-shorts new RUN --kind animated --language hi`.
4. **The storyboard.**
   - Claude writes script.json: style, characters, 4–6 shots, the narration with emotion tags.
   - `check_script` must pass.
   - Claude also writes 3 versions of the opening line, for hook testing.
5. **Characters.** Claude runs `cast`, looks at the takes, and shows you the best one or two. **You approve** (or say "use my mascot").
6. **Stills.** Claude runs `stills`, looks at the contact sheet, and redraws any still where the character drifted. **You approve the sheet.**
7. **Voice.** `speak`. The clip lengths now come from the narration.
8. **Animate.**
   - Claude shows the cost (seconds × $0.07) and **waits for your yes** before `animate`, or before `--paid` with `--yes`.
   - With `import`, it lists each still and its motion prompt for you to paste into the Gemini website, then brings the clips in.
9. **Choose and make.** If there are several takes, Claude makes `compare`, you choose, and `assemble` makes the video.
10. **Report.** Claude reports:
    - the video
    - the cost
    - the title and description
    - the hook variant used, tagged for `/review-video`

`--yes` skips the approvals at steps 5 and 6, but never the spending at step 8 unless `--paid` is also given.

#### 6.4 The plugin around it

- **`.claude-plugin/plugin.json`:** the description becomes "product demos and animated explainer Shorts". Keywords gain `animation`, `explainer` and `character-consistency`. The version goes from 0.4.0 to 0.5.0.
- **README:** a section for the second kind of video, with its keys (the same Google Cloud project as Omni; nothing new to sign up for) and its cost.
- **`/review-video`:** reads `kind` and the hook variant from the run, so insights can compare demos with animations, and one hook with another.

#### 6.5 Checking the skill itself

- **Which skill it picks:** a small set of requests, run with `claude plugin eval`, checks that animation requests go to `/make-animation`, product requests go to `/make-video`, and "make me a video" asks a question.
- **End to end:** the coconut Short made start to finish through `/make-animation`, as the first real run.

### Tests

New stages and animators get tests the way filmers have them. The models are faked (no network), and each test checks:
- the prompt and references sent
- that only changed stills are redrawn
- that cost estimates are printed and nothing paid runs without `--paid` or the stage's own command
- that a chosen clip lands in `footage/` and `assemble` uses it
- the script rules: unknown character, logo words, shot length

## Costs for a 30-second, 5-shot Short (rough)

| Step | Cost |
|---|---|
| Character sheet, 3 takes | ~$0.10 (Nano Banana 2.1) – $0.40 (Pro) |
| 5 stills, plus a few redraws | ~$0.25 – $1 |
| Animation with Omni, 5 × 6 s = 30 s at $0.07/s | ~$2.10 |
| Comparing two Omni takes or versions | ~$4.20 for the animation, so compare on the first few videos, then keep the winner |
| **Total, one take** | **about $2.50 – $3.50** |
| Free route | stills here, animation on the Gemini website, then `import` |

## Order of work and decisions

1. **Phase 0 first.** Its results decide how much the still controls Omni, and whether `end_still` is possible.
2. **Then the phases in order (1 → 6).** The pipeline stages come before the skill, because the skill only calls them. Each phase is tested before the next starts.
3. **Branch.** The working tree still has uncommitted `video-insights` work. I'd commit it, then start `animated-shorts` from an up-to-date `main`.
4. **Licences.** Check that Omni's terms allow commercial use of its output, along with OmniVoice's CC-BY-NC.

## Phase 0 results (24 Nov 2026)

One shot (the coconut hook), drawn with Nano Banana 2.1 from a character sheet, then animated for 6 s by each Omni.

- **The still controls Omni closely.** Both versions start on the exact still, and keep the man's face, body and
  clothes to the end. The character sheet carried into the still unchanged too.
- **1.1 vs 1.2:** close. 1.1 kept the coconuts green, as drawn; 1.2 turned the falling one brown and added a faint
  halo around it. Both freeze it above his head as he looks up in shock. 1.2 (`gemini-omni-1.2-flash`, not a
  preview) is the default, and `animate --with omni-1.1,omni-1.2` keeps comparing.
- **Length is a setting:** `response_format.duration` ("6s") gave exactly 6.04 s, so a clip is asked for only as
  long as its shot needs ($0.42 for 6 s). About 45 s to render each.
- **No end frame:** the Interactions API's image input has no first- or last-frame role, so `end_still` waits for a
  model that takes one (`Animator.end_frame` is False for Omni).
- **The style drifts without being told:** the still went to an outdoor sky instead of the cyan studio background.
  The skill's shots.md says to name outdoor shots in the style, and to redraw stills whose style drifted.
- **Google's shared quota** answered 429 after a few images in a row: image and Omni calls now wait and ask again.
- Cost: 2 images ($0.07) + 12 s of Omni ($0.84).
