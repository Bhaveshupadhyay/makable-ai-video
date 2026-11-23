"""Tags in the narration ("[laughter]"): found, left out of the captions, and given to each narrator as it takes them."""

from shorts.tags import OMNIVOICE, TAGS, for_model, found, known, without
from shorts.voice import ApiVoice, respelled

LINE = "[laughter] सोचो, एक छोटा सा नारियल और आपकी खोपड़ी!"


def test_the_tags_in_a_line() -> None:
    assert found(LINE) == ["[laughter]"]
    assert found("Wait, [sigh] it's [laughter] done.") == ["[sigh]", "[laughter]"]
    assert found("A [link](https://x.y), [1], [Laughter], [ laughter ], [laughter-]") == []  # not tags


def test_the_captions_show_only_the_words() -> None:
    assert without(LINE) == "सोचो, एक छोटा सा नारियल और आपकी खोपड़ी!"
    assert without("सोचो, [laughter] एक नारियल") == "सोचो, एक नारियल"
    assert without("It costs nothing [laughter].") == "It costs nothing."
    assert without("It's free [laughter]") == "It's free"
    assert without("[sigh] [laughter] Fine") == "Fine"


def test_text_without_tags_is_left_as_it_was() -> None:
    for text in ("Hello  there ,  you.", " spaced ", "A [link](https://x.y) and [1].", ""):
        assert without(text) == text
        assert for_model(text, "omnivoice") == text
        assert for_model(text, "chatterbox") == text


def test_omnivoice_performs_its_tags_and_other_narrators_get_none() -> None:
    assert for_model(LINE, "omnivoice") == LINE
    assert for_model(LINE, "chatterbox") == without(LINE)
    assert for_model(LINE, "eleven_multilingual_v2") == without(LINE)


def test_only_omnivoices_own_names_are_known() -> None:
    assert known("[laughter]") and known("[surprise-wa]")
    assert not known("[laugh]") and not known("[wow]")  # Claude swaps these by meaning, not the code
    assert for_model("[laugh] Yes, [sigh] fine.", "omnivoice") == "Yes, [sigh] fine."


def test_a_tag_no_narrator_performs_is_left_out() -> None:
    assert not known("[laff]")
    assert for_model("Ha [laff] ha.", "omnivoice") == "Ha ha."


def test_the_tags_omnivoice_performs_are_its_own() -> None:
    assert TAGS["omnivoice"] <= OMNIVOICE
    assert len(OMNIVOICE) == 13


def test_pronounce_respells_the_words_and_not_the_tags() -> None:
    assert respelled("[sigh] A sigh, [laughter]. Sigh!", {"sigh": "sai"}) == "[sigh] A sai, [laughter]. Sai!"
    voice = ApiVoice("sample.wav", model="omnivoice", pronounce={"laughter": "laafter"})
    assert voice.spoken("[laughter] Laughter.") == "[laughter] Laafter."
