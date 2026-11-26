"""How a posted video did: connecting YouTube and Instagram, their numbers, and where viewers left it."""

import json
import os
import threading
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from shorts.home import account, keep_account
from shorts.run import Run

httpx = pytest.importorskip("httpx")

from shorts.insights import by_part, instagram, report, youtube, youtube_shorts  # noqa: E402  (they need httpx)
from shorts.platforms import (  # noqa: E402
    Instagram,
    PlatformError,
    YouTube,
    connect_instagram,
    connect_youtube,
    instagram_code,
    instagram_token,
    youtube_id,
    youtube_token,
)

TODAY = date(2026, 10, 31)


def test_a_video_is_found_from_any_of_its_links() -> None:
    for link in (
        "https://youtube.com/shorts/dQw4w9WgXcQ?feature=share",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=3",
        "youtu.be/dQw4w9WgXcQ",
        "https://m.youtube.com/shorts/dQw4w9WgXcQ",
        "dQw4w9WgXcQ",
    ):
        assert youtube_id(link) == "dQw4w9WgXcQ"
    for link in ("https://www.instagram.com/reel/C9xYz_1-ab/", "instagram.com/maker/reel/C9xYz_1-ab", "C9xYz_1-ab"):
        assert instagram_code(link) == "C9xYz_1-ab"
    with pytest.raises(ValueError, match="isn't a YouTube video's link"):
        youtube_id("https://example.com/shorts/dQw4w9WgXcQ")
    with pytest.raises(ValueError, match="isn't an Instagram post's link"):
        instagram_code("https://www.instagram.com/maker/")


def retention_at(ratio: float) -> float:
    """Most leave in the first tenth (the intro), then a few at a time."""
    return 1 - 4 * ratio if ratio <= 0.1 else 0.6 - (ratio - 0.1) * 0.2 / 0.9


VIDEOS = {  # id: (posted, length)
    "aaaaaaaaaaa": ("2026-10-20T10:00:00Z", "PT40S"),  # the video
    "bbbbbbbbbbb": ("2026-09-01T10:00:00Z", "PT55S"),  # another Short
    "ccccccccccc": ("2026-01-01T10:00:00Z", "PT30S"),  # posted before the window
    "ddddddddddd": ("2026-10-01T10:00:00Z", "PT12M"),  # a long video
}


