# Driving the recording

You record the footage by driving a real Chrome yourself, a command at a time, while the pipeline records
its screen (`shorts/drive.py`). Each command is a step, as a tester's would be: it does one thing on the
page, with a mouse pointer gliding to what it clicks or types into, and prints the page as it is after it.
Afterwards, the time you spent thinking between commands is cut out, and so are the still parts of your
waits. Typing plays 4× as fast, and the video zooms in on each click.

## What the recording is for

The recording becomes about 50 seconds of narrated footage. So:

- **Show one thing well.** Take the shortest path to the functionality, show it working, then show the
  result. Don't tour the app.
- **End on the payoff,** the result the video is about, visible and still for a moment.
- **Every click is filmed, with a zoom.** Don't click around to find your way: read `look`'s elements
  and its screenshot instead. Looking isn't a step, so it isn't in the footage.

## Plan it first

Before `start`, write down the steps from `changes.md`: what to click, the labels exactly as the page
shows them, and what to type. A site's name must be new, since it's also a GitHub repository on the demo
account: add something unique, such as the date ("Crumb & Co 1026").

## The commands

`RUN` is the run's folder. Every command takes `--name NAME` for a footage other than `demo`.

```sh
.venv/bin/python -m shorts drive RUN start --signed-in        # opens https://makable.tech (--url for another page)
.venv/bin/python -m shorts drive RUN start --signed-in --url https://makable.tech/new   # straight to a new site's prompt
.venv/bin/python -m shorts drive RUN look                     # the page again, without doing anything
.venv/bin/python -m shorts drive RUN click 12 --goal "Open the site menu"
.venv/bin/python -m shorts drive RUN type 9 "A one-page website for …" --goal "Describe the site"
.venv/bin/python -m shorts drive RUN keys Enter --goal "Send it"
.venv/bin/python -m shorts drive RUN scroll down --pages 0.5 [--number 31]   # --number scrolls inside that element
.venv/bin/python -m shorts drive RUN wait 30 --goal "makable builds the site"      # only what changes is kept
.venv/bin/python -m shorts drive RUN hold 3 --goal "The finished site"             # all of it is kept
.venv/bin/python -m shorts drive RUN wait-for "Live preview" --timeout 240 --goal "Wait for the build"
.venv/bin/python -m shorts drive RUN tab 4666 --goal "Switch to the live site"
.venv/bin/python -m shorts drive RUN open https://… [--new-tab]
.venv/bin/python -m shorts drive RUN act go_back              # any other of browser-use's actions, its parameters as JSON
.venv/bin/python -m shorts drive RUN stop --report "…" [--failed]
```

- **The page.** `start`, `look` and every step print the tabs (with their ids, for `tab`), how far down the
  page is, and its elements, each with a number in brackets: `[12]<button>New site</button>`. Use the
  numbers from the latest output: they change when the page does. The output ends with a screenshot's
  path: Read it when the elements don't say enough, say, to see what a preview shows.
- **`--goal`:** what the step is for, in a few words. The script is written from the goals, so make them
  say what a viewer would see ("Pick GitHub Pages"), not the mechanics ("Click 31").
- **A failed command** (an element that isn't there, a `wait-for` whose text never showed) exits with an
  error and the page as it is. It's still a step, which the script can skip.
- **Bash's timeout:** most commands answer within seconds. `start` takes up to a minute or two, `wait`, `hold` and
  `wait-for` take their seconds, and `stop` takes minutes: it cuts the video, about a minute for every 5
  minutes recorded. Give each Bash call a timeout above that, such as 300000 ms for `wait-for --timeout 240`,
  and 600000 ms for `stop`.
- **One driver per footage.** It stops by itself after 30 minutes without a command, keeping what it
  recorded. A new `start` after `stop` records the footage again, replacing it.

## Rules that keep recordings clean

- **The window is 720×1280,** so makable shows its phone layout. With `--signed-in` you're makable's demo
  user. Signed in, https://makable.tech opens the last site the demo user worked on: a chat with that
  site's preview under it.
- **A new site starts on https://makable.tech/new** (`start --url`): it opens on "What do you want to
  build?", with a box that says "Describe the site you want to build…". Sending the prompt starts the new
  site in the builder, so the footage goes straight from the prompt to the build, with no menu to open.
- **Type a prompt as one line,** in one `type`. A line break presses Enter, which sends it half-written.
- **Keep it short.** Every minute recorded makes `stop` take longer, so don't leave the driver idle.
- **Waiting:** while makable builds (a few minutes) or deploys, use `wait-for` with the text that shows
  when it's done ("Live preview" in the preview's toolbar, "Your site is live"), and run it again if it
  isn't done yet. Its moments where the page changes are kept: the progress steps make good footage. Give
  up after about 10 minutes in all.
- **Never interrupt a build:** don't reload the page, and don't click Stop, Cancel or anything else while
  it's building.
- **Errors:** if makable shows an error such as "Couldn't reach the server", `wait 30` and try the same
  thing once more. If it fails again, `stop --failed` and report it. The script leaves the error out.
- **Check what matters** before you stop: that the page shows what the viewer should see. Scroll to it if
  it's below the fold, slowly (`--pages 0.5`), since the scroll is filmed.
- **Hold the end:** once the payoff shows, `hold 3` so it's still on screen for a moment, then `stop`. A
  `wait` won't do: its still parts are cut.
- **Don't** publish the site, change settings, click Undo or sign out, unless that's what the video is
  about.

## The report

`stop --report` takes what you'd tell whoever writes the script: whether each step worked, anything that
looked broken (an error message, a blank preview, a step that never finished), and how long the build and
anything else took, by makable's timer. Add `--failed` if the recording doesn't show what it was for.
