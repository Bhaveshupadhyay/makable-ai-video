# The product's notes

Every video is about one product: the user's own web app or site. What you need to know to record it and talk
about it is kept in a file of its own, `products/<name>.md` in SHORTS_HOME (`~/.config/makable-shorts` unless
that's set; `makable-shorts me` prints where), so you ask once and every video after uses it. `<name>` is the
product's name in lowercase, with hyphens for spaces.

It's Markdown, with the settings the commands need at the top:

```markdown
---
name: Acme Notes            # as it's written: on screen, in the script and the captions
url: https://app.acme.com   # where recordings start, unless a video starts deeper in
signed_in: true             # record signed in (`makable-shorts signin --url <url>`, once)
window: 720x1280            # the browser: 720x1280 for its phone layout, 1280x800 if it has none
code: acme/notes-web        # where its code is, for commits and labels: GitHub repos, or a folder here (optional)
pronounce:                  # words the narrator says wrong, by language, spelled as they're said (optional)
  en: {Acme: akmee}
---

## What it is
One or two sentences: what it does, and for whom.

## The sign-off
What the outro asks viewers to do, in the product's own words: "Try Acme Notes free at acme.com."

## Recording tips
What keeps a recording clean, learned while recording it:
- where each flow starts (a page to open with `--url`);
- what the page shows when something slow is done (for `wait-for`), and about how long it takes;
- what must be new each time (a project's name), and what never to click (billing, deleting, publishing).
```

## Setting them up

When there are no notes for the product the user means, ask them, in one message where you can:

1. **Its name and address:** the page recordings should start on.
2. **Sign-in:** whether what's worth showing is behind a sign-in. If it is, suggest a demo account: the
   recordings show the account and act in it, so what they make stays there. Then sign in once, by hand: run
   `makable-shorts signin --url <url>` in the background, and tell the user: "Chrome is open on
   <url>: sign in there, then close the window." The command finishes when they close it.
3. **Its code** (optional): a GitHub repo (`owner/repo`, more than one if the app and the backend are
   separate) or a folder on this machine. With it, videos can be made from commits, and you can look up a
   feature's labels. Without it, videos are made from a description, found on the product itself.
4. **The sign-off:** what viewers should do after watching (try it free, star it on GitHub, sign up at …).
5. **How to say its name,** only if it's not an ordinary word, or if they want it said a certain way.

The window: use 720×1280 unless the user says the product has no phone layout. If the first recording shows
a cramped or broken page, record it again with `--window 1280x800` and note that.

Then write the file, and show the user what you wrote. In `--yes` mode, never set notes up: stop and say the
product has none.

## Keeping them up to date

After a recording, add what the next one should know to the recording tips, in a line or two: a label that
moved, how long something took, a dialog that came up, a step that failed and what fixed it. Leave out what's
only true of this video.
