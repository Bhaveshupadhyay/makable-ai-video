"""How a posted video did: its numbers on YouTube and Instagram, against your other Shorts and Reels, and where
viewers left it, part by part (YouTube's audience retention over the intro, each scene and the outro).
`python -m shorts insights RUN` fetches them into the run folder, and the review-video skill works out why:

    insights/youtube.json     YouTube Analytics' numbers on the video (views, engaged views, watch time, likes,
                              shares, subscribers), its audience retention, where its views came from, its views day
                              by day, and the same numbers on your Shorts posted in the days before, to compare
    insights/instagram.json   Instagram's on the Reel (views, reach, skip rate, watch time, shares, saves), and your
                              other Reels'

Each has a `summary`: the same few numbers on both platforms, as shares and per 1,000 views, so videos of any
size compare. A Short's views count every play and replay; its engaged views, the plays that went on past the
first moments, and not its loops. So their share (`engaged`) is only a sign of how many swiped away: a Short
watched again and again has a lower one, though no one left. Instagram's skip rate is the share of views that
skipped in the first 3 seconds, so 1 minus it (`stayed`) is how many didn't.
"""

import re
import statistics
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from .platforms import Instagram, PlatformError, YouTube, instagram_code, is_reel, youtube_id

YOUTUBE_METRICS = (
    "views",
    "engagedViews",
    "estimatedMinutesWatched",
    "averageViewDuration",
    "averageViewPercentage",
    "likes",
    "comments",
    "shares",
    "subscribersGained",
    "subscribersLost",
)
YOUTUBE_OTHERS = (  # what the top videos report has of those
    "views",
    "engagedViews",
    "averageViewDuration",
    "averageViewPercentage",
    "likes",
    "comments",
    "shares",
    "subscribersGained",
)
REPORT_BATCH = 200  # videos a report is asked about at once: the most rows it gives
LONGEST_SHORT = 180  # seconds, for telling Shorts apart when YouTube won't
INSTAGRAM_METRICS = (
    "views",
    "reach",
    "likes",
    "comments",
    "shares",
    "saved",
    "total_interactions",
    "reposts",
    "reels_skip_rate",
    "ig_reels_avg_watch_time",  # milliseconds
    "ig_reels_video_view_total_time",
)
HOOK = 3.0  # seconds: the start a viewer decides in


def percent(value: float) -> str:
    return f"{value:.0%}"


# The numbers a summary has, where its platform gives them, and how the report shows them.
SUMMARY: dict[str, tuple[str, Callable[[float], str]]] = {
    "views": ("views", "{:,.0f}".format),
    "reach": ("accounts reached", "{:,.0f}".format),
    "engaged": ("engaged views, of all views (replays count in all)", percent),  # YouTube's
    "stayed": ("didn't skip in the first 3 s", percent),  # Instagram's: 1 - the skip rate
    "watched_seconds": ("watched, on average", "{:.1f} s".format),
    "watched_share": ("  of its length", percent),
    "likes": ("likes per 1k views", "{:.1f}".format),
    "comments": ("comments per 1k views", "{:.1f}".format),
    "shares": ("shares per 1k views", "{:.1f}".format),
    "saves": ("saves per 1k views", "{:.1f}".format),
    "subscribers": ("subscribers per 1k views", "{:.1f}".format),
}

# Where a Short's views come from (YouTube's insightTrafficSourceType), in words.
SOURCES = {
    "SHORTS": "the Shorts feed",
    "YT_SEARCH": "search",
    "SUBSCRIBER": "subscribers' feeds",
    "YT_CHANNEL": "your channel",
    "RELATED_VIDEO": "suggested videos",
    "EXT_URL": "other sites",
    "NO_LINK_OTHER": "direct or unknown",
    "NOTIFICATION": "notifications",
    "HASHTAGS": "hashtag pages",
    "SOUND_PAGE": "sound pages",
    "PLAYLIST": "playlists",
    "YT_OTHER_PAGE": "other YouTube pages",
}


