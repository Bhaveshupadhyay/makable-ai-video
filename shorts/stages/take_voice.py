"""take-voice: the avatar's voice, for the narration. voice/avatar.wav is the sound of the intro Omni filmed, from
where the talking starts, up to 10 seconds (OmniVoice clones best from 3 to 10).

With `narration_voice` "intro" in run.json, the narration is spoken in it, so the narrator sounds like the person in
the intro and the outro, which are used as filmed. Needs only ffmpeg.
"""

from ..run import AVATAR_VOICE, FILMED_INTRO, Run, file_hash, fingerprint, writing
from ..voice import voice_sample
from .base import NotReady, Stage

SECONDS = 10.0


class TakeVoice(Stage):
    name = "take-voice"
    product = "avatar-voice"
    needs = ("intro",)
    where = "anywhere with ffmpeg"  # no packages of its own

    def plan(self, run: Run) -> dict[str, str]:
        filmed = run.path(FILMED_INTRO)
        if not filmed.exists():
            raise NotReady(f"{FILMED_INTRO} isn't there yet")
        return {AVATAR_VOICE: fingerprint("take-voice", file_hash(filmed), SECONDS)}

    def make(self, run: Run, paths: list[str]) -> None:
        with writing(run.path(AVATAR_VOICE)) as out:
            voice_sample(run.path(FILMED_INTRO), out, length=SECONDS)
