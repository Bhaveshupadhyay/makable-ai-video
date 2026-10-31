# The product's notes

Every video is about one product: the user's own web app or site. What you need to know to record it and talk
about it is kept in a file of its own, so you ask once and every video after uses it:

- **In the product's own repo,** when you're in it: `.makable-shorts/products/<name>.md` at the repo's root,
  committed with its code, so teammates and the GitHub workflow make videos from the same notes.
- **Otherwise in SHORTS_HOME:** `products/<name>.md` there (`~/.config/makable-shorts` unless that's set), for a
  product whose code isn't here, or that has none.

`makable-shorts me` lists them all, with each one's file. `<name>` is the product's name in lowercase, with
hyphens for spaces.

It's Markdown, with the settings the commands need at the top:

```markdown
---
name: Acme Notes            # as it's written: on screen, in the script and the captions
url: https://app.acme.com   # where recordings start, unless a video starts deeper in
signed_in: true             # record signed in (`makable-shorts signin --url <url>`, once)
window: 720x1280            # the browser: 720x1280 for its phone layout, 1280x800 if it has none
code: .                     # where its code is: "." for the repo these notes are in, GitHub repos, or a folder
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

1. **Its name and address:** the page recordings should start on. Every video needs it, so never write notes
   without a `url`, and never guess one. In the product's repo, look for it first (a `homepage` in
   package.json, the README, a CNAME file, the deploy's config: vercel.json, netlify.toml, fly.toml), and ask
   the user to confirm what you found. A local address (`http://localhost:3000`) works too, for what isn't
   deployed yet, while the app runs there.
2. **Sign-in:** whether what's worth showing is behind a sign-in. If it is, suggest a demo account: the
   recordings show the account and act in it, so what they make stays there. Then sign in once, by hand: run
   `makable-shorts signin --url <url>` in the background, and tell the user: "Chrome is open on
   <url>: sign in there, then close the window." The command finishes when they close it.
3. **Its code:** in the product's repo, it's `.`, the repo itself: ask only whether another repo holds part of
   it (a separate backend). Elsewhere, a GitHub repo (`owner/repo`, more than one if the app and the backend
   are separate) or a folder on this machine, if there is one. With it, videos can be made from commits, and
   you learn each flow from the code. Without it, videos are made from a description, found on the product
   itself.
4. **The sign-off:** what viewers should do after watching (try it free, star it on GitHub, sign up at …).
5. **How to say its name,** only if it's not an ordinary word, or if they want it said a certain way.

The window: use 720×1280 unless the user says the product has no phone layout. If the first recording shows
a cramped or broken page, record it again with `--window 1280x800` and note that.

Then write the file (in the repo if you're in the product's, else in SHORTS_HOME), and show the user what you
wrote. Notes in the repo are theirs to commit: say so. In `--yes` mode, never set notes up: stop and say the
product has none.

## Keeping them up to date

After a recording, add what the next one should know to the recording tips, in a line or two: a label that
moved, how long something took, a dialog that came up, a step that failed and what fixed it. Leave out what's
only true of this video.
