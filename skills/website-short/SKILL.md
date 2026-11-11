---
name: website-short
description: Makes a "useful website" Short of 20 to 30 seconds for YouTube Shorts and Instagram Reels, in Hindi or English, about someone else's free website. You find what's trending on YouTube Shorts, pick a site from it that's free, needs no sign-in and shows its result within a minute, record it from a Google search to its payoff, and write the script; the pipeline films the user's avatar saying a 4-second hook, ends on the sign-off clip kept for every website Short, narrates it in the avatar's voice, and assembles it. Then Whisper checks the narration, and you stop for the user's approval, with the title, description and tags for YouTube Studio. Use when the user asks for a website Short, a "useful website" video, a video about a trending site or tool, or for the day's one.
argument-hint: "[a site or a topic] [--language hi|en] [--yes]"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(makable-shorts *), Bash(ffprobe *)
---

# Making a "useful website" Short

The request: $ARGUMENTS

A useful-website Short shows viewers a free website they didn't know, the way a friend would: "your hand hurts
from writing assignments? This site writes them for you". It's 20 to 30 seconds:

1. **The hook,** about 4 s: the user's avatar, to the camera, says a problem the viewer has, then the promise.
2. **The recording,** about 20 s, narrated in the avatar's voice: Google search, the first result, one thing done on
   the site, the payoff, and one more thing it can do.
3. **The sign-off:** the avatar again, with a cheeky "you know when to use this" and "follow for more websites like
   this". It's one clip, kept in SHORTS_HOME and brought into every website Short, so it's filmed once.

The video is made by this plugin's pipeline, the `makable-shorts` command, as for the make-video skill: read
`${CLAUDE_PLUGIN_ROOT}/skills/make-video/SKILL.md`'s opening (the pipeline, keys, `--yes`) once. Its references are
this skill's too: [drive.md](../make-video/references/drive.md) for recording,
[script.md](../make-video/references/script.md) for the script (its "useful website" section), and
[product.md](../make-video/references/product.md) for a site's notes. Never print a key, read the `.env`, or ask
for a key in the chat.

**Ask nothing until the end** (step 11), except what step 1 says you can't go on without. You pick the site, as
the user would. With `--yes` (a schedule), ask nothing at all: where this says to stop, stop and say why.

## 1. What's set up

Run `makable-shorts me`. This kind needs:

- **An avatar:** `filmer` `omni` (it films the 4-second hook), and a `face`. HeyGen or clips brought in work too,
  but HeyGen can't film to a length. If no filmer is chosen, or it's `none`, set it up as make-video's step 1 says
  (or stop, with `--yes`).
- **A narrator** in the avatar's voice: `modal` (OmniVoice) or `elevenlabs`, with its keys set.
- **`trends`: YOUTUBE_API_KEY set.** If it isn't, run `makable-shorts keys --open --trends`, and tell the user:
  it's a free API key from console.cloud.google.com, in a project with the YouTube Data API v3 on (APIs and
  services, Library), made under APIs and services, Credentials, Create credentials, API key. They paste it into the
  file that opened and save it. With `--yes`, stop and say so. If the request names a site, you can go on without
  it: skip step 2.
- **`signed in`: google.com.** Google shows the recorder an "unusual traffic" check unless it was passed once, by
  hand. If google.com isn't listed, run `makable-shorts signin --url https://www.google.com` in the background and
  tell the user: "Chrome is open on google.com: search for anything, tick the box if Google asks, then close the
  window." With `--yes`, stop and say so.
- **`sign-offs`** in the video's language (Hindi, `hi`, unless the request says otherwise). If there's none, this
  video's outro is filmed (about $1, once), and step 11 keeps it for the next ones.

## 2. What's trending

```sh
makable-shorts trends "useful website" "website for students" "ai website" "free website" --language hi
```

Each search costs 100 of the key's 10,000 units a day; the same search again that day costs nothing. It lists
the Shorts posted in the last 14 days, the outliers first: those whose views outrun their channel's subscribers
and their age. For each it shows its title, link, views, channel, the sites its description names (`names:`), and
whether a site made already is in it (`made already:`). `--json` adds each one's description and tags.

