"""A "useful website" Short: what's trending (YouTube's Data API, stood in for), the topics log, the script's targets,
the 4-second hook cut where its talking ends, the kept sign-off, and hearing the narration against the script."""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shorts.hear import differences, hear, report, said_words
from shorts.home import keep_sign_off, sign_off, sign_offs
from shorts.intro import film
from shorts.run import FILMED_INTRO, FILMED_OUTRO, Run, Settings, narration_file
from shorts.script import Scene, Script, check, tag_characters
from shorts.stages.assemble import AFTER_SPEECH, Assemble
from shorts.stages.film_intro import FilmIntro, FilmOutro
from shorts.stages.speak import Speak
from shorts.trends import (
    YouTubeData,
    YouTubeError,
    find,
    forget_site,
    listing,
    log_site,
    made_already,
    made_sites,
    sites_in,
)

from .conftest import make, needs_ffmpeg
from .test_avatar import Omni

httpx = pytest.importorskip("httpx")

NOW = datetime(2026, 11, 11, 12, tzinfo=UTC)


def posted(days: float) -> str:
    return (NOW - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


# Three Shorts and their channels, as YouTube would answer for them.
VIDEOS = {
    "aaaaaaaaaaa": {  # a small channel's hit: the outlier
        "snippet": {
            "title": "Useful website for students😂",
            "channelId": "small",
            "channelTitle": "Tiny Tips",
            "publishedAt": posted(2),
            "description": "Site: www.texttohandwriting.com\nFollow me on instagram.com/tinytips, mail me@gmail.com",
            "tags": ["website", "students"],
        },
        "statistics": {"viewCount": "200000", "likeCount": "9000", "commentCount": "80"},
        "contentDetails": {"duration": "PT19S"},
    },
    "bbbbbbbbbbb": {  # a big channel's: more views, but fewer than its subscribers
        "snippet": {
            "title": "AI website that edits photos",
            "channelId": "big",
            "channelTitle": "Big Tech Hindi",
            "publishedAt": posted(5),
            "description": "Try it at photoeditor.ai and bit.ly/xyz",
        },
        "statistics": {"viewCount": "900000"},
        "contentDetails": {"duration": "PT45S"},
    },
    "ccccccccccc": {  # too few views
        "snippet": {"title": "My website", "channelId": "small", "channelTitle": "Tiny Tips", "publishedAt": posted(1)},
        "statistics": {"viewCount": "500"},
        "contentDetails": {"duration": "PT30S"},
    },
    "ddddddddddd": {  # longer than a Short
        "snippet": {"title": "Website review", "channelId": "big", "channelTitle": "Big", "publishedAt": posted(3)},
        "statistics": {"viewCount": "800000"},
        "contentDetails": {"duration": "PT3M30S"},
    },
}
CHANNELS = {
    "small": {"statistics": {"subscriberCount": "10000", "hiddenSubscriberCount": False}},
    "big": {"statistics": {"subscriberCount": "5000000", "hiddenSubscriberCount": False}},
}


class YouTube:
    """A stand-in for the Data API: search finds every Short, and the lookups answer for those asked."""

    def __init__(self, error: tuple[int, dict] | None = None) -> None:
        self.asked: list[httpx.Request] = []
        self.error = error

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        if self.error:
            return httpx.Response(self.error[0], json=self.error[1])
        what, params = request.url.path.rsplit("/", 1)[-1], request.url.params
        if what == "search":
            return httpx.Response(200, json={"items": [{"id": {"videoId": video}} for video in VIDEOS]})
        table = VIDEOS if what == "videos" else CHANNELS
        items = [{"id": key, **table[key]} for key in params["id"].split(",") if key in table]
        return httpx.Response(200, json={"items": items})

    def searches(self) -> int:
        return sum(request.url.path.endswith("/search") for request in self.asked)


def api(youtube: YouTube) -> YouTubeData:
    return YouTubeData("the-key", client=httpx.Client(transport=httpx.MockTransport(youtube)))


def test_trends_ranks_the_shorts_that_outrun_their_channels() -> None:
    youtube = YouTube()
    found = find(["useful website"], api=api(youtube), now=NOW)

    assert [item.id for item in found.trends] == ["aaaaaaaaaaa", "bbbbbbbbbbb"]  # too few views, too long: left out
    hit = found.trends[0]
    assert hit.ratio == 20 and hit.per_day(NOW) == 100_000  # 200k views on 10k subscribers, in 2 days
    assert hit.url == "https://www.youtube.com/shorts/aaaaaaaaaaa"
    assert hit.sites == ["texttohandwriting.com"]  # not the socials, nor an email's host
    assert found.trends[1].sites == ["photoeditor.ai"]
    assert found.units == 100 + 1 + 1  # a search, then a lookup of the videos and one of their channels

    search = youtube.asked[0]
    assert search.headers["X-Goog-Api-Key"] == "the-key" and "the-key" not in str(search.url)
    assert dict(search.url.params) == {
        "part": "snippet",
        "q": "useful website",
        "type": "video",
        "videoDuration": "short",
        "publishedAfter": "2026-10-28T12:00:00Z",
        "order": "viewCount",
        "regionCode": "IN",
        "relevanceLanguage": "hi",
        "maxResults": "25",
    }
    text = listing(found, NOW)
    assert "1. Useful website for students😂" in text and "20.0x its subscribers" in text
    assert "200k views in 2 days (100k a day" in text and "names: texttohandwriting.com" in text


def test_the_same_search_again_today_costs_no_quota(shorts_home: Path) -> None:
    youtube = YouTube()
    find(["useful website"], api=api(youtube), now=NOW)
    again = find(["Useful website", "website for students"], api=api(youtube), now=NOW + timedelta(hours=2))
    assert youtube.searches() == 2  # only the new one
    assert (again.kept, again.units, again.today) == (1, 102, 204)
    find(["useful website"], api=api(youtube), now=NOW, fresh=True)
    assert youtube.searches() == 3
    assert json.loads((shorts_home / "trends" / "2026-11-11.json").read_text())["units"] == 306


def test_a_short_about_a_site_made_already_is_marked() -> None:
    log_site("https://www.texttohandwriting.com/", about="text to handwriting", run="/runs/one")
    assert [entry["site"] for entry in made_sites()] == ["texttohandwriting.com"]
    sites = made_sites()
    assert made_already("Text To Handwriting kaise kare", sites) == "texttohandwriting.com"
    assert made_already("Best AI photo editor", sites) is None
    found = find(["useful website"], api=api(YouTube()), now=NOW)
    assert found.trends[0].made == "texttohandwriting.com"
    assert "made already: texttohandwriting.com" in listing(found, NOW)
    assert forget_site("texttohandwriting.com") and made_sites() == []


def test_what_youtube_says_no_with_never_has_the_key() -> None:
    quota = (403, {"error": {"code": 403, "message": "quota", "errors": [{"reason": "quotaExceeded"}]}})
    with pytest.raises(YouTubeError, match="quota for today is used up") as raised:
        find(["useful website"], api=api(YouTube(quota)), now=NOW)
    assert "the-key" not in str(raised.value)
    invalid = (400, {"error": {"message": "API key not valid. Please pass a valid API key.", "errors": [
        {"reason": "badRequest"}], "details": [{"reason": "API_KEY_INVALID"}]}})  # fmt: skip
    with pytest.raises(YouTubeError, match="isn't a key Google knows"):
        find(["useful website"], api=api(YouTube(invalid)), now=NOW)


def test_trends_needs_its_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="keys --open --trends"):
        find(["useful website"], now=NOW)


