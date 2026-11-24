# Characters

A character is drawn once, as a **character sheet**: the same character three times, front, three-quarter and side
view, full body, on a plain light background. Every still with them in it is drawn from that sheet, so their face,
body and clothes stay the same from shot to shot.

## A look that draws well

`look` is a phrase: build, face, hair, clothes and colours, in plain words.

> a bald cartoon man, round friendly face, plain blue t-shirt, grey shorts, barefoot

- **Plain, solid colours** and simple clothes: a pattern or a print changes from shot to shot.
- **One thing to know them by** (bald, a red cap, round glasses), so a viewer sees it's the same person at once.
- **No text on clothes**, no brands, no one real.
- Give each character a name the shots use (`man`, `doctor`, `cat`), with letters, digits, - and _ only.

## Choosing a take

`cast` draws `cast_takes` takes. A good sheet has:
- the same face, body and clothes in all three views;
- all three views there, full body, with nothing cropped;
- the plain background, with nothing else in it, and no text;
- the look the script describes.

Choose with `makable-shorts choose RUN <name> <take>`. The chosen sheet is locked: changing the `look` later
doesn't redraw it. To start over, delete `cast/<name>.png` and run `cast` again.

## Mascots

A character the channel uses in every Short is kept with the user's own things: `makable-shorts me --character
<name>=<sheet.png>`, in `me/characters/` in SHORTS_HOME. Any Short with a character of that name uses it as it is,
whatever its `look` says (keep the look in the script the same anyway: the still prompts use the name). `me
--character <name>=` forgets it.