From the top of the list, write down the candidates: what each Short shows (from its title, its description and
its tags), and the site, where it's named. Leave out the ones `made already`, and run `makable-shorts topics` to
see every site made before. Two Shorts about the same kind of site (text to handwriting, background removers)
make that kind a strong topic. If the request names a site or a topic, it's that one.

## 3. Pick the site

A site is good for this only if all of these are true. Check each one, on the site itself:

- **Free, with no sign-in and no sign-up** for what the video shows: no paywall, no "create an account to
  download", no trial that asks for a card.
- **A result you can see within a minute** of opening it: typing, uploading or clicking something on screen, and
  the result appearing, without waiting in a queue.
- **It works on a phone's screen** (the recording is 720x1280), and opens without a full-page ad or a pop-up you
  can't close.
- **Harmless:** the cheeky sign-off is about homework and work shortcuts, not harm. Leave out sites for cheating
  in exams, piracy or downloading others' videos, fake documents, deepfakes of real people, hacking, gambling,
  adult content, and anything that takes payments or personal details.
- **Not made already** (`makable-shorts topics`).

To check a site, open it in a trial recording, in a run folder of its own that no video is made from,
`<runs>/<yyyy-mm-dd>-trial` (`runs` is the folder `me` printed): `makable-shorts drive TRIAL start --url
https://<site> --window 720x1280`, `look` at it, do the one action, `wait-for` its result, and `stop`. If a site
fails, try the next candidate. If none of the first five passes, search for something else (`trends` with other
words), or stop and say what you tried.

Where a Short doesn't name its site, find it on Google in the trial: search what the Short shows, and take the
first result that passes.

## 4. The site's notes

Write the site's notes in SHORTS_HOME's `products/<name>.md` (`me` names the folder), as
[product.md](../make-video/references/product.md) describes, before recording:

```markdown
---
name: texttohandwriting.com
url: https://www.google.com
signed_in: true             # google.com's profile, where Google's "unusual traffic" check was passed by hand
window: 720x1280
code: none (a third-party site, shown as a "useful website" Short)
pronounce:
  hi: {texttohandwriting.com: टेक्स्ट टू हैंडराइटिंग डॉट कॉम}
---

## What it is
One or two sentences: what it does, for whom, and that it's free with no sign-in.

## The sign-off
The kept sign-off's line (`makable-shorts sign-off`), or the one this video's outro will say.

## Recording tips
- The search: the words typed into Google, and the first result's title.
- Each step on the site: the labels exactly as shown, and what shows when the result is ready (for wait-for).
```

`name` is how the site is written: its address, as viewers would type it. `pronounce` says the address the way
the narrator should: in Hindi, the English words in Devanagari, with "डॉट कॉम" for ".com".

## 5. The run

Pick the run's folder, `<runs>/<yyyy-mm-dd>-<slug>`, in the `runs` folder `me` printed, with the site's name as
the slug: it's `RUN` below.

```sh
makable-shorts new RUN --format website --language hi --tone hype --no-captions --pronounce "texttohandwriting.com=टेक्स्ट टू हैंडराइटिंग डॉट कॉम"
```

- `--format website` has Omni film the hook for 4 s (`intro_seconds`), and brings in the kept sign-off as the
  outro (it prints its line): the video's outro is never filmed again.
- `--no-captions` for Hindi: the captions can't draw Devanagari yet. In English, leave them on.
- `--pronounce` for each of the notes' `pronounce` words.

Write `RUN/changes.md` as make-video's step 2 does: what a viewer can do with the site, where on it, the steps,
and what the viewer sees at the end.

## 6. Record it

Follow [drive.md](../make-video/references/drive.md). Start on Google, signed in, and keep the whole recording
under a minute:

```sh
makable-shorts drive RUN start --url https://www.google.com --signed-in --window 720x1280
makable-shorts drive RUN type 7 "text to handwriting" --goal "Search Google for text to handwriting"
makable-shorts drive RUN keys Enter --goal "Search"
makable-shorts drive RUN click 23 --goal "Open the first result, texttohandwriting.com"
…                                    # one thing done on the site, then its result
makable-shorts drive RUN wait-for "Download" --timeout 60 --goal "The handwriting is ready"
…                                    # one more thing it can do: another style, another option
makable-shorts drive RUN hold 3 --goal "The finished page"
makable-shorts drive RUN stop --report "…"
```

