# Writing the style, the stills and the motion

Image and video models do what's described, and invent everything that isn't. Describe pictures, exactly.

## The style

One sentence, written once, that every image prompt starts with. Name the render, the light and the background:

> Stylized 3D medical-explainer CGI, glossy Pixar-like render, soft studio light, clean cyan-to-white radial
> gradient background

If some shots happen outdoors, say so in the style ("…, outdoor shots in warm afternoon sun"). Otherwise the model
picks its own background for each still, and the shots stop looking like one video.

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

The clip is 4 to 8 seconds: two actions at most. Split anything longer into two shots.

## Never in a prompt

- **Text, captions, logos, brands, watermarks:** the models are told to show none, and the check refuses a prompt
  that asks for them. They spell words wrong, and brands are someone else's.
- **Real people,** by name or by likeness.
- **Gore.** "Clinical and non-graphic, no blood" for anything medical: an x-ray cutaway shows impact without it.

## The end still

`end_still` describes a shot's last frame, for a video model that takes one, to end a shot exactly ("the crack lines
glowing across the top of the skull"). Omni takes only a first frame, so with Omni leave it out: say the end state
in the motion instead.
