# Writing the script

The script is `script.json`: what the avatar says at the start and the end (or the title card and the end card
show, in a video without one), and what the narrator says over each stretch of the screen recording (or the
captions show, in a video without a voice). You write it from three things:

- **The steps:** `footage/<name>.steps.json` in the run, what browser-use did and when (seconds into the video).
- **The frames:** `makable-shorts frames RUN <name>` makes contact sheets of what's on screen when, in
  `RUN/frames/`. Look at them. For text too small to read, use `--at <seconds> ... --width 720`.
- **What it's about:** `RUN/changes.md`, if there is one, or what the user asked for. The run's
  `run.json` gives the `language` and the `tone`, and the product's notes its name, what it is and its sign-off.

**Trust the frames over the steps.** The steps say what the program did ("Waited 30 seconds", "Typed …"),
and its final report says what it saw. Neither tells you what's on screen at a given second: a preview
may still be loading, or show only the top of a page. Say only what's visible during the scene's stretch.

## The video's three parts

1. **Intro**, about 10 s. The avatar (Gemini Omni, HeyGen, or a clip the user films) talks to the camera.
   - `intro_line`: one hook of 14 to 20 words. Make people want to see the payoff, the thing the recording
     ends on. Make it concrete ("a bakery website from one sentence") rather than generic ("the future of
     web design").
   - `intro_setting`: the shot in one sentence: place, light, framing. Don't describe the person (Omni
     films them from their photo). Example: "A bright home office with a laptop on the desk, soft window
     light, framed from the chest up."
2. **The narrated recording**: 3 to 8 `scenes`.
   - **Length:** about 50 s of narration in all, or less if the recording is shorter.
   - **Each scene:** one or two short sentences, said over one stretch of one recording, from `start` to
     `end` in seconds.
   - **How it's timed:** the narrator says about 2.5 words a second, and the stretch is sped up or slowed
     down to last as long as its narration plus a 0.35 s pause. Aim for 0.8× to 1.5×: a stretch of
     `words / 2.5 + 0.35` seconds plays at 1×.
3. **Outro.** The avatar again, in the same shot.
   - `outro_line`: 8 to 16 words that ask people to try the product, in the words of the notes' sign-off.
   - `outro_setting`: leave it empty, so the outro is filmed in the intro's setting.

Also write a YouTube `title` (under 70 characters) and a `description` of 2 or 3 sentences.

## A product demo, with no avatar

When `run.json`'s `intro` and `outro` are `card`, there's no avatar. The video opens on a **title card** and ends on
an **end card**: a blurred still of the recording, where the first scene starts and where the last one ends. While
the narrator says the line, the captions show it as it's said; with no voice, the card shows it in big letters.

- `intro_line`: the hook, **12 words at most**, read at a glance: "A whole clothing store website from one sentence."
  The narrator says it over the card, and the card stays up while it does. With no voice, the card stays up for as
  long as it takes to read.
- `outro_line`: the sign-off, 12 words at most: "Try Acme Notes free at acme.com."
- `intro_setting` and `outro_setting`: `""`, since nothing is filmed.

Write the scenes as above. The narrator is Kokoro, or the user's own voice from a sample (`narrator`): either way,
not an avatar, so don't say "I" as if someone were on camera unless it's the user's own voice.

## A silent demo, with no voice

When `run.json`'s `narrator` is `none`, nothing is heard but music. The cards are as above, and each scene's `text`
is a caption, shown whole for as long as its stretch is on screen:

- **Write it to be read, not said:** a short phrase, 3 to 8 words, that says what's happening or why it matters:
  "Describe your store in one line", "It writes every file to your GitHub". No "I", no "now", no "just".
- **The stretch plays at its own speed,** so pick it for what it shows, not for how long the text is. It's slowed
  down only if its words take longer to read (2.5 words a second): `check-script` shows each one's speed.
- **About 50 s of scenes** in all, as for a narrated video.

## Reading the steps

Each step is `{goal, actions, did, url, start, end, clicks}`. Its times are for the video you're
narrating (the `-tight` one).

- `goal`: what the program set out to do.
- `did`: what each action did. The last step's action is `done`, and its `did` is the program's
  final report: whether everything worked, how long things took (by the product's own timer, if it shows
  one), and what the finished page has.
- `clicks`: `[seconds, x, y]` for each click. The video zooms in on each click and out again.
- A step that only `wait`s keeps just the moments when the page changed, so a 30-second wait may last 2 s
  on screen. Typing plays 4× as fast.

## Picking the stretches

- **Tell the story in order.** Stretches never overlap. They usually go forward through the recording,
  but you can skip parts.
- **Leave out what doesn't move the story along:** retries, error messages, waits where nothing new
  happens. Skip past them by starting the next scene after them. Keep one only if it shows something
  worth saying. For example, the product noticing that a name is already taken is worth a few words.
  A "couldn't reach the server" error never is.
- **Start each stretch where what it describes starts.** A click's stretch starts just before the click
  (`clicks` gives the time).
- **End on the payoff.** The last scene shows the result (the finished preview, the change made), held
  long enough to see.

## Writing what's said

- **Narrate as if you were showing a friend.** Never mention the program, its steps, waits, element
  numbers or retries.
- **Name what's on screen:** button labels, the site's name, the headline that appears. Prefer
  "the Opening Hours button turns into Order for pickup" to "the site updates".