- **The search** is what a viewer would type: the words for what the site does ("text to handwriting",
  "remove background"), not its address. Open the site's own result: the first one, if it is.
- **One thing done:** the site's main action, with something short and relatable (a line of an assignment, a
  photo the notes name, a few words). Show the result, still, for a moment.
- **One more:** a second style, a setting, the download button. Don't download files, sign up, pay, or
  share anything.
- If Google shows its "unusual traffic" check, the sign-in has run out: have the user do step 1's sign-in again,
  or with `--yes`, stop and say so.

Check it as make-video's step 5 does (`makable-shorts frames RUN demo`, and look at every sheet), and record it
again, at most twice more, if it doesn't show the result. Add what the next recording should know to the site's
notes.

## 7. The script

Follow [script.md](../make-video/references/script.md), its "useful website" section: a hook of 12 words at most,
3 to 6 scenes said to the viewer ("search…", "type…", "and there it is"), about 20 s of narration in all, the
outro line exactly as the kept sign-off says it (run.json's `sign_off_line`), a title, a description, and tags. The
hook's setting is the sign-off's, with what the person wears in it (Read the still that `new` printed): Omni
dresses them anew each clip, and a grey shirt cutting to a red one shows the sign-off was filmed apart.
Write it to `RUN/drafts/script.json`, then:

```sh
makable-shorts check-script RUN RUN/drafts/script.json
```

Fix every error, and every warning unless there's a reason not to. Then
`makable-shorts import RUN script RUN/drafts/script.json`.

## 8. Make it

```sh
makable-shorts run RUN --paid
```

Run it in the background: it films the 4-second hook with Omni (about $0.40), and the outro too if no sign-off is
kept (about $1), takes the avatar's voice from the hook, speaks each scene in it, and assembles `RUN/final.mp4`,
which ends a moment after the sign-off's last word. If it stops, it says why: fix that and run it again.

## 9. Hear it

```sh
makable-shorts hear RUN
```

Whisper writes down what the hook, each scene and the sign-off say, and lists the words that came out differently
from the script. The first time, it sets up its Python and downloads Whisper (about 1.6 GB): give it a Bash
timeout of 1800000 ms.

Whisper gets words wrong too, so a difference is a place to listen, not a mistake for sure. For each one, decide:

- **Whisper's spelling of the same sound** (हैंडराइटिंग and हैण्डराइटिंग, a digit for a number word): fine.
- **A word the narrator may have said wrong,** such as an English word in Hindi (डाउनलोड heard as डॉनलोड) or the
  site's name: respell it, `makable-shorts new RUN --pronounce WORD=SAID`, add that to the notes' `pronounce`, and
  run steps 8 and 9 again. Only the scenes with that word are spoken again. Do this at most twice.
- **The hook said differently by Omni:** if it changes the meaning, say so in the report, and that filming it again
  costs about $0.40 (delete `RUN/intro/filmed.mp4`, then step 8).

Whatever's still flagged goes in the report, for the user to listen to.

## 10. Log it

```sh
makable-shorts topics --add texttohandwriting.com --about "text to handwriting" --run RUN
```

`--about` is the words for what the site does, comma-separated: `trends` marks Shorts about them as made from
then on, so no site is made twice.

## 11. Report, and stop for approval

Tell the user:

- **The video:** `RUN/final.mp4` and its length (`RUN/metadata.json` has its seconds).
- **For YouTube Studio**, ready to paste: the title, the description, and the tags as one comma-separated line.
- **The site, and why:** the Short it came from (its title, link, views, and how far it outran its channel), and
  that it's free with no sign-in.
- **What's said:** the hook, each scene's text, and the sign-off.
- **To listen to:** what `hear` still flags, with the files' paths.
- **What it cost:** about $0.40 for the hook (and about $1 for the outro, if it was filmed), and the narration's
  few cents.
- To tick YouTube's "altered or synthetic content" box: `metadata.json`'s `containsSyntheticMedia`.

Then ask whether to post it, change something, or drop it. It isn't uploaded: they post it themselves for now. If
they drop it, take the site out of the log (`makable-shorts topics --remove SITE`).

**If this video's outro was filmed** (there was no sign-off kept), ask whether to keep it for every website Short in
this language: `makable-shorts sign-off --from RUN`. With `--yes`, keep it, and say so.
