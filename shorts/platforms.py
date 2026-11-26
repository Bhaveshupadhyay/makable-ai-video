"""Where your videos are posted, YouTube and Instagram: connecting your accounts, once, and their APIs, for the
numbers on what you've posted (`shorts.insights`).

    youtube     YouTube's Analytics and Data APIs, through an OAuth client of your own: a Desktop app's, made in
                Google Cloud's console (YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET). `python -m shorts connect
                youtube` opens Google's consent page in the browser, and keeps the refresh token it gives in
                SHORTS_HOME (accounts/youtube.json): it's all the commands after need. Where none is kept (GitHub
                Actions), YOUTUBE_REFRESH_TOKEN.
    instagram   The Instagram API with Instagram Login, for a professional account (Business or Creator): a token
                from your Meta app's dashboard (INSTAGRAM_ACCESS_TOKEN). It lasts 60 days, so `connect instagram`
                keeps it (accounts/instagram.json), and it's renewed when it's used once it's a week old: used
                at least every 60 days, it never runs out. Where none is kept, INSTAGRAM_ACCESS_TOKEN, as it is.

What goes wrong is said without the token. Needs httpx.
"""

import base64
import contextlib
import hashlib
import http.server
import itertools
import os
import re
import secrets
import time
import webbrowser
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from . import COMMAND
from .home import account, keep_account

PLATFORMS = ("youtube", "instagram")
SETUP = "the README's How your videos did"

GOOGLE_CONSENT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
YOUTUBE_SCOPES = (
    "https://www.googleapis.com/auth/yt-analytics.readonly",  # the numbers
    "https://www.googleapis.com/auth/youtube.readonly",  # the videos themselves: the Analytics API wants it too
)
YOUTUBE_DATA = "https://www.googleapis.com/youtube/v3"
YOUTUBE_ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
CONSENT_WAIT = 300  # seconds to wait for Google's consent page to answer

INSTAGRAM = "https://graph.instagram.com"
INSTAGRAM_VERSION = "v26.0"
# What Instagram Login gives on a post: caption and media_product_type are for Facebook Login only
INSTAGRAM_MEDIA = "id,media_type,permalink,shortcode,timestamp,like_count,comments_count"
RENEW = timedelta(days=7)  # how old Instagram's token gets before it's renewed: it lasts 60 days, and must be a day old


class PlatformError(RuntimeError):
    """A platform said no, or couldn't be reached."""


def said(response: httpx.Response) -> str:
    """What an error answer says: Google's and Meta's {"error": {"message": ...}}, OAuth's {"error": "invalid_grant",
    "error_description": ...}, or the text."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error)[:300]
    if isinstance(error, str):
        return f"{error} ({body['error_description']})" if body.get("error_description") else error
    return str(body)[:300]


def answer(platform: str, response: httpx.Response) -> dict[str, Any]:
    """The platform's answer, or what went wrong: its message and the path asked, never the token."""
    if response.is_error:
        path = response.request.url.path
        raise PlatformError(f"{platform} answered {response.status_code} to {path}: {said(response)}")
    return response.json()


def ask(client: httpx.Client, platform: str, method: str, url: str, **options: Any) -> dict[str, Any]:
    try:
        response = client.request(method, url, **options)
    except httpx.TransportError as error:  # its message can have the address in it, and the token with it
        raise PlatformError(f"couldn't reach {platform} ({type(error).__name__})") from None
    return answer(platform, response)


# YouTube


def youtube_client() -> tuple[str, str]:
    """Your OAuth client's id and secret."""
    client_id, secret = os.environ.get("YOUTUBE_CLIENT_ID", ""), os.environ.get("YOUTUBE_CLIENT_SECRET", "")
    if not client_id or not secret:
        raise ValueError(
            "Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET: an OAuth client of your own, a Desktop app's, from "
            f"Google Cloud's console ({SETUP})"
        )
    return client_id, secret


