"""What's trending on YouTube Shorts, for a "useful website" Short: the outliers among the Shorts a search finds, and
the websites they name. And the log of the sites made already (SHORTS_HOME's topics.json), so no site is made twice.

    python -m shorts trends [QUERY ...] [--days 14] [--region IN] [--language hi]
    python -m shorts topics [--add SITE --about WORDS --run RUN | --remove SITE]

`trends` searches YouTube (the Data API v3's search.list: Shorts posted in the last `--days`, most viewed first, in
the region and the language), then looks up each video's numbers (videos.list) and its channel's subscribers
(channels.list). It ranks them by how far each outruns its channel and its age: its views over the channel's
subscribers, times its views a day. A Short with ten times its channel's subscribers in views, posted yesterday, is
riding its topic, not its channel: that's a topic to make.

The key is YOUTUBE_API_KEY, an API key from a Google Cloud project with the YouTube Data API v3 on (`keys --trends`
adds its line to SHORTS_HOME's .env). It's sent in a header, never in an address, so no error message has it. YouTube
gives a key 10,000 units a day, and a search costs 100 (a lookup of 50 videos or channels, 1), so a day's searches
are kept (SHORTS_HOME's trends/<date>.json) and the same search again that day costs nothing, unless --fresh.
"""

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import COMMAND
from .home import home

YOUTUBE = "https://www.googleapis.com/youtube/v3"
QUERIES = ("useful website", "website for students", "amazing website")  # when trends is given none
DAILY_UNITS = 10_000  # what YouTube gives a key a day
COSTS = {"search": 100, "videos": 1, "channels": 1}  # units a request
QUOTA_DAY = ZoneInfo("America/Los_Angeles")  # YouTube's quota starts again at midnight Pacific time
LONGEST_SHORT = 180  # seconds: search's "short" is anything under 4 minutes
SETUP = (
    "an API key from console.cloud.google.com (APIs and services, Credentials, Create credentials, API key), in a "
    "project with the YouTube Data API v3 on (APIs and services, Library)"
)

# Hosts that a description links to that aren't the website a Short is about: the channel's socials, stores,
# shorteners, and YouTube and Google themselves.
NOT_SITES = {
    "youtube.com", "youtu.be", "instagram.com", "facebook.com", "fb.com", "twitter.com", "x.com", "t.me",
    "telegram.me", "telegram.org", "whatsapp.com", "wa.me", "bit.ly", "linktr.ee", "amzn.to", "amazon.in",
    "amazon.com", "google.com", "play.google.com", "apps.apple.com", "gmail.com", "threads.net", "linkedin.com",
    "discord.gg", "discord.com", "snapchat.com", "pinterest.com", "spotify.com", "tiktok.com", "goo.gl", "tinyurl.com",
    "flipkart.com", "github.com", "medium.com", "reddit.com", "blogspot.com", "wikipedia.org",
}  # fmt: skip
DOMAIN = re.compile(
    r"(?<![@\w.-])(?:https?://)?(?:www\.)?((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+"
    r"(?:com|in|io|ai|org|net|app|co|me|tech|xyz|dev|site|online|tools|tool|pro|so|cc|info|link|page|live|fun|"
    r"space|website|store|club|[a-z]{2}))(?![\w-])",  # and any country's: remove.bg, notion.so
    re.IGNORECASE,
)


class YouTubeError(RuntimeError):
    """YouTube said no, or couldn't be reached. Its message never has the key."""


def api_key() -> str:
    key = os.environ.get("YOUTUBE_API_KEY", "")
    if not key:
        raise ValueError(f"Set YOUTUBE_API_KEY: {SETUP}. `{COMMAND} keys --open --trends` adds its line to your .env")
    return key


