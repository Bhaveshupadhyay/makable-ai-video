# script.json for an animated Short

The same file as a demo's (`${CLAUDE_PLUGIN_ROOT}/shorts/script.py` has the format), with a storyboard, and no intro
or outro: the video opens on its first shot and ends on its last.

```json
{
  "style": "Stylized 3D medical-explainer CGI, glossy Pixar-like render, soft studio light, clean cyan-to-white radial gradient background",
  "characters": [
    {"name": "man", "look": "a bald cartoon man, round friendly face, plain blue t-shirt, grey shorts, barefoot"}
  ],
  "scenes": [
    {
      "text": "[surprise-wa] अगर पच्चीस मीटर ऊँचे पेड़ से नारियल सीधा आपके सिर पर गिरे… तो क्या खोपड़ी बचेगी?",
      "footage": "shot-01",
      "shot": {
        "still": "The man sits at the foot of a tall coconut palm, eyes closed, smiling; low angle looking up the trunk",
        "motion": "The camera tilts up the trunk; a coconut snaps loose and falls toward him; it freezes just above his head",
        "characters": ["man"]
      }
    },
    {
      "text": "एक नारियल डेढ़-दो किलो का होता है, और गिरते-गिरते अस्सी किलोमीटर प्रति घंटे तक पहुँच जाता है।",
      "footage": "shot-02",
      "shot": {
        "still": "Side view of one green coconut falling past the palm trunk, glowing cyan speed streaks behind it",
        "motion": "The coconut falls in slow motion, the streaks stretching; the camera tracks down with it"
      }
    }
  ],
  "title": "क्या नारियल आपकी खोपड़ी तोड़ सकता है?",
  "description": "… Source: Barss, Journal of Trauma, 1984",
  "language": "hi",
  "hooks": {
    "H1": "अगर पच्चीस मीटर ऊँचे पेड़ से नारियल सीधा आपके सिर पर गिरे… तो क्या खोपड़ी बचेगी?",
    "H2": "एक नारियल आपकी खोपड़ी तोड़ सकता है, और ये मज़ाक नहीं है।",
    "H3": "अस्सी किलोमीटर प्रति घंटे की रफ़्तार से आता एक नारियल… सीधा आपके सिर की तरफ़।"
  },
  "hook": "H1"
}
```

- **`footage`:** `shot-01`, `shot-02`, … in order, one per scene. Each shot is its own clip.
- **`caption`:** what the captions show, when it isn't `text`. For a Hindi Short, write each line in Hinglish
  (Hindi in Latin letters: "agar pachchees meter oonche ped se ek nariyal…"), word for word with `text` and with
  no tags, unless the user wants Devanagari. **Numbers are always digits in a caption**, whatever words the narrator
  says them in: "25 meter" (not "pachchees meter"), "80 kilometer prati ghante", "1.5-2 kilo". `new --captions-at bottom` puts the captions low in the frame.
- **`text`:** what's said over the shot, 8 to 18 words (4 to 8 seconds), with tags as `/make-video`'s
  [script.md](../../make-video/references/script.md) describes them. The first scene's text is the hook: the same
  words as `hooks[hook]`.
- **`shot`:** `still`, `motion`, `characters` (by name), `follows` (true when it continues the shot before, in the
  same place), and `end_still` (only for a model that takes a last frame: H3, not Omni). See [shots.md](shots.md).
- **`intro_line`** and **`outro_line`** stay empty: the hook is shot 1's text, and the sign-off is the last shot's.

## What `check-script` holds it to

Errors (the video can't be made):
- no `style`; two characters with one name; a character without a look;
- a scene without a shot, or a shot without a still or a motion;
- a shot naming a character who isn't in `characters`;
- two scenes with the same footage;
- text, captions, logos, brands or watermarks asked for in the style, a look, a still or a motion.

Warnings (it can be made, but may not look or sound right):
- a shot said in under 4 or over 8 seconds: it won't fit a clip;
- fewer than 4 or more than 6 shots, or narration far from 30 seconds;
- tags a narrator won't perform, or more than three of them.
