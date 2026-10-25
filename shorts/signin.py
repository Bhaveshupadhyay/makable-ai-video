"""Signs the recorder in to makable as a demo user, with a password instead of GitHub.

makable signs people in with GitHub through Supabase, then keeps Supabase's session in two HttpOnly
cookies (makable-backend's `app/api/cookies.py`). The demo user signed in with GitHub once, so makable
knows it, and also has a password in Supabase. `signed_in` asks Supabase for a session with that
password and gives the browser the same two cookies, so the site opens signed in:

    cookies = signed_in("https://makable.tech", SUPABASE_URL, SUPABASE_KEY, DEMO_EMAIL, DEMO_PASSWORD)
    await record_task(task, out, llm, url="https://makable.tech", cookies=cookies)

Each call starts a new session, so nothing is saved between runs. Sign in again for each recording:
the site rotates the refresh token as it goes, and Supabase ends a session whose old refresh token
comes back.

Password sign-in needs Supabase's Email provider turned on (it answers 422 email_provider_disabled
otherwise).
"""

import json
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

# Each cookie's name and path, as makable-backend sets them (`app/constants/auth.py`).
ACCESS_COOKIE = ("makable_access", "/api/v1")
REFRESH_COOKIE = ("makable_refresh", "/api/v1/auth")
REFRESH_COOKIE_DAYS = 30  # the backend's REFRESH_TOKEN_TTL_DAYS
SESSION_PATH = "/api/v1/auth/session"


def signed_in(app_url: str, supabase_url: str, key: str, email: str, password: str) -> list[dict[str, Any]]:
    """Signs in as `email` and returns the cookies that make `app_url` open signed in, for `record_task`'s
    `cookies`.

    Args:
        app_url: makable's address, e.g. "https://makable.tech".
        supabase_url: https://<ref>.supabase.co
        key: The project's publishable key (or the legacy anon key): the one makable's backend uses.

    Raises:
        RuntimeError: Supabase refused the sign-in, or makable doesn't know the user.
    """
    parts = urlsplit(app_url)
    origin = f"{parts.scheme}://{parts.netloc}"
    session = password_session(supabase_url, key, email, password)
    _check(origin, session["access_token"], email)
    return session_cookies(origin, session)


def password_session(supabase_url: str, key: str, email: str, password: str) -> dict[str, Any]:
    """A new Supabase session for `email`: access_token, refresh_token, expires_in (seconds) and user."""
    # Pasted secrets can end in a line break (Colab kept a "\r\n"), and Supabase matches the email exactly.
    supabase_url, key, email, password = supabase_url.strip(), key.strip(), email.strip(), password.strip("\r\n")
    request = urllib.request.Request(
        f"{supabase_url.rstrip('/')}/auth/v1/token?grant_type=password",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"apikey": key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:  # e.g. 400 invalid_credentials, 422 email_provider_disabled
        body = err.read().decode()
        hint = ""
        if "invalid_credentials" in body:
            hint = (
                f"\nSupabase says this when no user in {supabase_url} has the email {email!r}, when that user has "
                "no password yet, or when the password is wrong."
            )
            if password != password.strip():
                hint += " The password starts or ends with a space: check the secret."
        raise RuntimeError(f"Supabase refused the password sign-in ({err.code}): {body}{hint}") from None


def session_cookies(origin: str, session: dict[str, Any]) -> list[dict[str, Any]]:
    """The backend's two auth cookies for `session`, on `origin` (the Worker there forwards /api to the backend),
    as CDP's `Network.CookieParam`s."""
    now = time.time()

    def cookie(name_path: tuple[str, str], value: str, seconds: float) -> dict[str, Any]:
        name, path = name_path
        return {
            "name": name,
            "value": value,
            "url": origin,  # a `url` and no `domain`: only this host gets it, like the backend's own cookie
            "path": path,
            "expires": now + seconds,
            "httpOnly": True,
            "secure": origin.startswith("https://"),
            "sameSite": "Lax",
        }

    return [
        cookie(ACCESS_COOKIE, session["access_token"], session["expires_in"]),
        cookie(REFRESH_COOKIE, session["refresh_token"], REFRESH_COOKIE_DAYS * 86400),
    ]


def _check(origin: str, access_token: str, email: str) -> None:
    """Asks makable who the session belongs to, so a recording never starts on the signed-out page."""
    name, _ = ACCESS_COOKIE
    request = urllib.request.Request(
        origin + SESSION_PATH, headers={"Cookie": f"{name}={access_token}", "User-Agent": "makable-videos"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30):
            return
    except urllib.error.HTTPError as err:
        if err.code == 401:
            raise RuntimeError(
                f"Supabase signed {email} in, but makable doesn't know that user: sign in to makable with the "
                "demo's GitHub account once, and set the password on that same Supabase user"
            ) from None
        raise RuntimeError(f"{origin}{SESSION_PATH} answered {err.code}: {err.read().decode()}") from None
