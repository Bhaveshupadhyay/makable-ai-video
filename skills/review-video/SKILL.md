---
name: review-video
description: Finds out how a posted Short or Reel did on YouTube and Instagram, and why. It covers views, watch time, average view duration, retention, swipe-aways and engagement, compared with the user's other videos. From the retention curve, the script and the frames, it works out where viewers left and what was said and shown there, then says what to change next time and keeps the lessons in the product's notes for the make-video skill. Use when the user asks how a video did, why it flopped or took off, for its analytics, insights, watch time or engagement, or what's working on their channel.
argument-hint: "[run folder, YouTube or Instagram link] [--yes]"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(makable-shorts *), Bash(ffprobe *)
---

# How a video did, and why

The request: $ARGUMENTS

The `makable-shorts` command fetches the numbers (`${CLAUDE_PLUGIN_ROOT}/shorts/insights.py` says what each is).
Your part is the judgment: why the video did as it did, and what to do differently next time.

Run it with `makable-shorts …`: the plugin puts it on the Bash tool's PATH. The first time, and after an update,
a command first sets up its Python environments, which takes a few minutes, so give it a Bash timeout of 600000 ms.
Never print a key or a token, and never ask the user to paste one into the chat.

With `--yes`, never ask anything: decide, and say what you decided in the final report.

## 1. Which video

- **A run folder** (`.makable-shorts/runs/<name>/`), or "the last one": the newest run folder with a `final.mp4`.
  Its `script.json` says what was said, `metadata.json` where each part is in the video, and its
  `footage/*.steps.json` what was on screen. That's what makes the "why" possible.
- **A link** to a Short or a Reel. If it's one of the run folders' videos (same title as its `metadata.json`),
  use that folder. If not (a video made elsewhere), make a folder for it,
  `.makable-shorts/runs/<yyyy-mm-dd>-posted-<slug>`, from its posting date and title. There's no script there,
  so retention comes in 10-second stretches instead of parts.
- **The channel as a whole** ("what's working?", "why do my Shorts flop?"): go to step 5.

## 2. The accounts

Run `makable-shorts me`. The `connected` line shows which platforms are connected.

- **YouTube** needs the user's own OAuth client: `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` in the `.env` that
  `me` names. If they're missing, point the user to `${CLAUDE_PLUGIN_ROOT}/README.md`'s "How your videos did", and
  stop until they're added. Then run `makable-shorts connect youtube` in the background and tell the user: "Google's
  consent page is open in your browser: pick the channel's account and allow it." It finishes when they do.
- **Instagram** needs `INSTAGRAM_ACCESS_TOKEN` in that `.env` (the same README section says how to get one), then
  `makable-shorts connect instagram`.

Connect only the platforms the video is on. With `--yes`, use what's connected, and say what wasn't.

## 3. Fetch the numbers

```sh
makable-shorts insights RUN [--youtube LINK] [--instagram LINK]
```

Give each link the first time. After that, the run remembers them. With no link, it finds the run's video among
the channel's 50 newest uploads by the title in `metadata.json`.

It prints a report for each platform and keeps all of it in `RUN/insights/<platform>.json`. Read the JSON too: it
has the full retention curve, the views day by day, and every one of the user's other videos with its numbers.

- **This video against the median** of the user's other Shorts or Reels posted in the last 90 days
  (`--days` changes that). The numbers are shares and per 1,000 views, so videos of any size compare:
  - didn't swipe away: YouTube's engaged views as a share of views; on Instagram, 1 minus the skip rate (skipped
    in the first 3 seconds);
  - watched on average, in seconds and as a share of the length;
  - likes, comments, shares, saves and subscribers per 1,000 views.