def per_thousand(count: float | None, views: float | None) -> float | None:
    return 1000 * count / views if count is not None and views else None


def share(part: float | None, whole: float | None) -> float | None:
    return part / whole if part is not None and whole else None


def kept(summary: dict[str, float | None]) -> dict[str, float]:
    return {key: value for key, value in summary.items() if value is not None}


def youtube_summary(numbers: dict[str, Any]) -> dict[str, float]:
    views = numbers.get("views")
    viewed = numbers.get("averageViewPercentage")
    return kept(
        {
            "views": views,
            "engaged": share(numbers.get("engagedViews"), views),
            "watched_seconds": numbers.get("averageViewDuration"),
            "watched_share": viewed / 100 if viewed is not None else None,
            "likes": per_thousand(numbers.get("likes"), views),
            "comments": per_thousand(numbers.get("comments"), views),
            "shares": per_thousand(numbers.get("shares"), views),
            "subscribers": per_thousand(numbers.get("subscribersGained"), views),
        }
    )


def instagram_summary(numbers: dict[str, Any], seconds: float | None = None) -> dict[str, float]:
    views = numbers.get("views")
    skipped = numbers.get("reels_skip_rate")  # a percentage
    skipped = skipped / 100 if skipped is not None else None
    watched = numbers.get("ig_reels_avg_watch_time")
    watched = watched / 1000 if watched is not None else None
    return kept(
        {
            "views": views,
            "reach": numbers.get("reach"),
            "stayed": 1 - skipped if skipped is not None else None,
            "watched_seconds": watched,
            "watched_share": share(watched, seconds),
            "likes": per_thousand(numbers.get("likes"), views),
            "comments": per_thousand(numbers.get("comments"), views),
            "shares": per_thousand(numbers.get("shares"), views),
            "saves": per_thousand(numbers.get("saved"), views),
        }
    )


def middle(summaries: list[dict[str, float]]) -> dict[str, float]:
    """The median of each number, over the summaries that have it."""
    keys = {key for summary in summaries for key in summary}
    return {key: statistics.median(summary[key] for summary in summaries if key in summary) for key in keys}


def others(videos: list[dict[str, Any]], days: int) -> dict[str, Any]:
    return {"days": days, "videos": videos, "median": middle([video["summary"] for video in videos])}


