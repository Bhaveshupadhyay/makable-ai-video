"""hear: what Whisper hears in each narration file, and in the intro and the outro you were filmed saying, against
what the script says is said there: the words that came out differently, for you to listen to.

    python -m shorts hear RUN [--model large-v3-turbo]

Nobody making the video hears it: a narrator can say a word wrong (a site's name, an English word in Hindi, such as
"डाउनलोड"), and Omni sometimes says a line a little differently. Whisper (faster-whisper, on this machine's CPU) writes
down what each file says, and the words it heard that the script doesn't have, or the other way round, are the places
to listen to. Whisper gets words wrong too, so a difference is a place to listen, not a mistake for sure.

Whisper writes the English words in Hindi in English letters ("website" for वेबसाइट): those are compared by their
consonants, so one said with a wrong vowel isn't caught. A Devanagari word is compared as it's spelled, give or take
the ways of writing the same sound (a nukta, a halant, chandrabindu).

A narration file is compared with what the narrator was given to read: its scene's text, with run.json's
`pronounce` respellings. Writes heard.json in the run folder. Needs the `whisper` extra (faster-whisper): the
plugin's makable-shorts makes its environment the first time, and the model downloads once (large-v3-turbo, about
1.6 GB).
"""

import difflib
import json
import subprocess
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .media import executable
from .run import FILMED_INTRO, FILMED_OUTRO, Run, narrated, writing
from .stages.base import NotReady, read_script
from .voice import respelled

MODEL = "large-v3-turbo"  # Whisper's, as faster-whisper names it: good at Hindi, and fast enough on a CPU
HEARD = "heard.json"
FILMED = ("omni", "heygen", "import")  # an intro or outro that's a clip of someone talking
# Ways of writing the same Devanagari sounds that Whisper and a script may each use: the nukta (फ़ and फ),
# chandrabindu for anusvara (हाँ and हां), a halant (कर्सिव and करसिव), and the joiners.
SPELLINGS = str.maketrans({"\u093c": None, "\u0901": "\u0902", "\u094d": None, "\u200c": None, "\u200d": None})
NUKTA = "\u093c"
# Each Devanagari consonant's sound, as near as English's letters say it, for an English word Whisper writes in
# English letters ("website") where the script has it in Devanagari (वेबसाइट): the two are compared by their
# consonants, since the vowels are written too differently to compare.
SOUNDS = dict(
    zip(
        "कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसहंँः",
        "kkggnccjjnttddnttddnpfbbmyrlvssshnnh",
        strict=True,
    )
)
WITH_NUKTA = {"ज": "s", "फ": "f", "ड": "r", "ढ": "r"}  # ज़ is a z, which English's consonants count as an s
# English spellings of one sound, and letters not said: in the order they're replaced
ENGLISH = (("ph", "f"), ("sh", "s"), ("ch", "C"), ("th", "t"), ("ck", "k"), ("qu", "k"), ("wr", "r"), ("kn", "n"),
           ("gn", "n"), ("x", "ks"), ("z", "s"), ("q", "k"))  # fmt: skip
SAME_SOUND = 0.75  # how alike two words' consonants are, at least, to be the same word in two scripts

Transcribe = Callable[[Path, str], str]  # (an audio or video file, its language) -> what's said in it


def said_words(text: str) -> list[str]:
    """`text`'s words: lower case, without punctuation. Hyphens split words ("लिखते-लिखते" is two)."""
    text = unicodedata.normalize("NFC", text).lower()
    return "".join(" " if unicodedata.category(letter)[0] in "PSZ" else letter for letter in text).split()


def spelling(word: str) -> str:
    """One way of writing a word's Devanagari: without a nukta, a halant or a joiner, and anusvara for
    chandrabindu."""
    return word.translate(SPELLINGS)


def devanagari(word: str) -> bool:
    return any("\u0900" <= letter <= "\u097f" for letter in word)


def collapsed(letters: list[str]) -> str:
    """The letters, with each one said twice in a row once ("ss" in assignment)."""
    return "".join(letter for index, letter in enumerate(letters) if not index or letter != letters[index - 1])


def consonants(word: str) -> str:
    """A word's consonants, as English letters: वेबसाइट and website are both "vbst"."""
    if devanagari(word):
        found = []
        for index, letter in enumerate(word):
            if letter in SOUNDS:
                nukta = word[index + 1 : index + 2] == NUKTA
                found.append(WITH_NUKTA.get(letter, SOUNDS[letter]) if nukta else SOUNDS[letter])
        return collapsed(found)
    letters = "".join(letter for letter in word.lower() if "a" <= letter <= "z")
    if letters.startswith("u"):
        letters = "y" + letters[1:]  # use, user: "yu"
    for spelled, sound in ENGLISH:
        letters = letters.replace(spelled, sound)
    found = []
    for index, letter in enumerate(letters):
        after = letters[index + 1 : index + 2]
        if letter in "aeiou" or (letter == "y" and index):
            continue
        if letter == "w" and after not in tuple("aeiou"):  # follow, show: a vowel's
            continue
        found.append(
            {"c": "s" if after in tuple("eiy") else "k", "g": "j" if after in tuple("eiy") else "g", "w": "v"}.get(
                letter, letter
            ).lower()
        )
    return collapsed(found)


