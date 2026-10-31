# Driving the recording

You record the footage by driving a real Chrome yourself, a command at a time, while the pipeline records
its screen (`shorts/drive.py`). Each command is a step, as a tester's would be: it does one thing on the
page, with a mouse pointer gliding to what it clicks or types into, and prints the page as it is after it.
Afterwards, the time you spent thinking between commands is cut out, and so are the still parts of your
waits. Typing plays 4× as fast, the video zooms in on each click, and the pointer fades out 2 s after it.

## What the recording is for

The recording becomes about 50 seconds of narrated footage. So:

- **Show one thing well.** Take the shortest path to the functionality, show it working, then show the
  result. Don't tour the app.
- **End on the payoff,** the result the video is about, visible and still for a moment.
- **Every click is filmed, with a zoom.** Don't click around to find your way: read `look`'s elements
  and its screenshot instead. Looking isn't a step, so it isn't in the footage.

## Plan it first

Before `start`, write down the steps from `changes.md`: what to click, the labels exactly as the page
shows them, and what to type. Read the product's notes for its recording tips first. Anything the product
needs to be new each time (a project's name, say) gets something unique, such as the date ("Crumb & Co 1026").

## The commands

`RUN` is the run's folder. Every command takes `--name NAME` for a footage other than `demo`.

```sh
makable-shorts drive RUN start --url https://app.example.com/projects --signed-in --window 720x1280
makable-shorts drive RUN look                     # the page again, without doing anything
makable-shorts drive RUN click 12 --goal "Open the project menu"
makable-shorts drive RUN type 9 "A one-page website for …" --goal "Describe the site"
makable-shorts drive RUN type 9 "A one-page website for …" --goal "…" --spotlight   # only if asked for
makable-shorts drive RUN keys Enter --goal "Send it"
makable-shorts drive RUN scroll down --pages 0.5 [--number 31]   # --number scrolls inside that element
makable-shorts drive RUN wait 30 --goal "It builds the site"           # only what changes is kept
makable-shorts drive RUN hold 3 --goal "The finished site"             # all of it is kept
makable-shorts drive RUN wait-for "Ready" --timeout 240 --goal "Wait for the build"
makable-shorts drive RUN tab 4666 --goal "Switch to the live site"
makable-shorts drive RUN open https://… [--new-tab]
makable-shorts drive RUN act go_back              # any other of browser-use's actions, its parameters as JSON
makable-shorts drive RUN stop --report "…" [--failed]
```

- **The page.** `start`, `look` and every step print the tabs (with their ids, for `tab`), how far down the
  page is, and its elements, each with a number in brackets: `[12]<button>New site</button>`. Use the
  numbers from the latest output: they change when the page does. The output ends with a screenshot's
  path: Read it when the elements don't say enough, say, to see what a preview shows.
- **`--goal`:** what the step is for, in a few words. The script is written from the goals, so make them
  say what a viewer would see ("Pick GitHub Pages"), not the mechanics ("Click 31").
- **`--spotlight`** (`click` and `type`): the rest of the page blurs and dims, and the element stands out
  in a ring, from half a second before the pointer moves to it until the click lands or the typing's
  done. **It's off: use it only when the user asks for it** (for this video, or for every video), and
  not when they say not to. Even then:
  - **Never on a button:** on a small one it's a ring round a speck. A button isn't spotlit even with
    `--spotlight`, so use it for typing, or a click on something that isn't a button (a card, a link).
  - **Only the moments the video is about,** such as typing the prompt, not every step: it's in the
    footage for good, and on every step it stops meaning anything.
  - A text field that has no border of its own (a chat app's prompt, say) lights the box it's in.
- **A failed command** (an element that isn't there, a `wait-for` whose text never showed) exits with an
  error and the page as it is. It's still a step, which the script can skip.
- **Bash's timeout:** most commands answer within seconds. `start` takes up to a minute or two, `wait`, `hold` and
  `wait-for` take their seconds, and `stop` takes minutes: it cuts the video, about a minute for every 5
  minutes recorded. Give each Bash call a timeout above that, such as 300000 ms for `wait-for --timeout 240`,
  and 600000 ms for `stop`.
- **One driver per footage.** It stops by itself after 30 minutes without a command, keeping what it
  recorded. A new `start` after `stop` records the footage again, replacing it.

## Rules that keep recordings clean

- **The window** is the notes' (`--window`): 720×1280 gets a site's phone layout, which fills a vertical
  video. A product without one records at 1280×800, and the video shows it whole.
- **Signed in, it's a real account:** with `--signed-in` you're whoever the user signed in as, and what you
  make stays in their account. Start where the flow starts (`--url` a page deeper in, if the notes say so),
  so the footage doesn't open on menus.
- **Type a prompt as one line,** in one `type`. A line break presses Enter, which sends it half-written.
- **Keep it short.** Every minute recorded makes `stop` take longer, so don't leave the driver idle.
- **Waiting:** while the product works on something slow, use `wait-for` with the text that shows when it's
  done (the notes may say what), and run it again if it isn't done yet. Its moments where the page changes
  are kept: progress steps make good footage. Give up after about 10 minutes in all.
- **Never interrupt it** while it works: don't reload the page, and don't click Stop, Cancel or anything else.
- **Errors:** if the product shows an error such as "Couldn't reach the server", `wait 30` and try the same
  thing once more. If it fails again, `stop --failed` and report it. The script leaves the error out.
- **Check what matters** before you stop: that the page shows what the viewer should see. Scroll to it if
  it's below the fold, slowly (`--pages 0.5`), since the scroll is filmed.
- **Hold the end:** once the payoff shows, `hold 3` so it's still on screen for a moment, then `stop`. A
  `wait` won't do: its still parts are cut.
- **Don't** pay, delete, publish, invite people, change settings or sign out, unless that's what the video
  is about, nor anything the notes say not to.

## The report

`stop --report` takes what you'd tell whoever writes the script: whether each step worked, anything that
looked broken (an error message, a blank preview, a step that never finished), and how long anything slow
took (by the product's own timer, if it shows one). Add `--failed` if the recording doesn't show what it was for.