- **Claim only what the frames, the steps and the report back up.** Use the report's numbers (the build
  took about 36 seconds by the product's own timer). Don't say "instantly" for something that took 30 seconds,
  or "six pastries with prices" if the menu never comes into view.
- **Use plain words.** Don't say "seamless", "revolutionary", "game-changer" or "in seconds" (unless it was).
  Don't open with "Welcome".
- **No hashtags or emojis**, since the narrator can't say them. Write "and" for "&" in spoken text
  ("Crumb and Co"): the captions show what's written.
- **Write the product's name as its notes spell it.** The narrator is told how to say it (run.json's
  `pronounce`).

### Tones (`tone` in run.json)

- `friendly`: like a person talking: short sentences, plain words.
- `hype`: like a creator excitedly showing a friend something they just found. Use short, punchy
  sentences, an exclamation mark where something good happens, and words that pull the viewer in (look,
  just, wait). Before the best part, add a turn like "wait, that's not even the best part".

### Languages (`language` in run.json)

- `en`: English.
- `hi`: everyday spoken Hindi in Devanagari, the way a friendly Indian tech YouTuber talks. The English
  words Indians say anyway stay English but are written in Devanagari (वेबसाइट, प्रीव्यू). Keep the
  product's name in Latin letters. Set `"language": "hi"` in script.json.

Write everything that's said, the title and the description in the run's language.

### Tags: a laugh, a sigh, a "wow"

With OmniVoice as the narrator (`narrator_model` "omnivoice", the voice API's own), a tag in square brackets
says how a line is said, not only what's said:

```json
{"text": "[laughter] सोचो, एक छोटा सा नारियल और आपकी खोपड़ी!", "footage": "demo", "start": 0, "end": 4}
```

| Tag | What you hear |
|---|---|
| `[laughter]` | a short laugh |
| `[sigh]` | a breath out, before the words |
| `[surprise-wa]` | a surprised "वा!" |

The captions show only the words, and the tags don't count toward the scene's length.

- **Where they help:** a laugh after the punchline, a sigh before the "but…", surprise on the big number.
  A tag works best at the start of a line, or of a sentence in it.
- **At most 2 or 3 a video.** Used sparingly, a tag lands; on every line, it sounds put on.
- **Never in a filmed intro or outro line** (Omni, HeyGen or your own clip): the avatar would say them out
  loud. A title card's or an end card's line is spoken by the narrator, so a tag works there.
- **Never a line of only tags:** the captions need its words.
- **Only with OmniVoice.** Chatterbox, ElevenLabs and Kokoro are given the line without its tags, so none of
  them reads one out, but you won't hear them either.
- Only the tags above: `check-script` says any other is an error, since OmniVoice would read it out.

#### A tag OmniVoice doesn't perform

The user may write a tag that isn't above, in a script they give you or in what they ask for: `[whisper]`,
`[excited]`, `[giggle]`, or one spelled wrong, like `[lugh]`. Don't stop at the error. Rewrite the script yourself,
going by what the tag means, not how it's spelled:

- **Swap it for the tag closest in meaning**, if one is close: `[laugh]`, `[lugh]`, `[giggle]` → `[laughter]`;
  `[wow]`, `[excited]`, `[amazed]` → `[surprise-wa]`; `[sighs]`, `[tired]` → `[sigh]`.
- **Remove it** if none is: `[whisper]`, `[angry]`, `[sad]`, `[shout]`. A tag is a single sound at its spot, a
  laugh or a breath, and none of them changes how the words after it are said, so a whole whispered or excited
  line can't be done with one. Don't swap in a tag that means something else (a `[sigh]` for a whisper).
- **Write the words as they were.** Only the tags change. If a removed tag left the line's feeling unsaid and the
  user wants it, say so in the words instead ("और अब, धीरे से…").
- **Tell the user what you changed**, one line a tag, before you bring the script in:
  > Scene 1: [lugh] is now [laughter]. Scene 2: removed [whisper], OmniVoice can't whisper. Scene 3: [excited] is now
  > [surprise-wa], a surprised "वा!".

Then run `check-script` again. With a narrator other than OmniVoice, every tag is left out anyway (`check-script`
warns): tell the user that once, rather than rewriting each one.

## The format

For a website builder, say:

```json
{
  "intro_line": "A whole bakery website from one sentence, and it lands on your own GitHub. Watch this.",
  "intro_setting": "A bright home office with a laptop on the desk, soft window light, framed from the chest up.",
  "scenes": [
    {"text": "To start a new site, just describe it in one sentence.", "footage": "demo", "start": 0.6, "end": 5.4},
    {"text": "…", "footage": "demo", "start": 5.8, "end": 11.6}
  ],
  "outro_line": "It's free and open source. Describe your site and see it built.",
  "outro_setting": "",
  "title": "One sentence to a live bakery website",
  "description": "…",
  "language": "en"
}
```

`footage` is the recording's name in `run.json` (its `footage` keys). Write the draft to
`RUN/drafts/script.json`.

## Checking it

```sh
makable-shorts check-script RUN RUN/drafts/script.json
```

It prints each scene's stretch, word count and the speed it will play at. Then it lists errors (overlapping
stretches, a stretch outside its recording, an unknown recording), which you must fix, and warnings, which
you should fix unless there's a reason. Run it until there are no errors, then bring the script in:

```sh
makable-shorts import RUN script RUN/drafts/script.json
```