def same(said: str, heard: str) -> bool:
    """Whether a word was heard as written: the same, spelled one of the ways it can be, or in the other script,
    with the same consonants (website for वेबसाइट). In the same script, a vowel heard differently is a difference
    (डॉनलोड for डाउनलोड); across scripts, it can't be told."""
    if spelling(said) == spelling(heard):
        return True
    if devanagari(said) == devanagari(heard):
        return False
    ours, theirs = consonants(said), consonants(heard)
    return bool(ours) and difflib.SequenceMatcher(None, ours, theirs, autojunk=False).ratio() >= SAME_SOUND


def differences(said: str, heard: str) -> list[dict[str, str]]:
    """Where what was heard isn't what was said (`same`): each word, or stretch of words, that differs,
    {"said", "heard"} ("" for words left out, or heard but not in the script)."""
    a, b = said_words(said), said_words(heard)
    matcher = difflib.SequenceMatcher(
        None, [spelling(word) for word in a], [spelling(word) for word in b], autojunk=False
    )
    found = []
    for change, a1, a2, b1, b2 in matcher.get_opcodes():
        ours, theirs = a[a1:a2], b[b1:b2]
        if change == "equal":
            continue
        if change == "replace" and len(ours) == len(theirs):  # word for word
            found += [{"said": x, "heard": y} for x, y in zip(ours, theirs, strict=True) if not same(x, y)]
        elif not (ours and theirs and same("".join(ours), "".join(theirs))):  # words split or joined differently
            found.append({"said": " ".join(ours), "heard": " ".join(theirs)})
    return found


def matched(said: str, heard: str) -> float:
    """How much of what was said was heard as written: 1 for all of it."""
    words = said_words(said)
    differ = sum(len(difference["said"].split()) for difference in differences(said, heard))
    return 1 - differ / len(words) if words else 1.0


def to_hear(run: Run) -> list[tuple[str, str, str]]:
    """What there is to hear in the run, in the order it plays: (the file, what it is, what it should say). The
    intro and the outro, when they're clips of you, and each narration file that's made."""
    settings, script = run.settings(), read_script(run)
    files: list[tuple[str, str, str]] = []
    if settings.intro in FILMED and run.path(FILMED_INTRO).exists():
        files.append((FILMED_INTRO, "The intro", script.intro_line))
    if settings.narrator != "none":
        for path, text in narrated(script, settings):
            if run.path(path).exists():
                name = Path(path).stem
                what = f"Scene {int(name)}" if name.isdigit() else f"The {name} card"
                files.append((path, what, respelled(text, settings.pronounce or {})))
    if settings.outro in FILMED and script.outro_line.strip() and run.path(FILMED_OUTRO).exists():
        files.append((FILMED_OUTRO, "The outro", script.outro_line))
    return files


def samples(path: Path, rate: int = 16000) -> Any:
    """A file's sound as Whisper takes it: mono, 16 kHz, floats, decoded by the pipeline's ffmpeg (not PyAV, whose
    versions change what faster-whisper can call)."""
    import numpy

    command = [executable(), "-hide_banner", "-loglevel", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(rate)]
    result = subprocess.run([*command, "-f", "f32le", "-"], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg can't read {path}: {result.stderr.decode().strip()}")
    return numpy.frombuffer(result.stdout, dtype=numpy.float32)


def whisper(model: str = MODEL) -> Transcribe:
    """faster-whisper's `model`, loaded once, on the CPU."""
    from faster_whisper import WhisperModel

    loaded = WhisperModel(model, device="cpu", compute_type="int8")

    def transcribe(path: Path, language: str) -> str:
        # Not told what the script says: it'd hear that, rather than what's there
        options = {"language": language, "beam_size": 5, "condition_on_previous_text": False}
        segments, _ = loaded.transcribe(samples(path), **options)
        return " ".join(segment.text.strip() for segment in segments).strip()

    return transcribe


def hear(run: Run, transcribe: Transcribe | None = None, model: str = MODEL) -> list[dict[str, Any]]:
    """Hears every file there is to hear in the run (`to_hear`), writes heard.json, and returns what it has: each
    file's {file, what, said, heard, matched, differences}."""
    files = to_hear(run)
    if not files:
        raise NotReady("there's nothing to hear yet: no narration, and no intro or outro clip of you")
    language = read_script(run).language
    transcribe = transcribe or whisper(model)
    heard = []
    for path, what, said in files:
        text = transcribe(run.path(path), language)
        heard.append(
            {
                "file": path,
                "what": what,
                "said": said,
                "heard": text,
                "matched": round(matched(said, text), 3),
                "differences": differences(said, text),
            }
        )
    with writing(run.path(HEARD)) as out:
        out.write_text(json.dumps(heard, indent=1, ensure_ascii=False) + "\n")
    return heard


def report(run: Run, heard: list[dict[str, Any]]) -> str:
    """What `hear` prints: each file, what was heard in it where it differs, and which to listen to."""
    lines = []
    for item in heard:
        count = len(said_words(item["said"]))
        lines.append(
            f"{item['what']} ({item['file']}): {round(item['matched'] * count)} of {count} words heard as written"
        )
        if item["differences"]:
            lines += [f"  said:  {item['said']}", f"  heard: {item['heard']}"]
            for difference in item["differences"]:
                said = f'"{difference["said"]}"' if difference["said"] else "nothing"
                heard_as = f'"{difference["heard"]}"' if difference["heard"] else "nothing"
                lines.append(f"  listen: {said} came out as {heard_as}")
    listen = [item["file"] for item in heard if item["differences"]]
    if listen:
        lines.append(f"Listen to {len(listen)} of {len(heard)}: {', '.join(str(run.path(file)) for file in listen)}")
    else:
        lines.append(f"All {len(heard)} heard as written")
    return "\n".join(lines)
