# Writing the style, the stills and the motion

Image and video models do what's described, and invent everything that isn't. Describe pictures, exactly.

## The style

One sentence, written once, that every image prompt starts with. Name the render, the light and the background:

> Stylized 3D medical-explainer CGI, glossy Pixar-like render, soft studio light, clean cyan-to-white radial
> gradient background

If some shots happen outdoors, say so in the style ("…, outdoor shots in warm afternoon sun"). Otherwise the model
picks its own background for each still, and the shots stop looking like one video.

### Ready-made styles

Use one when the user names it, or asks for that look in other words.

- **Glossy explainer** (the default): the sentence above.
- **Cutaway** (also "Blender", "Blender cross-section", "like those 3D Blender Shorts"): a plain Blender render with
  the scene cut open, so the viewer sees what happens underground, underwater or inside a wall.

  > Simple 3D Blender Eevee render: plain matte materials with no textures, simple props, simple stylized
  > characters, flat soft daylight, not glossy, not cinematic, no depth of field

  The style is the look alone, because it starts the character sheets' prompts too, and a sheet needs its plain
  background and its three clean views. The cut goes in each still instead. Start every still with the same
  framing, written once for the Short and fitted to what's cut open:

  - underground: "Straight-on side view, the ground cut away as a cross-section filling the lower half of the
    frame, soil in sandy-brown layers with faint strata lines, a blue sky with soft realistic clouds above";
  - underwater: "Straight-on side view, the sea cut away as a cross-section, clear blue water in the upper half,
    the seabed in layers of sand and rock below";
  - inside a wall or a body: "Straight-on side view, the wall cut open as a cross-section, its layers of plaster,
    brick and insulation showing", with the room or the place around it.

  Keep the camera the same in every motion: it holds still or pans sideways along the cut ("the camera pans right
  along the cut"). Say what moves in plain physical terms ("sand falls into the hole in chunky clumps", "water
  rises in the hole and fills it to the brim"). Water, splashes and flying sand are where a video model goes wrong
  most (stray rocks in the sky, a blob of a splash). With H3, give those shots an `end_still` that shows where the
  water or the sand ends up. Omni takes no last frame, so with Omni say that end state in the motion instead ("…
  and settles, the water still and level with the brim").

## A still

What the first frame shows: who, where, doing what, and from where the camera sees it.

- **Who:** by the names in `characters`, and list them in the shot's `characters`, so their sheets go in as
  references. Don't describe their looks again: the sheet does that.
- **Where:** the place, and anything in it that matters. Say "the same place as shot 1" and set `follows` when it
  continues the shot before.
- **The camera:** "low angle looking up the trunk", "close-up of his face", "side view".
- **One moment.** A still is a frame: "the coconut a metre above his head", not "the coconut falls and hits him".

## The motion

What the video model does with the still, in one action, and the camera's move:

- one thing happens: "a coconut snaps loose and falls; it freezes just above his head";
- the camera's move named: "tilts up", "tracks down with it", "slow push in", "holds still";
- the end state said: where it stops is where the next shot picks up.

The clip is 4 to 8 seconds with Omni, 3 to 6.5 with H3: one action, two at most. H3 is at its best at 5 seconds
or less: a short clip is made far quicker than a long one (about a minute for 4.5 s at 480p, several times that for
15 s) and drifts less. So with H3, about 5 seconds a shot, 6 to 8 shots for a 30-second Short, joined one after
another. Split anything longer into two shots, each with a still of its own.

## A shot with no one in it

A video model fills what a shot leaves open, and the style can steer it: with "medical-explainer" in the style, H3
turned a still of a balance scale into an anatomy figure. For a shot of things (a scale, an x-ray, a chart), say in
the motion that what's drawn stays exactly as drawn ("the scale, the coconut and the bottle stay exactly as
drawn"), say the one thing that moves, and give it an end still. Don't list what mustn't appear ("no confetti, no
people"): the words bring some of it in.

## Never in a prompt

- **Text, captions, logos, brands, watermarks:** the models are told to show none, and the check refuses a prompt
  that asks for them. They spell words wrong, and brands are someone else's.
- **Real people,** by name or by likeness.
- **Gore.** "Clinical and non-graphic, no blood" for anything medical: an x-ray cutaway shows impact without it.

## The end still

`end_still` describes a shot's last frame, for a video model that takes one, to end a shot exactly ("the crack lines
glowing across the top of the skull"). `stills` draws it from the shot's still, as `stills/<shot>-end.png`, for one
more image.

- **H3 takes one: give it one** on every shot where something moves toward a moment the next shot picks up, and on
  every shot with no one in it. Without it, H3 hurries the action to its end: the coconut that was to stop in
  mid-air above his head fell all the way and landed beside him, giving the answer away before the question. Make
  it the next shot's opening ("the coconut a couple of metres above his head, he hasn't noticed").
- **Omni takes only a first frame,** so with Omni leave it out: say the end state in the motion instead.