def test_the_sites_a_description_names() -> None:
    text = "Link: https://www.ilovepdf.com/merge_pdf, youtu.be/abc, t.me/x, a@b.com and Remove.bg!"
    assert sites_in(text) == ["ilovepdf.com", "remove.bg"]


# The script


def website_script(hook_words: int = 10, scene_words: int = 12, scenes: int = 4, **fields) -> Script:
    return Script(
        intro_line=" ".join(["शब्द"] * hook_words),
        intro_setting="A room at night.",
        scenes=[
            Scene(text=" ".join(["शब्द"] * scene_words), footage="demo", start=6.0 * n, end=6.0 * n + 5.0)
            for n in range(scenes)
        ],
        title="स्टूडेंट्स के लिए सीक्रेट वेबसाइट",
        description="…",
        outro_line="ऐसी वेबसाइट्स के लिए फॉलो करो।",
        language="hi",
        **({"tags": ["website", "students"]} | fields),
    )


def test_a_website_short_has_a_short_hook_and_about_20_seconds_of_narration() -> None:
    lengths = {"demo": 30.0}
    errors, warnings = check(website_script(), lengths, {"demo"}, outro=True, website=True)
    assert errors == [] and warnings == []  # 4 scenes of 12 words: about 19 s

    _, warnings = check(website_script(hook_words=15, scenes=8, tags=[]), lengths, outro=True, website=True)
    assert "The hook has 15 words: keep it to 12, for a clip of about 4 s" in warnings
    assert "The script has 8 scenes: 3 to 6 tell a 20-second story" in warnings
    assert "The narration is about 38 s long: aim for about 20 s" in warnings
    assert any(warning.startswith("There are no tags") for warning in warnings)

    # A demo's targets are as they were: 14 to 20 words of intro, and about 50 s
    _, warnings = check(website_script(), {"demo": 60.0}, outro=True)
    assert "The intro line has 10 words: 14 to 20 fit Omni's 10-second clip" in warnings
    assert "The narration is about 19 s long: aim for about 50 s" in warnings


