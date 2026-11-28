# Hooks: the first 3 seconds

Most viewers decide in the first 3 seconds whether to stay or swipe. The hook is the opening line, plus what is on
screen while it's said. It has one job: give the viewer a reason to watch to the end. Below are ten kinds of hook
that work in Shorts. Pick the one that fits the video's payoff, not the one that sounds loudest.

**Where the hook goes:**
- in a demo, it's `intro_line` (the avatar says it, or a title card shows it);
- in an animation, it's shot 1's `text`, and `hooks[hook]`.

## The rules for every hook

1. **The video must deliver what the hook promises.** A hook that the video doesn't pay off is clickbait. It
   loses viewers at the payoff, and earns angry comments. Misleading titles and hashtags also break YouTube's
   rules.
2. **The first frame shows the premise**, not a setup: the crowd already at the sea with straws, the finished
   website, the coconut already falling. The line and the picture tell the same story.
   - **An avatar demo** opens on the avatar, so the line carries the premise: name the result in its first words
     ("A whole bakery website, from one sentence…"), and put it in the shot when you can, through `intro_setting`
     ("…a laptop on the desk showing a finished bakery website"). A climax-first hook needs a card intro
     (below), not an avatar.
3. **No setup beat after the hook.** Seconds 3 to 8 are where earlier Shorts lost a third of their viewers.
   Drop lines like "chalo dekhte hain" and "let me show you". Go straight from the hook to the first new thing.
4. **Short.** A spoken hook says one idea, in the word limits of `script.md`. A card hook is 12 words at most,
   readable at a glance.
5. **Write three versions as three different kinds**, in the script's `hooks` (`H1`, `H2`, `H3`), with the one
   the video opens with in `hook`, and each one's kind in `hook_kinds`, by the name in brackets in its heading
   below: `"hook_kinds": {"H1": "climax first", "H2": "did you know", "H3": "contrarian"}`. metadata.json keeps
   the kind of the one used, so `/review-video` can learn which kind works on this channel. `check-script` says
   when a kind is missing or isn't one of these.
6. **The channel's lessons win.** If `lessons.md` says a kind of hook worked or flopped here, follow it over this
   file.

## The ten kinds

### 1. Climax first (`climax first`)
Show the best moment of the video in the first second, and cut away **just before** it resolves. The viewer has
to wait for the end to see what happens.
- **Animation:** shot 1 is the peak moment frozen or cut a moment early: the coconut a few centimetres above the
  head, the last drop of the ocean on the straw. The last shot finishes that moment. This also makes the video
  loop, because the end runs back into the start.
- **Demo, with a title card** (`intro: card`): the card shows a still of where scene 1 starts, so make scene 1
  a short stretch of the finished result, a second before it's complete (the site loading its last section).
  Scene 2 goes back to the recording's start to show how it got there. `check-script` warns that scene 2 goes
  back to before scene 1: that's the point here, so leave it. With an avatar intro, use another kind of hook.
- Best for: anything with one strong visual payoff.

### 2. Contrarian (`contrarian`)
Say something that goes against what most viewers believe. It grabs attention because the viewer wants to argue,
or to know why.
- "Samundar ka paani peena dangerous nahi hai… agar ye straw ho." / "You don't need to learn code to build a
  website."
- The video must back it up with a fact or a demo. Don't contradict a belief that's actually true.
- Best for: myth-busting facts, and "you're doing it the hard way" product demos.

### 3. "___, stop scrolling" (`stop scrolling`)
Name the target audience in the first word or two: "Students, stop scrolling." "Shop owners, ruko!" It breaks
the scroll by speaking to a specific person.
- Name a group that will actually see the video and that the video is really for.
- Best for: product demos with a clear user (students, freelancers, small shops).

### 4. Fear of missing out (`fear of missing out`)
A line that makes the viewer feel they'll lose something by swiping: "Agar aap ye nahi jaante, toh exam mein
ghante waste karoge." "Ignore this and your website will never show up on Google."
- Keep it about a real, everyday loss, never health, money or safety scares the video can't back up.
- Best for: tips and tools that save time or money.

### 5. Authority (`authority`)
Say why the viewer should trust you: experience, effort, or numbers. "Maine 30 AI website builders try kiye.
Sirf ye ek free hai." "I made 50 Shorts with AI. Here's what actually got views."
- It must be true. Use the user's real experience, from their notes or what they told you.
- Best for: product comparisons and "what I learned" videos.

### 6. Time-sensitive (`time-sensitive`)
Put the year or "now" in the hook, so it feels up to date: "2026 mein free website banane ka sabse aasaan tareeka."
- Use it only when the method is really current. Update or retire the video when it stops being true.
- Best for: tools and how-tos, where people search for the newest way. Good for search titles too.

### 7. Abstract concept (`abstract concept`)
Name a concept most viewers have heard of only vaguely, or never: "Kya aapne Zeigarnik effect ke baare mein suna
hai? Aap shayad abhi isi mein phase ho." They stay to learn what it is, and whether it applies to them.
- Explain it in plain words within the next scene. Don't leave the viewer lost.
- Best for: science, psychology and "why does this happen" explainers.

### 8. "Did you know…" (`did you know`)
Open with a surprising fact: "Kya aap jaante ho, ek nariyal 80 kilometer prati ghante ki speed se gir sakta hai?"
"Did you know Google Docs can turn your handwriting into text?"
- The fact must be surprising and sourced (put the source in the description).
- Best for: fact animations and hidden features of a tool.

### 9. "If you want ___, this is for you" (`if you want`)
Fill the blank with what the viewer wants: "Agar aapko bina coding ke apni website chahiye, ye aapke liye hai."
"If you want to finish assignments faster, this is for you."
- Name one specific want, not a vague one ("success").
- Best for: product demos, where the product delivers that want.

### 10. Listicle (`listicle`)
Promise a fixed number of things: "3 free websites jo har student ke paas hone chahiye." "5 facts about the
ocean you won't believe." A fixed number tells the viewer how long they're signing up for, so they stay to
the end.
- Keep the number small for a Short (3, or at most 5), and give each point its own scene.
- Put the best point last, and say early that the last one is the best ("teesra wala sabse crazy hai", in a list
  of 3), so viewers don't leave midway. The teaser names the point that really is last.
- Best for: tool roundups, fact collections.

## Which kind for which video

| Video | Try first | Also good |
|---|---|---|
| "What if…" or fact animation | Climax first, Did you know | Contrarian, Abstract concept |
| Story from the scriptures (devotional) | Climax first | Did you know |
| Product demo (one tool) | If you want ___, ___ stop scrolling | Fear of missing out, Time-sensitive |
| "Useful website" Short | ___ stop scrolling, Did you know | Listicle |
| Tool comparison or roundup | Authority, Listicle | Contrarian |

## After the hook

- **Hold the payoff to the end.** The hook opens a question. Answer it in the last scene, not in scene 2.
- **Ask for a guess, not a follow.** "Kitne saal lagenge? Comment mein guess karo," with the answer at the end,
  gets comments. A spoken "follow karo" at the end is where earlier Shorts lost the most viewers. Leave the
  follow to the screen: the subscribe animation (`me --subscribe`) over the last shot, if there is one.
- **Let the end loop into the start.** It's easy with a climax-first hook: the last shot is the moment the first
  shot cut away from.
