# Writing the script

The script is `script.json`: what the avatar says at the start and the end, and what the narrator says over
each stretch of the screen recording. You write it from three things:

- **The steps:** `footage/<name>.steps.json` in the run, what browser-use did and when (seconds into the video).
- **The frames:** `makable-shorts frames RUN <name>` makes contact sheets of what's on screen when, in
  `RUN/frames/`. Look at them. For text too small to read, use `--at <seconds> ... --width 720`.
- **What it's about:** `RUN/changes.md`, if there is one, or what the user asked for. The run's
  `run.json` gives the `language` and the `tone`, and the product's notes its name, what it is and its sign-off.

**Trust the frames over the steps.** The steps say what the program did ("Waited 30 seconds", "Typed …"),
and its final report says what it saw. Neither tells you what's on screen at a given second: a preview
may still be loading, or show only the top of a page. Say only what's visible during the scene's stretch.

## The video's three parts

1. **Intro**, about 10 s. The avatar (Gemini Omni) talks to the camera.
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