def test_the_outro_line_is_what_the_kept_sign_off_says() -> None:
    script = website_script()
    _, warnings = check(script, {}, outro=True, website=True, sign_off="इसका यूज़ कहाँ करना है, आप समझदार हो।")
    assert "The outro is your kept sign-off, so its line is what it says: इसका यूज़ कहाँ करना है, आप समझदार हो।" in warnings
    _, warnings = check(script, {}, outro=True, website=True, sign_off=script.outro_line)
    assert not any("sign-off" in warning for warning in warnings)


def test_youtube_takes_500_characters_of_tags() -> None:
    assert tag_characters(["a b", "cd"]) == 3 + 2 + 2 + 1  # the quotes around "a b", and a comma
    _, warnings = check(website_script(tags=[f"tag number {n}" for n in range(40)]), {}, website=True)
    assert any(warning.startswith("The tags have 629 characters") for warning in warnings)


# The clips


def test_omni_films_the_hook_for_4_seconds(run: Run, tmp_path: Path) -> None:
    face = tmp_path / "face.jpg"
    face.write_bytes(b"jpeg")
    client = Omni(b"mp4 bytes")
    film(client, "a prompt", face, tmp_path / "clip.mp4", seconds=4)
    assert client.asked[0]["response_format"]["duration"] == "4s"
    with pytest.raises(ValueError, match="3 to 10 s"):
        film(client, "a prompt", face, tmp_path / "clip.mp4", seconds=20)

    run.save_settings(Settings(face=run.relative(face), outro="omni"))
    run.path("script.json").write_text(website_script().model_dump_json())
    own_length = FilmIntro().plan(run)
    run.save_settings(run.settings().model_copy(update={"intro_seconds": 4}))
    assert FilmIntro().plan(run) != own_length  # filmed again for 4 s
    assert FilmIntro().seconds(run.settings()) == 4 and FilmOutro().seconds(run.settings()) is None


@needs_ffmpeg
def test_a_website_shorts_clips_end_just_after_the_talking(run: Run, tmp_path: Path) -> None:
    clip = make(tmp_path / "intro.mp4", "testsrc2=s=180x320:r=30", "sine=f=440:d=1.5,apad=whole_dur=4", seconds=4)
    demo = Assemble().clip(clip, "Hi.", run.settings())
    assert demo.length == pytest.approx(4.0, abs=0.04)  # a demo's, as filmed
    website = Assemble().clip(clip, "Hi.", run.settings().model_copy(update={"format": "website"}))
    assert website.length == pytest.approx(1.5 + AFTER_SPEECH, abs=0.1)


def test_omnivoice_is_told_the_intro_line_is_what_the_avatars_voice_says(run: Run) -> None:
    run.path("script.json").write_text(website_script().model_dump_json())
    assert Speak().transcript(run, run.settings()) is None  # a demo's intro may be cut, in its 10 s
    website = run.settings().model_copy(update={"format": "website"})
    assert Speak().transcript(run, website) == website_script().intro_line
    told = website.model_copy(update={"reference_text": "What I said."})
    assert Speak().transcript(run, told) == "What I said."


# The kept sign-off


