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

## Gods and sages (the devotional style)

Write the look from how the scriptures and temple art show them, in plain words, and keep it the same across the
channel's Shorts: devotees know these figures, and notice when one changes.

> a five-year-old boy, curly black shoulder-length hair, big dark eyes, white U-shaped Vaishnava tilak on his
> forehead, bare-chested, a rudraksha mala, a white dhoti with a red border, barefoot

> an old sage, long white hair in a top knot wrapped with rudraksha beads, long white beard, three white lines of
> ash and a saffron dot on his forehead, saffron robe over one shoulder, rudraksha malas

- **Say an adult is an adult**: "a tall adult god in his thirties with adult body proportions and broad
  shoulders". The style's big eyes and soft rounded features draw everyone as a child otherwise: Shani, Vishnu,
  Parvati and Shani's wife all came out as children or teenagers on their first sheets (2026-11-28). Children and
  babies need no help.
- **Say the clothes exactly**, colour by colour. Without a sheet, the same boy came back in a saffron cloth in
  place of his white dhoti one shot later.
- **The god's marks belong in the look:** blue skin, a peacock feather, a crescent moon in the hair, a conch and a
  discus. Anything the god holds goes in the look too, so it's in every shot.
- **A figure the channel comes back to** (Krishna, Hanuman, Narada as a storyteller) is a mascot: keep its sheet
  with `me --character`, so it looks the same in every Short.

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