def iso_seconds(text: str) -> float | None:
    """Seconds, from an ISO 8601 length such as PT1M2S."""
    found = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?", text or "")
    if not found:
        return None
    days, hours, minutes, seconds = (float(part or 0) for part in found.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# YouTube


def youtube(api: YouTube, link: str, *, days: int = 90, today: date | None = None) -> dict[str, Any]:
    """What YouTube has on a video of yours, from its link or id, and on your Shorts posted in the `days` before
    today, to compare. What it wouldn't give is in `missing`, with what it said."""
    video = youtube_id(link)
    found = api.videos([video])
    if not found:
        raise ValueError(f"YouTube has no video {video} (or it's someone else's, and private)")
    item, today = found[0], today or datetime.now(UTC).date()
    posted = item["snippet"]["publishedAt"]
    window = {"startDate": posted[:10], "endDate": today.isoformat(), "filters": f"video=={video}"}
    missing: dict[str, str] = {}

    def report(what: str, **params: Any) -> list[dict[str, Any]]:
        try:
            return api.report(**window, **params)
        except PlatformError as error:
            missing[what] = str(error)
            return []

    totals = report("numbers", metrics=",".join(YOUTUBE_METRICS))
    retention = report(
        "retention", dimensions="elapsedVideoTimeRatio", metrics="audienceWatchRatio,relativeRetentionPerformance"
    )
    sources = report("sources", dimensions="insightTrafficSourceType", metrics="views,engagedViews", sort="-views")
    daily = report("daily", dimensions="day", metrics="views,engagedViews", sort="day")
    numbers = totals[0] if totals else {}
    if not totals and "numbers" not in missing:
        missing["numbers"] = "none yet: YouTube Analytics has a video's numbers a day or two after it's posted"
    try:
        shorts = [short for short in youtube_shorts(api, days=days, today=today) if short["id"] != video]
    except PlatformError as error:
        shorts, missing["others"] = [], str(error)
    return {
        "platform": "youtube",
        "id": video,
        "link": f"https://youtube.com/shorts/{video}",
        "title": item["snippet"]["title"],
        "posted": posted,
        "fetched": now(),
        "seconds": iso_seconds(item.get("contentDetails", {}).get("duration", "")),
        "public": item.get("statistics", {}),  # what anyone sees, up to now: Analytics' lag a day or two
        "numbers": numbers,
        "summary": youtube_summary(numbers),
        "retention": sorted(retention, key=lambda point: point["elapsedVideoTimeRatio"]),
        "sources": sources,
        "daily": daily,
        "others": others(shorts, days),
        "missing": missing,
    }


def youtube_shorts(api: YouTube, *, days: int = 90, today: date | None = None) -> list[dict[str, Any]]:
    """Your Shorts posted in the last `days`, newest first, with their numbers: all their life's, so they compare."""
    today = today or datetime.now(UTC).date()
    since = (today - timedelta(days=days)).isoformat()
    # Your uploads in the window first, then their numbers, a batch at a time: a report of your top videos would
    # leave out a new Short that older videos outrank
    recent = [video["id"] for video in api.uploads(None, since=since)]
    metrics = ",".join(YOUTUBE_OTHERS)
    numbers: dict[str, dict[str, Any]] = {}
    longest = None
    for first in range(0, len(recent), REPORT_BATCH):
        batch = recent[first : first + REPORT_BATCH]
        window = {
            "startDate": since,
            "endDate": today.isoformat(),
            "filters": "video==" + ",".join(batch),
            "sort": "-views",
            "maxResults": len(batch),
        }
        try:
            rows = api.report(dimensions="video,creatorContentType", metrics=metrics, **window)
            numbers |= {row["video"]: row for row in rows if row.get("creatorContentType") == "SHORTS"}
        except PlatformError:  # it won't tell them apart: a Short is a video no longer than one can be
            numbers |= {row["video"]: row for row in api.report(dimensions="video", metrics=metrics, **window)}
            longest = LONGEST_SHORT
    shorts = []
    for item in api.videos(list(numbers)):
        posted, seconds = item["snippet"]["publishedAt"], iso_seconds(item["contentDetails"]["duration"])
        if posted[:10] < since or (longest and (seconds is None or seconds > longest)):
            continue  # posted before: these are only part of its life's numbers
        row = {key: value for key, value in numbers[item["id"]].items() if key not in ("video", "creatorContentType")}
        shorts.append(
            {
                "id": item["id"],
                "title": item["snippet"]["title"],
                "posted": posted,
                "seconds": seconds,
                "numbers": row,
                "summary": youtube_summary(row),
            }
        )
    return sorted(shorts, key=lambda video: video["posted"], reverse=True)


def find_on_youtube(api: YouTube, title: str) -> str | None:
    """The id of your newest upload with this title, among your 50 newest."""
    wanted = title.strip().casefold()
    return next((video["id"] for video in api.uploads() if video["title"].strip().casefold() == wanted), None)


# Instagram


def instagram(
    api: Instagram, link: str, *, days: int = 90, seconds: float | None = None, today: date | None = None
) -> dict[str, Any]:
    """What Instagram has on a post of yours, from its link, and on your Reels posted in the `days` before today.
    `seconds` is the video's length, if it's known: Instagram doesn't say."""
    post = api.post(instagram_code(link))
    numbers, refused = api.insights(post["id"], list(INSTAGRAM_METRICS))
    missing = dict(refused)
    if not numbers:
        missing["numbers"] = "none yet: Instagram has a post's numbers up to two days after it's posted"
    metrics = [metric for metric in INSTAGRAM_METRICS if metric not in refused]  # what it gives, for the others
    try:
        reels = [
            reel for reel in instagram_reels(api, days=days, today=today, metrics=metrics) if reel["id"] != post["id"]
        ]
    except PlatformError as error:
        reels, missing["others"] = [], str(error)
    return {
        "platform": "instagram",
        "id": post["id"],
        "link": post.get("permalink"),
        "title": title(post),
        "posted": post.get("timestamp"),
        "fetched": now(),
        "seconds": seconds,
        "numbers": numbers,
        "summary": instagram_summary(numbers, seconds),
        "others": others(reels, days),
        "missing": missing,
    }


def title(post: dict[str, Any]) -> str:
    """What a post is called in a report: its caption's first line where Instagram gives it (it doesn't with
    Instagram Login), or its link."""
    caption = (post.get("caption") or "").split("\n")[0][:120]
    return caption or post.get("permalink") or post.get("shortcode") or post.get("id", "")


def instagram_reels(
    api: Instagram, *, days: int = 90, today: date | None = None, metrics: list[str] | None = None, count: int = 25
) -> list[dict[str, Any]]:
    """Your Reels posted in the last `days`, the newest `count` of them, newest first, with their numbers."""
    today = today or datetime.now(UTC).date()
    since = (today - timedelta(days=days)).isoformat()
    reels = []
    for post in api.posts():  # newest first, a page at a time, until there are `count` or they're too old
        if post.get("timestamp", "")[:10] < since:
            break
        if not is_reel(post):
            continue
        numbers, _ = api.insights(post["id"], list(metrics or INSTAGRAM_METRICS))
        reels.append(
            {
                "id": post["id"],
                "title": title(post),
                "posted": post.get("timestamp"),
                "link": post.get("permalink"),
                "numbers": numbers,
                "summary": instagram_summary(numbers),
            }
        )
        if len(reels) == count:
            break
    return reels


# Where viewers left


def watching(retention: list[dict[str, Any]], ratio: float) -> float | None:
    """How many viewers are still watching `ratio` of the way through the video, as a share of its views (YouTube's
    audienceWatchRatio: over 1 where it's watched again). Each of its points is the stretch up to its ratio."""
    for point in retention:
        if ratio < point["elapsedVideoTimeRatio"]:
            return point["audienceWatchRatio"]
    return retention[-1]["audienceWatchRatio"] if retention else None


def stretches(seconds: float) -> list[dict[str, Any]]:
    """The video's stretches, for one whose parts aren't known: its first seconds, then every ten."""
    marks = [0.0, HOOK, *range(10, int(seconds), 10), seconds]
    return [
        {"part": f"{start:.0f}-{end:.0f} s", "start": start, "end": end}
        for start, end in zip(marks, marks[1:], strict=False)
        if end > start
    ]


def by_part(retention: list[dict[str, Any]], parts: list[dict[str, Any]], seconds: float) -> list[dict[str, Any]]:
    """Each part of the video (the intro, each scene, the outro, as `stages.assemble.timeline` has them), with how
    many were watching as it started and as it ended, and how fast they left during it."""
    found = []
    for part in parts:
        start, end = part["start"], min(part["end"], seconds)
        if start >= end:
            continue
        first, last = watching(retention, start / seconds), watching(retention, max(start, end - 0.01) / seconds)
        if first is None or last is None:
            continue
        found.append({**part, "from": first, "to": last, "lost_per_second": (first - last) / (end - start)})
    return found


# The report


def table(summary: dict[str, float], median: dict[str, float], count: int) -> list[str]:
    lines = [f"  {'':26}{'this one':>12}{'your median':>13}" if count else f"  {'':26}{'this one':>12}"]
    for key, (label, shown) in SUMMARY.items():
        if key in summary or key in median:
            mine = shown(summary[key]) if key in summary else "-"
            theirs = (shown(median[key]) if key in median else "-") if count else ""
            lines.append(f"  {label:26}{mine:>12}{theirs:>13}".rstrip())
    return lines


def report(found: dict[str, Any], parts: list[dict[str, Any]] | None = None, seconds: float | None = None) -> str:
    """What `youtube` or `instagram` found, to read: the video's numbers against the median of your others, where its
    views came from, and, from YouTube's retention, how many were left at each of `parts` (the video's, if known)."""
    platform = "YouTube" if found["platform"] == "youtube" else "Instagram"
    length = seconds or found.get("seconds")
    posted = (found.get("posted") or "")[:10]
    lines = [
        f'{platform}: "{found["title"]}" {found["link"]}, posted {posted}' + (f", {length:.0f} s" if length else "")
    ]
    videos = found["others"]["videos"]
    lines += table(found["summary"], found["others"]["median"], len(videos))
    if videos:
        everyone = [*(video["summary"].get("views", 0) for video in videos), found["summary"].get("views", 0)]
        rank = sorted(everyone, reverse=True).index(found["summary"].get("views", 0)) + 1
        kind = "Shorts" if found["platform"] == "youtube" else "Reels"
        lines.append(
            f"  (your median: your {len(videos)} other {kind} posted in the {found['others']['days']} days before. "
            f"By views, this is {rank} of {len(videos) + 1})"
        )
    sources = found.get("sources") or []
    total = sum(source["views"] for source in sources)
    if total:
        said = [
            f"{SOURCES.get(s['insightTrafficSourceType'], s['insightTrafficSourceType'].lower())} {s['views'] / total:.0%}"
            for s in sources[:5]
        ]
        lines.append(f"Where its views came from: {', '.join(said)}")
    daily = [day["views"] for day in found.get("daily") or []]
    if daily:
        lines.append(
            f"Views a day since it was posted: {', '.join(f'{views:,}' for views in daily[:14])}"
            + (" …" if len(daily) > 14 else "")
        )
    retention = found.get("retention") or []
    if retention and length:
        hook = watching(retention, min(HOOK / length, 1.0))
        rows = by_part(retention, parts or stretches(length), length)
        lines.append(
            f"Still watching (YouTube's audience retention): {hook:.0%} after {HOOK:.0f} s, {watching(retention, 1.0):.0%} at the end"
        )
        steepest = max(rows, key=lambda row: row["lost_per_second"], default=None)
        for row in rows:
            mark = "  <- the steepest" if row is steepest and row["lost_per_second"] > 0 else ""
            what = f'  "{row["said"]}"' if row.get("said") else ""
            lines.append(
                f"  {row['part']:10}{row['start']:5.1f}-{row['end']:5.1f} s  {row['from']:4.0%} -> {row['to']:4.0%}"
                f"  ({100 * row['lost_per_second']:.1f} points a second){mark}{what}"
            )
    for what, why in found.get("missing", {}).items():
        lines.append(f"Not given: {what}: {why}")
    return "\n".join(lines)


def listing(videos: list[dict[str, Any]]) -> str:
    """Your Shorts or Reels, a line each, with their main numbers."""
    lines = []
    for video in videos:
        summary = video["summary"]
        numbers = [
            f"{summary['views']:>9,.0f} views" if "views" in summary else f"{'':15}",
            f"{summary['stayed']:4.0%} stayed"
            if "stayed" in summary
            else f"{summary['engaged']:4.0%} engaged"
            if "engaged" in summary
            else f"{'':12}",
            f"{summary['watched_share']:4.0%} watched" if "watched_share" in summary else f"{'':12}",
            f"{summary['likes']:5.1f} likes/1k" if "likes" in summary else f"{'':14}",
        ]
        lines.append(f"{(video.get('posted') or '')[:10]}  {video['id']:<20}{'  '.join(numbers)}  {video['title']}")
    return "\n".join(lines) or "(none)"