def connect_youtube(
    *, browse: Callable[[str], Any] = webbrowser.open, client: httpx.Client | None = None, wait: float = CONSENT_WAIT
) -> dict[str, Any]:
    """Asks you, on Google's consent page, to let this read your channel's numbers, and keeps the refresh token Google
    gives (with PKCE, through a one-off server on this machine that the page sends you back to). Returns what's kept.

    Args:
        browse: Opens the consent page (a test's answers it).
        client: An httpx client to send requests with (a test's); one of its own by default.
        wait: Seconds to wait for you on the page.
    """
    client_id, secret = youtube_client()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    answered: dict[str, str] = {}

    class Back(http.server.BaseHTTPRequestHandler):
        """Where the consent page sends you back to, with a code to swap for the tokens."""

        def do_GET(self) -> None:
            query = {key: values[0] for key, values in parse_qs(urlsplit(self.path).query).items()}
            if query.get("state") != state:  # the browser's own requests (a favicon), or someone else's
                self.send_error(404)
                return
            answered.update(query)
            page = "Connected: you can close this tab." if "code" in query else f"Not connected: {query.get('error')}"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode())

        def log_message(self, *args: Any) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Back)
    server.timeout = 1
    back = f"http://127.0.0.1:{server.server_port}/"
    asked = {
        "client_id": client_id,
        "redirect_uri": back,
        "response_type": "code",
        "scope": " ".join(YOUTUBE_SCOPES),
        "access_type": "offline",  # for a refresh token
        "prompt": "consent",  # and again, when you connect again
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    page = f"{GOOGLE_CONSENT}?{urlencode(asked)}"
    print(f"Google's consent page is opening in the browser. If it doesn't, open this:\n{page}", flush=True)
    browse(page)
    deadline = time.monotonic() + wait
    try:
        while not answered and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    if not answered:
        raise PlatformError(f"Google's consent page didn't answer in {wait / 60:.0f} minutes: connect again")
    if "code" not in answered:
        raise PlatformError(f"Google said {answered.get('error', 'no')}: connect again, and allow it")
    with client or httpx.Client(timeout=60) as google:
        form = {"client_id": client_id, "client_secret": secret, "code": answered["code"], "code_verifier": verifier}
        tokens = ask(
            google,
            "Google",
            "POST",
            GOOGLE_TOKEN,
            data={**form, "redirect_uri": back, "grant_type": "authorization_code"},
        )
        if "refresh_token" not in tokens:
            raise PlatformError("Google gave no refresh token: connect again")
        channel = YouTube(tokens["access_token"], client=google).channel()
    kept = {
        "client_id": client_id,
        "refresh_token": tokens["refresh_token"],
        "channel": channel["id"],
        "title": channel["snippet"]["title"],
    }
    keep_account("youtube", kept)
    return kept


def youtube_token(*, client: httpx.Client | None = None) -> str:
    """A token to use YouTube's APIs as you for the next hour, from the refresh token `connect` kept."""
    kept = account("youtube")
    refresh = kept.get("refresh_token") or os.environ.get("YOUTUBE_REFRESH_TOKEN")
    if not refresh:
        raise ValueError(f"YouTube isn't connected: run `{COMMAND} connect youtube` ({SETUP})")
    client_id, secret = youtube_client()
    if kept and kept.get("client_id") != client_id:
        raise ValueError(f"YOUTUBE_CLIENT_ID isn't the client you connected with: run `{COMMAND} connect youtube`")
    form = {"client_id": client_id, "client_secret": secret, "refresh_token": refresh, "grant_type": "refresh_token"}
    try:
        return ask(client or httpx.Client(timeout=60), "Google", "POST", GOOGLE_TOKEN, data=form)["access_token"]
    except PlatformError as error:
        if "invalid_grant" in str(error):  # revoked, or 7 days old, from a client whose app is still in Testing
            raise PlatformError(
                f"YouTube's sign-in has run out or was taken back: run `{COMMAND} connect youtube` again. If it "
                "runs out every week, your OAuth app is still in Testing: publish it (Google Auth Platform, Audience)"
            ) from None
        raise


class YouTube:
    """YouTube's Data and Analytics APIs, as the channel's owner."""

    def __init__(self, token: str, *, client: httpx.Client | None = None) -> None:
        self.http = client or httpx.Client(timeout=60)
        self.http.headers["Authorization"] = f"Bearer {token}"

    @classmethod
    def connected(cls, *, client: httpx.Client | None = None) -> "YouTube":
        return cls(youtube_token(client=client), client=client)

    def data(self, path: str, **params: Any) -> dict[str, Any]:
        return ask(self.http, "YouTube", "GET", f"{YOUTUBE_DATA}/{path}", params=params)

    def videos(self, ids: list[str]) -> list[dict[str, Any]]:
        """The videos' titles, lengths and public counts (the Data API's snippet, contentDetails and statistics),
        for those it has."""
        found: list[dict[str, Any]] = []
        for first in range(0, len(ids), 50):
            chunk = ",".join(ids[first : first + 50])
            found += self.data("videos", part="snippet,contentDetails,statistics", id=chunk).get("items", [])
        return found

    def channel(self) -> dict[str, Any]:
        """Your channel."""
        items = self.data("channels", part="snippet,contentDetails", mine="true").get("items") or []
        if not items:
            raise PlatformError("this Google account has no YouTube channel")
        return items[0]

    def uploads(self, count: int | None = 50, *, since: str | None = None) -> list[dict[str, Any]]:
        """Your newest videos, newest first: {id, title, posted}. The newest `count`, or (count None) all those
        posted since the date `since` (yyyy-mm-dd)."""
        playlist = self.channel()["contentDetails"]["relatedPlaylists"]["uploads"]
        found: list[dict[str, Any]] = []
        page = None
        while count is None or len(found) < count:
            items = self.data(
                "playlistItems",
                part="snippet,contentDetails",
                playlistId=playlist,
                maxResults=50 if count is None else min(count - len(found), 50),
                **({"pageToken": page} if page else {}),
            )
            for item in items.get("items", []):
                video = {
                    "id": item["contentDetails"]["videoId"],
                    "title": item["snippet"]["title"],
                    "posted": item["contentDetails"].get("videoPublishedAt", ""),
                }
                if since and video["posted"] and video["posted"][:10] < since:
                    return found  # newest first: the rest were posted before
                found.append(video)
            page = items.get("nextPageToken")
            if not page:
                break
        return found

    def report(self, **params: Any) -> list[dict[str, Any]]:
        """A YouTube Analytics report on your channel: its rows, each by its columns' names. None, when YouTube has
        no numbers for it yet."""
        table = ask(self.http, "YouTube", "GET", YOUTUBE_ANALYTICS, params={"ids": "channel==MINE", **params})
        names = [column["name"] for column in table.get("columnHeaders", [])]
        return [dict(zip(names, row, strict=True)) for row in table.get("rows", [])]


YOUTUBE_ID = re.compile(r"[\w-]{11}")


def youtube_id(link: str) -> str:
    """A YouTube video's id, from its link (a Short's, a watch page's, youtu.be's), or the id itself."""
    link = link.strip()
    if YOUTUBE_ID.fullmatch(link):
        return link
    parts = urlsplit(link if "//" in link else f"https://{link}")
    host = (parts.hostname or "").removeprefix("www.").removeprefix("m.")
    segments = parts.path.strip("/").split("/")
    found = []
    if host == "youtu.be":
        found = segments[:1]
    elif host == "youtube.com" or host.endswith(".youtube.com"):
        found = parse_qs(parts.query).get("v", [])
        if len(segments) > 1 and segments[0] in ("shorts", "live", "embed"):
            found.append(segments[1])
    for candidate in found:
        if YOUTUBE_ID.fullmatch(candidate):
            return candidate
    raise ValueError(f"{link!r} isn't a YouTube video's link")


# Instagram


def renew(token: str, client: httpx.Client | None = None) -> str:
    """A new 60-day token for one that's at least a day old and hasn't run out."""
    params = {"grant_type": "ig_refresh_token", "access_token": token}
    return ask(
        client or httpx.Client(timeout=60), "Instagram", "GET", f"{INSTAGRAM}/refresh_access_token", params=params
    )["access_token"]


def connect_instagram(*, client: httpx.Client | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Keeps INSTAGRAM_ACCESS_TOKEN, once it's shown to work, renewed for 60 days. Returns what's kept."""
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        raise ValueError(
            "Set INSTAGRAM_ACCESS_TOKEN: a token from your Meta app's dashboard (Instagram, API setup with Instagram "
            f"login, Generate token), in .env or the environment ({SETUP})"
        )
    me = Instagram(token, client=client).get("me", fields="user_id,username")
    renewed = None  # less than a day old, it can't be renewed yet: then it's renewed the next time it's used
    with contextlib.suppress(PlatformError):
        token, renewed = renew(token, client), (now or datetime.now(UTC)).isoformat()
    kept = {
        "token": token,
        "renewed": renewed,
        "username": me.get("username"),
        "user_id": me.get("user_id"),
    }
    keep_account("instagram", kept)
    return kept


def instagram_token(*, client: httpx.Client | None = None, now: datetime | None = None) -> str:
    """The token `connect` kept, renewed once it's a week old; or INSTAGRAM_ACCESS_TOKEN, where none is kept."""
    kept = account("instagram")
    if not kept:
        token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
        if not token:
            raise ValueError(
                f"Instagram isn't connected: set INSTAGRAM_ACCESS_TOKEN, then run `{COMMAND} connect instagram` ({SETUP})"
            )
        return token
    now = now or datetime.now(UTC)
    if not kept.get("renewed") or now - datetime.fromisoformat(kept["renewed"]) > RENEW:
        try:
            kept = {**kept, "token": renew(kept["token"], client), "renewed": now.isoformat()}
            keep_account("instagram", kept)
        except PlatformError:  # used as it is: if it's run out, what it's used for says so
            pass
    return kept["token"]


class Instagram:
    """The Instagram API with Instagram Login, as the account's owner."""

    def __init__(self, token: str, *, client: httpx.Client | None = None) -> None:
        self.http = client or httpx.Client(timeout=60)
        self.token = token

    @classmethod
    def connected(cls, *, client: httpx.Client | None = None) -> "Instagram":
        return cls(instagram_token(client=client), client=client)

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        url = f"{INSTAGRAM}/{INSTAGRAM_VERSION}/{path}"
        return ask(self.http, "Instagram", "GET", url, params={**params, "access_token": self.token})

    def posts(self) -> Iterator[dict[str, Any]]:
        """Your posts, newest first, a page at a time, for as long as they're asked for."""
        after = None
        while True:
            page = self.get("me/media", fields=INSTAGRAM_MEDIA, limit=50, **({"after": after} if after else {}))
            yield from page.get("data", [])
            paging = page.get("paging", {})
            after = paging.get("cursors", {}).get("after")
            if not paging.get("next") or not after:
                return

    def media(self, count: int = 50) -> list[dict[str, Any]]:
        """Your newest posts, newest first, up to `count`."""
        return list(itertools.islice(self.posts(), count))

    def post(self, code: str, *, among: int = 200) -> dict[str, Any]:
        """A post of yours, by its media id (digits) or its shortcode (from its link), looked for among your
        newest `among`."""
        if code.isdigit():
            return self.get(code, fields=INSTAGRAM_MEDIA)
        for post in self.media(among):
            if post.get("shortcode") == code or f"/{code}/" in post.get("permalink", ""):
                return post
        raise ValueError(f"Instagram has no post {code} among your newest {among}: is it this account's?")

    def insights(self, media: str, metrics: list[str]) -> tuple[dict[str, Any], dict[str, str]]:
        """A post's numbers, by metric, and those asked for that it said no to, with what it said. A metric it has
        no number for yet is in neither."""
        try:
            return self._insights(media, metrics), {}
        except PlatformError:  # one metric it won't give fails them all: ask for each on its own
            numbers: dict[str, Any] = {}
            refused: dict[str, str] = {}
            for metric in metrics:
                try:
                    numbers |= self._insights(media, [metric])
                except PlatformError as error:
                    refused[metric] = str(error)
            return numbers, refused

    def _insights(self, media: str, metrics: list[str]) -> dict[str, Any]:
        data = self.get(f"{media}/insights", metric=",".join(metrics)).get("data", [])
        return {item["name"]: item["values"][0]["value"] for item in data if item.get("values")}


def is_reel(post: dict[str, Any]) -> bool:
    """Whether a post is a Reel. Instagram Login doesn't give media_product_type, and a Reel's media_type is VIDEO,
    like any video's: its link says, instagram.com/reel/CODE/."""
    return post.get("media_product_type") == "REELS" or (
        post.get("media_type") == "VIDEO" and "/reel/" in (post.get("permalink") or "")
    )


def instagram_code(link: str) -> str:
    """A post's shortcode, from its link (instagram.com/reel/CODE/, /p/CODE/), or the shortcode or media id itself."""
    link = link.strip()
    if re.fullmatch(r"[\w-]+", link):
        return link
    parts = urlsplit(link if "//" in link else f"https://{link}")
    host = (parts.hostname or "").removeprefix("www.")
    segments = parts.path.strip("/").split("/")
    if host == "instagram.com" or host.endswith(".instagram.com"):
        for kind, code in zip(segments, segments[1:], strict=False):
            if kind in ("reel", "reels", "p", "tv") and re.fullmatch(r"[\w-]+", code):
                return code
    raise ValueError(f"{link!r} isn't an Instagram post's link")
