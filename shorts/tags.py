"""Tags in the narration: how a line is said, not only what's said. "[laughter] Think, a coconut and your skull!"

OmniVoice performs a tag (you hear a laugh, not the word "laughter"). The captions show only the words, and a
narrator that performs no tags (Chatterbox, ElevenLabs' models, Kokoro) gets the line without them, so it never reads
one out. A tag is a lowercase word, or words joined by hyphens, in square brackets: other square brackets aren't
touched.

How to use them in a script is in skills/make-video/references/script.md.
"""

import re
from collections.abc import Callable

# The tags each narrator's model performs. OmniVoice knows 13 (OMNIVOICE): these are the ones that sound right in
# Hindi, where a cloned voice laughs or sighs instead of saying the tag. A tag that isn't here never reaches a script.
TAGS: dict[str, frozenset[str]] = {
    "omnivoice": frozenset({"[laughter]", "[sigh]", "[surprise-wa]"}),
}
# All of OmniVoice's own, by its README, for trying another one out (tests/test_tags.py checks TAGS are among them)
OMNIVOICE = frozenset({
    "[laughter]", "[sigh]", "[confirmation-en]", "[question-en]", "[question-ah]", "[question-oh]", "[question-ei]",
    "[question-yi]", "[surprise-ah]", "[surprise-oh]", "[surprise-wa]", "[surprise-yo]", "[dissatisfaction-hnn]",
})  # fmt: skip
# Friendlier names Claude or you may write, for the model's own
ALIASES = {"[laugh]": "[laughter]", "[laughs]": "[laughter]", "[sighs]": "[sigh]", "[wow]": "[surprise-wa]"}
TAG = re.compile(r"[ \t]*\[[a-z]+(?:-[a-z]+)*\](?!\()[ \t]*")  # with the spaces around it: not a [link](...)
CLOSES = ",.!?;:।…)\"'”’"  # what a line goes on with right after a word, with no space before it


def found(text: str) -> list[str]:
    """Every tag in `text`, in order, as written: "[laugh]", not "[laughter]"."""
    return [match.group().strip(" \t") for match in TAG.finditer(text)]


def performed() -> set[str]:
    """Every tag some narrator performs, by its own name."""
    return set().union(*TAGS.values())


def known(tag: str) -> bool:
    """Whether a tag is one some narrator performs, or an alias for one."""
    return ALIASES.get(tag, tag) in performed()


def _replaced(text: str, keep: Callable[[str], str]) -> str:
    """`text` with each tag as `keep(tag)` says ("" drops it), and the spaces around a dropped one tidied: none at
    the start or the end, or before a comma, and one between two words."""
    out: list[str] = []
    done = 0
    for match in TAG.finditer(text):
        out.append(text[done : match.start()])
        done = match.end()
        tag = match.group().strip(" \t")
        kept = keep(tag)
        if kept:
            out.append(match.group().replace(tag, kept))
            continue
        before, after = "".join(out), TAG.sub("", text[done:]).lstrip(" \t")
        if before.strip() and not before[-1].isspace() and after and after[0] not in CLOSES:
            out.append(" ")
    return "".join(out) + text[done:]


def without(text: str) -> str:
    """`text` without its tags: what the captions show, what's counted as words, and what a narrator that performs
    none of them is given. Text without tags comes back as it was."""
    return _replaced(text, lambda tag: "")


def for_model(text: str, model: str) -> str:
    """`text` as `model` should be given it: aliases as the model's own tags, those it performs kept, every other
    tag dropped."""
    performs = TAGS.get(model, frozenset())
    return _replaced(text, lambda tag: ALIASES.get(tag, tag) if ALIASES.get(tag, tag) in performs else "")