def new(run: Run, *args: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from shorts.__main__ import main

    monkeypatch.setattr(sys, "argv", ["shorts", "new", str(run.folder), *args])
    main()


def test_a_website_short_ends_on_the_kept_sign_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    run = Run(tmp_path / "runs" / "first")
    new(run, "--format", "website", "--language", "hi", "--outro", "omni", monkeypatch=monkeypatch)
    assert run.settings().intro_seconds == 4
    assert "There's no sign-off kept in hi yet" in capsys.readouterr().out
    assert run.settings().outro == "omni"  # filmed this time

    clip = tmp_path / "outro.mp4"
    clip.write_bytes(b"the sign-off")
    keep_sign_off("hi", clip, "ऐसी वेबसाइट्स के लिए फॉलो करो।")
    assert sign_offs() == {"hi": "ऐसी वेबसाइट्स के लिए फॉलो करो।"}

    second = Run(tmp_path / "runs" / "second")
    new(second, "--format", "website", "--language", "hi", "--outro", "omni", monkeypatch=monkeypatch)
    settings = second.settings()
    assert (settings.outro, settings.sign_off_line) == ("import", "ऐसी वेबसाइट्स के लिए फॉलो करो।")
    assert second.path(FILMED_OUTRO).read_bytes() == b"the sign-off"
    capsys.readouterr()
    new(second, "--tone", "hype", monkeypatch=monkeypatch)
    assert "The outro is your sign-off" not in capsys.readouterr().out  # it's in already

    # A demo never takes it
    demo = Run(tmp_path / "runs" / "demo")
    new(demo, "--language", "hi", "--outro", "omni", monkeypatch=monkeypatch)
    assert demo.settings().outro == "omni" and demo.settings().intro_seconds is None


def test_a_runs_outro_is_kept_as_the_sign_off(
    run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    from shorts.__main__ import main

    run.path(FILMED_OUTRO).parent.mkdir(parents=True)
    run.path(FILMED_OUTRO).write_bytes(b"filmed")
    run.path("script.json").write_text(website_script().model_dump_json())
    monkeypatch.setattr(sys, "argv", ["shorts", "sign-off", "--from", str(run.folder)])
    main()
    clip, line = sign_off("hi")
    assert clip.read_bytes() == b"filmed" and line == "ऐसी वेबसाइट्स के लिए फॉलो करो।"
    assert "every website Short in hi ends on it" in capsys.readouterr().out


# Hearing the narration


def test_the_same_words_written_two_ways_arent_a_difference() -> None:
    assert said_words("लिखते-लिखते हाथ दुख गया? ये वेबसाइट!") == ["लिखते", "लिखते", "हाथ", "दुख", "गया", "ये", "वेबसाइट"]
    assert differences("यूज़ कहाँ करना है।", "यूज कहां करना है") == []  # the nukta, and chandrabindu as anusvara
    assert differences("पीडीएफ़ भी डाउनलोड कर लो", "पीडीएफ भी डॉनलोड कर लो") == [{"said": "डाउनलोड", "heard": "डॉनलोड"}]
    assert differences("one two three", "one three four") == [
        {"said": "two", "heard": ""},
        {"said": "", "heard": "four"},
    ]
    assert differences("कोई कर्सिव", "कोई करसिव") == []  # a halant


def test_english_words_whisper_writes_in_english_letters_are_heard_as_written() -> None:
    # What Whisper wrote for the texttohandwriting.com Short's narration, by OmniVoice
    said = "गूगल पे टेक्स्ट टू हैंडराइटिंग सर्च करो, और पहली वेबसाइट खोलो।"
    assert differences(said, "गूगल पे text to handwriting सर्च करो और पहली website खोलो") == []
    said = "जनरेट इमेज दबाओ, और असली कॉपी के पेज जैसी इमेज तैयार, पीडीएफ़ भी डाउनलोड कर लो।"
    heard = "generate image दबाओ और असली copy के page जैसी image तयार PDF भी डाउनलोड कर लो"
    assert differences(said, heard) == [{"said": "तैयार", "heard": "तयार"}]  # a vowel, in the same script
    said = "इसका यूज़ कहाँ करना है, आप समझदार हो। ऐसी वेबसाइट्स के लिए फॉलो करो।"
    assert differences(said, "इसका use कहां करना है आप समझदार हो ऐसी websites के लिए follow करो") == []
    assert differences("पूरी चौदह हैंडराइटिंग", "पूरी 14 handwriting") == [{"said": "चौदह", "heard": "14"}]


def test_hear_flags_the_words_that_came_out_differently(run: Run) -> None:
    script = website_script(scenes=2)
    script.scenes[0].text = "texttohandwriting.com खोलो"
    script.scenes[1].text = "पीडीएफ़ भी डाउनलोड कर लो"
    run.path("script.json").write_text(script.model_dump_json())
    run.save_settings(
        run.settings().model_copy(update={"intro": "import", "pronounce": {"texttohandwriting.com": "टेक्स्ट टू हैंडराइटिंग"}})
    )
    for path in (FILMED_INTRO, narration_file(0), narration_file(1)):
        run.path(path).parent.mkdir(parents=True, exist_ok=True)
        run.path(path).write_bytes(b"sound")
    heard_as = {
        FILMED_INTRO: script.intro_line,
        narration_file(0): "टेक्स्ट टू हैंडराइटिंग खोलो",  # as respelled: as it should be
        narration_file(1): "पीडीएफ भी डॉनलोड कर लो",
    }
    asked = []

    def transcribe(path: Path, language: str) -> str:
        asked.append((path.relative_to(run.folder).as_posix(), language))
        return heard_as[path.relative_to(run.folder).as_posix()]

    heard = hear(run, transcribe)
    assert asked == [(FILMED_INTRO, "hi"), (narration_file(0), "hi"), (narration_file(1), "hi")]
    assert [item["differences"] for item in heard] == [[], [], [{"said": "डाउनलोड", "heard": "डॉनलोड"}]]
    assert json.loads(run.path("heard.json").read_text()) == heard
    text = report(run, heard)
    assert 'listen: "डाउनलोड" came out as "डॉनलोड"' in text
    assert f"Listen to 1 of 3: {run.path(narration_file(1))}" in text