class FakeYouTube:
    """A stand-in for Google's OAuth and YouTube's Data and Analytics APIs, for the channel that has VIDEOS."""

    def __init__(self, *, retention: bool = True, refresh: str = "access-2") -> None:
        self.asked: list[httpx.Request] = []
        self.retention = retention
        self.refresh = refresh

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        url, query = request.url, dict(request.url.params)
        if url.host == "oauth2.googleapis.com":
            form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
            if form["grant_type"] == "authorization_code":
                return httpx.Response(200, json={"access_token": "access-1", "refresh_token": "refresh-1"})
            if self.refresh == "invalid_grant":
                return httpx.Response(400, json={"error": "invalid_grant", "error_description": "Token expired"})
            return httpx.Response(200, json={"access_token": self.refresh})
        if url.path == "/youtube/v3/channels":
            uploads = {"relatedPlaylists": {"uploads": "UU1"}}
            return httpx.Response(
                200, json={"items": [{"id": "UC1", "snippet": {"title": "Maker"}, "contentDetails": uploads}]}
            )
        if url.path == "/youtube/v3/playlistItems":
            items = [
                {"snippet": {"title": title}, "contentDetails": {"videoId": video, "videoPublishedAt": "2026-10-20"}}
                for video, title in (("aaaaaaaaaaa", "A store in 60 seconds"), ("bbbbbbbbbbb", "Another"))
            ]
            return httpx.Response(200, json={"items": items})
        if url.path == "/youtube/v3/videos":
            items = [
                {
                    "id": video,
                    "snippet": {"title": f"Video {video[0]}", "publishedAt": VIDEOS[video][0]},
                    "contentDetails": {"duration": VIDEOS[video][1]},
                    "statistics": {"viewCount": "1500"},
                }
                for video in query["id"].split(",")
                if video in VIDEOS
            ]
            return httpx.Response(200, json={"items": items})
        if url.host == "youtubeanalytics.googleapis.com":
            assert query["ids"] == "channel==MINE"
            return self.report(query)
        return httpx.Response(404, json={"error": {"message": "no such path"}})

    def report(self, query: dict[str, str]) -> httpx.Response:
        dimensions, metrics = query.get("dimensions"), query["metrics"].split(",")
        if dimensions is None:
            assert query["filters"] == "video==aaaaaaaaaaa" and query["startDate"] == "2026-10-20"
            numbers = {"views": 1000, "engagedViews": 600, "averageViewDuration": 14.0, "averageViewPercentage": 35.0}
            numbers |= {"likes": 30, "comments": 4, "shares": 5, "subscribersGained": 2}
            return table([], metrics, [[numbers.get(metric, 0) for metric in metrics]])
        if dimensions == "elapsedVideoTimeRatio":
            if not self.retention:
                return httpx.Response(400, json={"error": {"message": "The query is not supported."}})
            rows = [[n / 100, round(retention_at(n / 100), 4), 0.4] for n in range(1, 101)]
            return table([dimensions], metrics, rows)
        if dimensions == "insightTrafficSourceType":
            return table([dimensions], metrics, [["SHORTS", 900, 540], ["YT_SEARCH", 100, 60]])
        if dimensions == "day":
            return table([dimensions], metrics, [["2026-10-20", 700, 420], ["2026-10-21", 300, 180]])
        if dimensions == "video,creatorContentType":
            assert query["sort"] == "-views" and int(query["maxResults"]) <= 200
            rows = [
                ["aaaaaaaaaaa", "SHORTS", 1000, 600, 14.0, 35.0, 30, 4, 5, 2],
                ["bbbbbbbbbbb", "SHORTS", 4000, 3200, 33.0, 60.0, 200, 20, 40, 10],
                ["ccccccccccc", "SHORTS", 50, 20, 9.0, 30.0, 1, 0, 0, 0],
                ["ddddddddddd", "VIDEO_ON_DEMAND", 900, 900, 300.0, 40.0, 50, 9, 3, 4],
            ]
            return table(["video", "creatorContentType"], metrics, rows)
        return httpx.Response(400, json={"error": {"message": "The query is not supported."}})


def table(dimensions: list[str], metrics: list[str], rows: list[list]) -> httpx.Response:
    headers = [{"name": name, "columnType": "DIMENSION"} for name in dimensions]
    headers += [{"name": name, "columnType": "METRIC"} for name in metrics]
    return httpx.Response(200, json={"kind": "youtubeAnalytics#resultTable", "columnHeaders": headers, "rows": rows})


def client(fake) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(fake))


@pytest.fixture
def oauth_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "client-1")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "secret-1")
    monkeypatch.delenv("YOUTUBE_REFRESH_TOKEN", raising=False)


def answer_consent(code: str = "the-code"):
    """A browser that, shown Google's consent page, is sent back with a code, after asking for a favicon."""

    def browse(page: str) -> None:
        asked = {key: values[0] for key, values in parse_qs(urlsplit(page).query).items()}
        assert asked["code_challenge_method"] == "S256" and asked["access_type"] == "offline"
        assert "yt-analytics.readonly" in asked["scope"]

        def back() -> None:
            assert httpx.get(f"{asked['redirect_uri']}favicon.ico").status_code == 404
            got = httpx.get(asked["redirect_uri"], params={"state": asked["state"], "code": code})
            assert "Connected" in got.text

        threading.Thread(target=back, daemon=True).start()

    return browse


def test_connecting_youtube_keeps_a_refresh_token_only_you_can_read(oauth_client: None) -> None:
    fake = FakeYouTube()
    kept = connect_youtube(browse=answer_consent(), client=client(fake), wait=10)
    assert kept == {"client_id": "client-1", "refresh_token": "refresh-1", "channel": "UC1", "title": "Maker"}
    assert account("youtube") == kept
    file = Path(os.environ["SHORTS_HOME"]) / "accounts" / "youtube.json"
    assert file.stat().st_mode & 0o777 == 0o600
    swapped = parse_qs(next(r for r in fake.asked if r.url.host == "oauth2.googleapis.com").content.decode())
    assert swapped["code"] == ["the-code"] and swapped["code_verifier"][0]  # with PKCE

    assert youtube_token(client=client(FakeYouTube())) == "access-2"
    with pytest.raises(PlatformError, match="connect youtube"):
        youtube_token(client=client(FakeYouTube(refresh="invalid_grant")))