def said(response: Any) -> str:
    """What YouTube's error answer means, in words: its reason, for the ones that need you to do something."""
    try:
        error = response.json().get("error", {})
    except ValueError:
        return response.text[:300]
    reasons = {item.get("reason") for item in error.get("errors", []) if isinstance(item, dict)}
    reasons |= {item.get("reason") for item in error.get("details", []) if isinstance(item, dict)}
    if reasons & {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"}:
        return (
            f"the key's quota for today is used up ({DAILY_UNITS:,} units a day; a search is {COSTS['search']}): "
            "it starts again at midnight Pacific time"
        )
    if reasons & {"keyInvalid", "API_KEY_INVALID", "badRequest"} and "API key not valid" in str(error.get("message")):
        return "YOUTUBE_API_KEY isn't a key Google knows: copy it again from the Credentials page"
    if reasons & {"accessNotConfigured", "SERVICE_DISABLED"}:
        return "the YouTube Data API v3 isn't on in the key's project: turn it on (APIs and services, Library)"
    if reasons & {"API_KEY_SERVICE_BLOCKED", "forbidden"}:
        return "the key isn't allowed to use the YouTube Data API v3: allow it in the key's API restrictions"
    return str(error.get("message") or error)[:300]


class YouTubeData:
    """YouTube's Data API v3 with an API key: public numbers only, no sign-in. Counts the units it spends."""

    def __init__(self, key: str, *, client: Any = None) -> None:
        import httpx

        self.http = client or httpx.Client(timeout=60)
        self.http.headers["X-Goog-Api-Key"] = key  # not in the address, where an error message could show it
        self.units = 0

    def get(self, what: str, **params: Any) -> dict[str, Any]:
        import httpx

        try:
            response = self.http.get(f"{YOUTUBE}/{what}", params=params)
        except httpx.TransportError as error:
            raise YouTubeError(f"couldn't reach YouTube ({type(error).__name__})") from None
        self.units += COSTS[what]
        if response.is_error:
            raise YouTubeError(f"YouTube answered {response.status_code} to {what}: {said(response)}")
        return response.json()

    def search(self, query: str, after: datetime, region: str, language: str, count: int) -> list[str]:
        """The ids of the Shorts `query` finds, posted after `after`, most viewed first."""
        found = self.get(
            "search",
            part="snippet",
            q=query,
            type="video",
            videoDuration="short",
            publishedAfter=after.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            order="viewCount",
            regionCode=region,
            relevanceLanguage=language,
            maxResults=min(count, 50),
        )
        return [item["id"]["videoId"] for item in found.get("items", []) if item.get("id", {}).get("videoId")]

    def lookup(self, what: str, ids: list[str], part: str) -> list[dict[str, Any]]:
        """videos.list or channels.list, 50 at a time."""
        items: list[dict[str, Any]] = []
        for first in range(0, len(ids), 50):
            items += self.get(what, part=part, id=",".join(ids[first : first + 50]), maxResults=50).get("items", [])
        return items


def iso_seconds(text: str) -> float | None:
    """An ISO 8601 length (PT1M5S) in seconds."""
    found = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?", text or "")
    if not found:
        return None
    days, hours, minutes, seconds = (float(part or 0) for part in found.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def sites_in(text: str) -> list[str]:
    """The websites a text names (texttohandwriting.com, www.ilovepdf.com/...), without socials and shorteners."""
    found: list[str] = []
    for match in DOMAIN.finditer(text):
        site = match[1].lower().removeprefix("www.")
        if site not in NOT_SITES and not any(site.endswith(f".{other}") for other in NOT_SITES) and site not in found:
            found.append(site)
    return found


def squashed(text: str) -> str:
    """Letters (with their marks: Devanagari's vowel signs) and digits only, lower case: "Text To Handwriting" and
    "texttohandwriting.com" both have "texttohandwriting" in them."""
    return "".join(letter for letter in text.lower() if unicodedata.category(letter)[0] in "LMN")


@dataclass
class Trend:
    """A Short a search found, with its numbers and its channel's."""

    id: str
    title: str
    channel: str
    published: datetime
    views: int
    subscribers: int | None  # None: the channel hides them
    likes: int | None = None
    comments: int | None = None
    seconds: float | None = None
    description: str = ""
    tags: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)  # the searches that found it
    made: str | None = None  # the site in the topics log it's about, if it's one made already

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/shorts/{self.id}"

    def days(self, now: datetime) -> float:
        """How long it's been up, in days (half a day at least, so a Short an hour old doesn't top them all)."""
        return max((now - self.published).total_seconds() / 86400, 0.5)

    def per_day(self, now: datetime) -> float:
        return self.views / self.days(now)

    @property
    def ratio(self) -> float | None:
        """Its views over its channel's subscribers (None: they're hidden)."""
        return self.views / max(self.subscribers, 1) if self.subscribers is not None else None

    def score(self, now: datetime) -> float:
        """How far it outruns its channel and its age: its views over its subscribers, times its views a day. A
        channel that hides its subscribers counts as one with as many as the video has views."""
        return (self.ratio if self.ratio is not None else 1.0) * self.per_day(now)

    @property
    def sites(self) -> list[str]:
        return sites_in(f"{self.title}\n{self.description}")

    def summary(self, now: datetime) -> dict[str, Any]:
        """What `trends --json` prints about it."""
        return {
            "url": self.url,
            "title": self.title,
            "channel": self.channel,
            "subscribers": self.subscribers,
            "views": self.views,
            "views_per_day": round(self.per_day(now)),
            "views_per_subscriber": round(self.ratio, 2) if self.ratio is not None else None,
            "days": round(self.days(now), 1),
            "seconds": self.seconds,
            "likes": self.likes,
            "comments": self.comments,
            "sites": self.sites,
            "made": self.made,
            "found_by": self.queries,
            "tags": self.tags,
            "description": self.description,
        }


def trend(video: dict[str, Any], channels: dict[str, dict[str, Any]]) -> Trend:
    """A Trend from videos.list's item and channels.list's, by id."""
    snippet, numbers = video.get("snippet", {}), video.get("statistics", {})
    channel = channels.get(snippet.get("channelId", ""), {}).get("statistics", {})
    hidden = channel.get("hiddenSubscriberCount") or "subscriberCount" not in channel

    def count(value: Any) -> int | None:
        return int(value) if value is not None else None

    return Trend(
        id=video["id"],
        title=snippet.get("title", ""),
        channel=snippet.get("channelTitle", ""),
        published=datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00")),
        views=int(numbers.get("viewCount", 0)),
        subscribers=None if hidden else int(channel["subscriberCount"]),
        likes=count(numbers.get("likeCount")),
        comments=count(numbers.get("commentCount")),
        seconds=iso_seconds(video.get("contentDetails", {}).get("duration", "")),
        description=snippet.get("description", ""),
        tags=snippet.get("tags", []),
    )


# The log of the sites made already, and the day's searches.


def topics_file() -> Path:
    return home() / "topics.json"


def made_sites() -> list[dict[str, Any]]:
    """The topics log: each site made already, {site, about, run, made}, oldest first."""
    file = topics_file()
    return json.loads(file.read_text()).get("sites", []) if file.exists() else []


def _save_topics(sites: list[dict[str, Any]]) -> None:
    file = topics_file()
    file.parent.mkdir(parents=True, exist_ok=True)
    part = file.with_name(f".{file.name}.part")  # first, so a failed write loses nothing
    part.write_text(json.dumps({"sites": sites}, indent=1, ensure_ascii=False) + "\n")
    part.replace(file)


def site_name(site: str) -> str:
    """A site as the log keeps it: its host, without www. or a path ("texttohandwriting.com")."""
    found = sites_in(site) or [site.strip().lower()]
    return found[0].removeprefix("www.").split("/")[0]


def log_site(site: str, *, about: str = "", run: str = "", today: date | None = None) -> dict[str, Any]:
    """Adds a site to the topics log (or updates its entry), so trends marks Shorts about it as made."""
    entry = {"site": site_name(site), "about": about, "run": run, "made": (today or date.today()).isoformat()}
    sites = [old for old in made_sites() if old["site"] != entry["site"]]
    _save_topics([*sites, entry])
    return entry


def forget_site(site: str) -> bool:
    """Takes a site out of the topics log. Returns whether it was in it."""
    sites = made_sites()
    kept = [old for old in sites if old["site"] != site_name(site)]
    _save_topics(kept)
    return len(kept) != len(sites)


def made_already(text: str, sites: list[dict[str, Any]]) -> str | None:
    """The site in the log a Short is about, if its title, description or tags name it: by its host, its name
    without the ending ("texttohandwriting"), or the words it's about ("text to handwriting")."""
    text = squashed(text)
    for entry in sites:
        names = [entry["site"], entry["site"].rsplit(".", 1)[0], *filter(None, entry.get("about", "").split(","))]
        if any(len(squashed(name)) >= 5 and squashed(name) in text for name in names):
            return entry["site"]
    return None


def searches_file(day: date) -> Path:
    return home() / "trends" / f"{day.isoformat()}.json"


def _searches(day: date) -> dict[str, Any]:
    file = searches_file(day)
    return json.loads(file.read_text()) if file.exists() else {"units": 0, "searches": {}}


def _save_searches(day: date, kept: dict[str, Any]) -> None:
    file = searches_file(day)
    file.parent.mkdir(parents=True, exist_ok=True)
    part = file.with_name(f".{file.name}.part")
    part.write_text(json.dumps(kept, indent=1) + "\n")
    part.replace(file)


@dataclass
class Found:
    """What `trends` found: the Shorts, best first, and what it cost."""

    trends: list[Trend]
    units: int  # spent by this search
    today: int  # spent by trends today (YouTube's day: from midnight Pacific time), this search's too
    kept: int  # searches that were kept from earlier today, and cost nothing


def find(
    queries: list[str],
    *,
    days: int = 14,
    region: str = "IN",
    language: str = "hi",
    count: int = 25,
    fresh: bool = False,
    least_views: int = 10_000,
    api: YouTubeData | None = None,
    now: datetime | None = None,
) -> Found:
    """The Shorts the searches find, posted in the last `days`, with at least `least_views` views, the outliers
    first (`Trend.score`). Each is marked with the site in the topics log it's about, if any.

    Args:
        queries: What to search for: "useful website", "website for students".
        days: How far back to look.
        region: The country whose YouTube to search ("IN").
        language: The language the videos should be in ("hi").
        count: How many Shorts each search returns (at most 50).
        fresh: Search again, even if the same search was made earlier today.
        least_views: Leave out Shorts with fewer views.
        api: YouTube's Data API (a test's); one with YOUTUBE_API_KEY by default.
        now: The time now (a test's).
    """
    now = now or datetime.now(UTC)
    api = api or YouTubeData(api_key())
    day = now.astimezone(QUOTA_DAY).date()
    kept = _searches(day)
    after = now - timedelta(days=days)
    found_by: dict[str, list[str]] = {}
    reused = 0
    try:
        for query in queries:
            key = json.dumps([query.strip().lower(), days, region, language, count])
            if key in kept["searches"] and not fresh:
                ids = kept["searches"][key]
                reused += 1
            else:
                ids = api.search(query, after, region, language, count)
                kept["searches"][key] = ids
            for video in ids:
                found_by.setdefault(video, []).append(query)
        videos = api.lookup("videos", list(found_by), "snippet,statistics,contentDetails")
        channel_ids = sorted({video["snippet"]["channelId"] for video in videos if video.get("snippet")})
        channels = {channel["id"]: channel for channel in api.lookup("channels", channel_ids, "statistics")}
    finally:
        kept["units"] += api.units
        _save_searches(day, kept)
    log = made_sites()
    trends = []
    for video in videos:
        item = trend(video, channels)
        if item.views < least_views or (item.seconds is not None and item.seconds > LONGEST_SHORT):
            continue
        item.queries = found_by.get(item.id, [])
        item.made = made_already(f"{item.title}\n{item.description}\n{' '.join(item.tags)}", log)
        trends.append(item)
    trends.sort(key=lambda item: item.score(now), reverse=True)
    return Found(trends, api.units, kept["units"], reused)


def short_number(value: float | None) -> str:
    """1234567 as 1.2M, 45600 as 45.6k."""
    if value is None:
        return "?"
    for size, letter in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(value) >= size:
            return f"{value / size:.1f}".removesuffix(".0") + letter
    return f"{value:.0f}"


def listing(found: Found, now: datetime | None = None, top: int = 20) -> str:
    """What `trends` prints: each Short, best first, then what it cost."""
    now = now or datetime.now(UTC)
    lines = []
    for rank, item in enumerate(found.trends[:top], 1):
        ratio = f"{item.ratio:.1f}x its subscribers" if item.ratio is not None else "subscribers hidden"
        subscribers = f"{short_number(item.subscribers)} subscribers" if item.subscribers is not None else "hidden"
        lines += [
            f"{rank:2}. {item.title}",
            f"    {item.url}",
            f"    {short_number(item.views)} views in {item.days(now):.0f} days ({short_number(item.per_day(now))} a "
            f"day, {ratio}), {item.channel} ({subscribers})",
        ]
        if item.sites:
            lines.append(f"    names: {', '.join(item.sites)}")
        if item.made:
            lines.append(f"    made already: {item.made} (the topics log)")
    if not found.trends:
        lines.append("No Shorts found: try other words, or more --days")
    lines.append(
        f"YouTube quota: {found.units} units for this ({found.kept} searches kept from earlier today, free), "
        f"{found.today:,} of {DAILY_UNITS:,} by trends today"
    )
    return "\n".join(lines)
