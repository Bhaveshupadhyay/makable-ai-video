# Writing the browser-use task

browser-use's agent does the task in a real Chrome while the screen is recorded. At each step it gets the
page's elements and a screenshot, and picks the next clicks and typing. Write the task the way you'd brief
a careful tester who has never seen the product. Save it as `RUN/task.md`.

## What the recording is for

The recording becomes about 50 seconds of narrated footage, after the model's thinking pauses are cut out
and the waits are cut down to the moments the page changed. So:

- **Show one thing well.** Take the shortest path to the functionality, show it working, then show the
  result. Don't tour the app.
- **End on the payoff,** the result the video is about, visible and still for a moment.
- **Avoid long, aimless waits.** Waiting while the product works on something is fine (its notes say how
  long things take): progress steps make good footage.

## The window and the starting point

- The window is `--window`, the notes': 720×1280 gets a site's phone layout.
- The recording starts on `--url`: the notes' `url`, or a page deeper in where the flow starts (the notes'
  recording tips may say which). With `--signed-in`, the agent is already signed in, as the user was when
  they signed in by hand. Use it for anything behind the sign-in.

## The task's shape

```
You're testing <the product>, <what it is, from its notes>, in a phone-sized window. You're already signed in.
<One sentence: what to do and why, such as "Share a note with a teammate and check they can see it.">

1. <A step: where, what to click or type, using the labels exactly as the page shows them.>
   <What to do if the page is different: "If a list opens instead, first choose …".>
2. ...

Don't pay for anything, don't delete or publish anything, don't change any settings and don't sign out.

At the end, call done with success true only if every step worked. In its text, report whether each step
worked, anything that looked broken (an error message, a blank page, a step that never finished), and
roughly how long anything slow took (from the product's own timer, if it shows one).
```

## Rules that keep recordings clean

- **Labels exactly as shown.** Quote them: "Ask for a change to your site…", "New site",
  "Live preview". When a change touches the UI, find the labels in the commits' diff, or in the product's
  code, before you write the task.
- **Type a prompt as one line.** A line break presses Enter, which sends it half-written.
- **Names must be new,** where the product needs that (the notes say): add something unique, such as the
  date: "Crumb & Co 1026".
- **Waiting:** "Use the wait action for 30 seconds at a time, then look at the page again." Say when it's
  done (what the page shows), and when to give up: "Give up if the progress steps haven't moved for
  5 minutes, or after 10 minutes in all."
- **Never interrupt it:** "Don't reload the page, and don't click Stop, Cancel or anything else while
  it's working."
- **Errors:** "If the page shows an error such as 'Couldn't reach the server', wait 30 seconds and try
  the same thing once more. If it fails again, stop and report it." The script leaves the error out.
- **Check what matters:** have it confirm what the viewer should see ("Check that the preview shows an
  'Order for pickup' button in the hero"), and scroll inside the preview if that's below the fold.
- **Plan the steps:** keep the task under the step limit (`--max-steps`, 60 by default). Every 30-second
  wait is a step.

## A task that worked: makable, an AI website builder

makable builds a website from a prompt, in a chat with the site's preview under it. Its notes say a new site
starts on https://makable.tech/new, and that a site's name is also a GitHub repository, so it must be new.
This ran with `--signed-in --url https://makable.tech/new`. A build plus one change fit in 60 steps.

```
You're testing makable, an AI website builder, in a phone-sized window. You're already signed in as a demo user.
Build a new website from start to finish and check that each part works.

1. Start a new site. The page says "What do you want to build?" and has a box that says "Describe the site
   you want to build…": use it. If one of your sites opens instead (a chat with a preview of a site under
   it), first open the menu with the site's name at the top of the chat and choose "New site".
   Type this into the box as one line (a line break presses Enter, which sends it), then send it:
   "A one-page website for Crumb & Co, a small neighbourhood bakery: a hero with the bakery's name and a short tagline, a menu of 6 breads and pastries with prices, opening hours, and a contact section with an address and a phone number."

2. makable starts building the site in a chat. If it asks for the site's name, type "Crumb & Co 1026" in the
   chat's box and send it. Answer any other question with a short, sensible answer that fits a bakery.
   If makable says it needs an AI model or an API key, stop and report that.

3. Building takes a few minutes. While it works, the chat shows its progress steps and a timer counting
   the seconds. Wait for it: use the wait action for 30 seconds at a time, then look at the page again.
   Don't reload the page, and don't click Stop, Cancel or anything else while it's building.
   Give up if the progress steps haven't moved for 5 minutes, or after 10 minutes in all.

4. When it's done, the chat is at the top and a live preview of the site is under it. Wait until the
   preview's toolbar says "Live preview" (not "Building preview…" or "Preview error"). Check that the
   preview shows the bakery's name and its headline.

5. Ask for one change in the chat's box ("Ask for a change to your site…"), typed as one line:
   "Make the hero background a warm cream colour and add an 'Order for pickup' button."
   Wait for it the same way (give up after 5 minutes), then check that the preview shows the new button.

Don't publish the site, don't change any settings, don't click Undo and don't sign out.

At the end, call done with success true only if every step worked. In its text, report whether each step
worked, anything that looked broken (an error message, a blank or empty preview, a step that never
finished), and roughly how long the build and the change each took (from the chat's timer).
```

The first time this ran, makable said "crumb-co" and "crumb-co-bakery" already existed, so the agent tried
three names. A server error also made it send the change three times. The script skipped the retries, but
a unique name and the error rule above keep the footage shorter.