def test_youtube_needs_your_own_oauth_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "")
    keep_account("youtube", {"client_id": "client-1", "refresh_token": "r"})
    with pytest.raises(ValueError, match="YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET"):
        youtube_token()


def test_a_videos_numbers_against_your_other_shorts() -> None:
    api = YouTube("access-1", client=client(FakeYouTube()))
    found = youtube(api, "https://youtube.com/shorts/aaaaaaaaaaa", days=90, today=TODAY)
    assert (found["id"], found["seconds"], found["posted"][:10]) == ("aaaaaaaaaaa", 40.0, "2026-10-20")
    assert found["summary"] == {
        "views": 1000,
        "stayed": 0.6,
        "watched_seconds": 14.0,
        "watched_share": 0.35,
        "likes": 30.0,
        "comments": 4.0,
        "shares": 5.0,
        "subscribers": 2.0,
    }
    # Only the other Shorts posted in the window: not this one, an older one, or a long video.
    assert [video["id"] for video in found["others"]["videos"]] == ["bbbbbbbbbbb"]
    assert found["others"]["median"]["stayed"] == 0.8
    assert len(found["retention"]) == 100 and found["missing"] == {}
    assert found["sources"][0]["insightTrafficSourceType"] == "SHORTS"
    assert [video["id"] for video in youtube_shorts(api, days=365, today=TODAY)] == [
        "aaaaaaaaaaa",
        "bbbbbbbbbbb",
        "ccccccccccc",
    ]


def test_where_viewers_left_part_by_part() -> None:
    found = youtube(YouTube("access-1", client=client(FakeYouTube())), "aaaaaaaaaaa", today=TODAY)
    parts = [
        {"part": "intro", "start": 0.0, "end": 10.0, "said": "Watch me build a store."},
        {"part": "scene 1", "start": 10.0, "end": 25.0, "said": "Type what you sell."},
        {"part": "scene 2", "start": 25.0, "end": 40.0, "said": "And it's live."},
    ]
    rows = by_part(found["retention"], parts, 40.0)
    assert [row["part"] for row in rows] == ["intro", "scene 1", "scene 2"]
    assert rows[0]["from"] == pytest.approx(0.96) and rows[0]["to"] == pytest.approx(retention_at(0.25), abs=0.01)
    assert max(rows, key=lambda row: row["lost_per_second"])["part"] == "intro"

    text = report(found, parts, 40.0)
    assert "didn't swipe away" in text and "60%" in text and "80%" in text  # this one, and the median
    assert "the Shorts feed 90%, search 10%" in text
    assert "intro" in text.split("<- the steepest")[0].splitlines()[-1]
    assert '"Watch me build a store."' in text
    # Without the video's parts, its first seconds and every ten after.
    assert "0-3 s" in report(found)


def test_what_youtube_wont_give_is_said_and_the_rest_is_kept() -> None:
    found = youtube(YouTube("access-1", client=client(FakeYouTube(retention=False))), "aaaaaaaaaaa", today=TODAY)
    assert found["retention"] == [] and "not supported" in found["missing"]["retention"]
    assert found["summary"]["views"] == 1000
    assert "Not given: retention" in report(found)