- **Where its views came from** (YouTube): the Shorts feed, search, the channel page, and so on.
- **Still watching, part by part** (YouTube's audience retention): the share still watching at the start and end
  of the intro, each scene and the outro, how fast viewers left in each, and what's said in it. A share above 100%
  means people watched that part again.
- **Not given:** what a platform wouldn't answer, and why. Say so plainly. Don't guess numbers it didn't give.

**Too early to judge?** If it was posted less than 48 hours ago, or has under about 200 views, the numbers are
thin. Say so, give what there is, and suggest checking again in a few days.

## 4. Why it did as it did

Work from the numbers to the video, never the other way round. For each finding, give the number, what was on
screen and said then, and the likely reason. Keep what the numbers show apart from what you think explains it.

1. **Verdict.** Did it do better or worse than the user's usual, and on what? A video can win on views and lose on
   watch time. Its rank among the others, and its views day by day, show whether the feed kept pushing it or
   stopped after the first day.
2. **The hook:** the first 3 seconds, where most viewers decide. Compare "didn't swipe away" and the share still
   watching after 3 s with the median. Look at what opened it: `makable-shorts frames RUN final --at 0 0.5 1 1.5 2
   2.5 3 --width 540`, and the script's `intro_line`. Is the first frame something worth stopping for? Does the
   first sentence promise a concrete payoff? Weak openers include a slow greeting, a name before a reason, or a
   generic claim.
3. **Where they left.** Take the two or three parts with the steepest drop, then the frames at their times
   (`makable-shorts frames RUN final --at …`), the scene's text in `script.json`, and its stretch of the
   recording in `footage/<name>.steps.json`. Common reasons:
   - nothing changes on screen for a while (a wait, a spinner, a long form);
   - the narration explains something the screen doesn't show yet;
   - the text is too small to read on a phone;
   - the payoff was given away early, so there's nothing left to wait for;
   - it repeats itself;
   - the outro starts and people leave (normal: compare with the user's other videos).

   A part where the curve stays flat or rises (rewatched) worked. Say what's in it.
4. **The end.** How many are left at the end, and whether the end rises (loops: the end runs into the start).
5. **Engagement.** Shares and saves per 1,000 views mean people found it useful enough to keep or pass on.
   Comments mean curiosity, a question or disagreement. Likes are the weakest sign. On YouTube, subscribers per
   1,000 views shows whether it made people want more. Compare each with the median, not with general benchmarks.
6. **Reach** (where its views came from). Mostly the Shorts feed means the hook and the retention decided it.
   Search or the channel page means the title did.
7. **Against the user's best videos.** In the JSON's `others`, look at the two or three with the best "didn't swipe
   away" and watch share. What do their titles, lengths and (if they're run folders too, with `insights` fetched)
   intros and scenes do that this one doesn't? Run `makable-shorts posts youtube` (or `instagram`) for the list.

## 5. The channel as a whole

For "what's working?": run `makable-shorts posts youtube` (and `instagram`), and `insights` on the run folders of
the best and the worst few. Look for what the best ones share, compared with the worst: the hook's kind, the length,
the topic, the pace, the outro. Be honest about how few videos there are to go on.

## 6. Write it down

Write `RUN/insights/review.md`:

- **Verdict:** one or two sentences.
- **The numbers:** this video against the median, as a small table.
- **Where viewers left, and why:** each finding with its part, its time, the number, what was said and shown,
  and the likely reason.
- **What worked:** keep doing it.
- **Next time:** three changes at most, each concrete enough for the next script or recording. For example:
  "open on the finished site, then say how", "cut the 6-second wait in scene 3", "end on the live link, not
  a sign-off".

Then **keep the lessons**, so the next script follows them. Keep only what should change future videos, a line
each, with its evidence: "Opening on the finished result kept 71% past 3 s against a median of 58% (2026-10-30
clothing-store-publish)". Update a lesson when a new video confirms or contradicts it, and drop one the numbers
stop backing. Don't add one that only explains this video. There are two places:

- **The channel's lessons**, `lessons.md` in SHORTS_HOME (the folder `makable-shorts me` prints first). Both
  make-video and make-animation read it before writing a script. It's for what holds for any video on the
  channel: the first frame and the hook, the seconds after it, the ending, the length, comments and likes, the
  title and the upload (a title that can be searched, how often to post). Keep its sections, and the channel's
  median at the top up to date. If it isn't there, make it, with a line saying what it's for.
- **The product's notes** (`me` lists where), under `## What's worked`, for what holds only for that product:
  which flow or result to show, how to talk about it. Notes in the product's repo are the user's to commit: say so.

A channel review (step 5) writes its findings to `lessons.md` too, and "Still to learn" there lists what to check
once the numbers are in (a video too new for its retention, say).

## 7. Report

Tell the user, briefly:
- the verdict and the three or four numbers behind it, against their median;
- where viewers left, and why;
- what to change next time;
- where the review is (`RUN/insights/review.md`), and the lessons you added or changed, in `lessons.md` and in
  the notes.

Offer to make the next video with those changes (`/make-video`), or to redo this one's script, which is cheaper:
only the narration of each scene whose text changed is made again, and the intro and outro only if their lines
change, about a dollar each.