class FakeInstagram:
    """A stand-in for the Instagram API with Instagram Login: two pages of posts, and insights that won't give
    `reposts` (so asking for it with the others fails them all)."""

    def __init__(self) -> None:
        self.asked: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        path, query = request.url.path, dict(request.url.params)
        assert query.get("access_token"), "every request carries the token"
        if path == "/refresh_access_token":
            return httpx.Response(200, json={"access_token": "renewed", "expires_in": 5184000})
        if path == "/v26.0/me":
            return httpx.Response(200, json={"user_id": "17", "username": "maker"})
        if path == "/v26.0/me/media":
            first = {
                "id": "1",
                "shortcode": "OTHER",
                "media_product_type": "REELS",
                "timestamp": "2026-10-01T09:00:00+0000",
            }
            target = {
                "id": "2",
                "shortcode": "C9xYz_1-ab",
                "media_product_type": "REELS",
                "timestamp": "2026-10-25T09:00:00+0000",
            }
            target["permalink"], target["caption"] = "https://www.instagram.com/reel/C9xYz_1-ab/", "A store\n#build"
            if query.get("after") == "page-2":
                return httpx.Response(200, json={"data": [target]})
            paging = {"cursors": {"after": "page-2"}, "next": "https://graph.instagram.com/next"}
            return httpx.Response(200, json={"data": [first], "paging": paging})
        if path.endswith("/insights"):
            metrics = query["metric"].split(",")
            if "reposts" in metrics:
                return httpx.Response(400, json={"error": {"message": "(#100) metric[7] must be one of ..."}})
            values = {"views": 2000, "reach": 1500, "likes": 80, "comments": 6, "shares": 10, "saved": 12}
            values |= {"reels_skip_rate": 45.0, "ig_reels_avg_watch_time": 9500}
            data = [{"name": metric, "values": [{"value": values[metric]}]} for metric in metrics if metric in values]
            return httpx.Response(200, json={"data": data})
        return httpx.Response(404, json={"error": {"message": "no such path"}})


def test_a_reels_numbers_against_your_other_reels() -> None:
    fake = FakeInstagram()
    api = Instagram("token-1", client=client(fake))
    found = instagram(api, "https://www.instagram.com/reel/C9xYz_1-ab/", seconds=38.0, today=TODAY)
    assert (found["id"], found["title"]) == ("2", "A store")
    assert found["summary"]["stayed"] == pytest.approx(0.55)  # a 45% skip rate
    assert found["summary"]["watched_seconds"] == 9.5  # from milliseconds
    assert found["summary"]["watched_share"] == pytest.approx(9.5 / 38)
    assert found["summary"]["saves"] == 6.0
    assert "reposts" in found["missing"] and "total_interactions" not in found["missing"]
    assert [reel["id"] for reel in found["others"]["videos"]] == ["1"]
    asked = [r.url.params["metric"] for r in fake.asked if r.url.path == "/v26.0/1/insights"]
    assert len(asked) == 1 and "reposts" not in asked[0].split(",")  # once, without what it wouldn't give
    assert "Instagram" in report(found) and "didn't swipe away" in report(found)


def test_instagrams_token_is_kept_and_renewed_once_its_a_week_old(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "from-the-dashboard")
    start = datetime(2026, 10, 1, tzinfo=UTC)
    assert instagram_token() == "from-the-dashboard"  # nothing kept yet: the environment's
    kept = connect_instagram(client=client(FakeInstagram()), now=start)
    assert (kept["token"], kept["username"]) == ("renewed", "maker")

    keep_account("instagram", {**kept, "token": "kept"})
    assert instagram_token(client=client(FakeInstagram()), now=start + timedelta(days=2)) == "kept"
    assert instagram_token(client=client(FakeInstagram()), now=start + timedelta(days=8)) == "renewed"
    assert account("instagram")["renewed"] == (start + timedelta(days=8)).isoformat()


def test_insights_finds_the_video_by_its_title_and_keeps_what_it_fetched(
    run: Run, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    from shorts.__main__ import main

    parts = [
        {"part": "intro", "start": 0.0, "end": 10.0, "said": "Hi."},
        {"part": "scene 1", "start": 10.0, "end": 40.0, "said": "Look."},
    ]
    run.path("metadata.json").write_text(
        json.dumps({"title": "A store in 60 seconds", "seconds": 40.0, "parts": parts})
    )
    monkeypatch.setattr(YouTube, "connected", classmethod(lambda cls: cls("access-1", client=client(FakeYouTube()))))
    monkeypatch.setattr("sys.argv", ["shorts", "insights", str(run.folder)])
    main()
    kept = json.loads(run.path("insights/youtube.json").read_text())
    assert kept["id"] == "aaaaaaaaaaa"
    out = capsys.readouterr().out
    assert "<- the steepest" in out and '"Hi."' in out

    monkeypatch.setattr("sys.argv", ["shorts", "insights", str(run.folder), "--days", "30"])
    main()  # again: the same video, from what's kept
    assert json.loads(run.path("insights/youtube.json").read_text())["others"]["days"] == 30
