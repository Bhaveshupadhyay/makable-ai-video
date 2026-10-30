"""Signing in to a product by hand, once, so its recordings start signed in.

    python -m shorts signin --url https://app.example.com

opens Chrome on the page, in a profile of the site's own (`home.site_profile`). You sign in there the way the site
signs people in (a password, Google, GitHub, a code by email), then close the window. The profile keeps what the site
saved (its cookies, local storage, IndexedDB), and `drive start --signed-in` and `browse --signed-in` record in it,
headless. A site that refreshes its session as it's used saves the new one there too, so it stays signed in from one
recording to the next. Sign in again when a site's session runs out; `--forget` deletes the profile.

It's the Chrome that browser-use records with, so the profile suits it, and it's not run through browser-use, which
opens a new tab when the last one closes: closing the window is how you say you're done.
"""

import contextlib
import json
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from . import COMMAND
from .home import site, site_profile

WAIT = 20 * 60  # seconds to wait for the window to close
OPENING = 180  # seconds for Chrome to open: the first run after an update can take a while (under Rosetta, say)


def recording_profile(url: str) -> Path:
    """The signed-in profile to record `url` in.

    Raises:
        ValueError: There's none: nobody has signed in to the site with `signin`.
    """
    profile = site_profile(url)
    if not profile.exists():
        raise ValueError(f"nobody has signed in to {site(url)}: sign in once with `{COMMAND} signin --url {url}`")
    return profile


def forget(url: str) -> bool:
    """Deletes the site's signed-in profile: whether there was one."""
    profile = site_profile(url)
    if not profile.exists():
        return False
    shutil.rmtree(profile)
    return True


def _chrome() -> str:
    from browser_use.browser.watchdogs.local_browser_watchdog import LocalBrowserWatchdog

    chrome = LocalBrowserWatchdog._find_installed_browser_path()
    if not chrome:
        raise RuntimeError(
            "No Chrome or Chromium to sign in with: install Chrome, or `uvx playwright install chromium`"
        )
    return chrome


def _pages(port: int) -> list[dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as answer:
        return [target for target in json.load(answer) if target["type"] == "page"]


def _quit(port: int) -> None:
    """Has Chrome quit by itself (CDP's Browser.close), which saves what the site saved to the profile: on a SIGTERM
    it didn't save a cookie set seconds before."""
    from websockets.sync.client import connect  # browser-use's

    with contextlib.suppress(Exception):  # it's quit already (closing the last window does, but on a Mac)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as answer:
            address = json.load(answer)["webSocketDebuggerUrl"]
        with connect(address, open_timeout=5) as browser:
            browser.send(json.dumps({"id": 1, "method": "Browser.close"}))
            browser.recv(timeout=5)


def sign_in(url: str, wait: float = WAIT) -> Path:
    """Opens Chrome on `url` in the site's profile, and returns the profile once the window's closed (or after `wait`
    seconds, keeping what's been saved).

    Raises:
        RuntimeError: Chrome didn't open, or closed at once: the profile's in use (a recording), say. A profile made
            for it is deleted, so the site doesn't look signed in.
    """
    executable, profile = _chrome(), site_profile(url)
    made = not profile.exists()
    profile.mkdir(parents=True, exist_ok=True)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    chrome = subprocess.Popen(
        [executable, f"--user-data-dir={profile}", f"--remote-debugging-port={port}", "--no-first-run",
         "--no-default-browser-check", url],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )  # fmt: skip
    up = False
    try:
        opened = time.time()
        while True:  # until its page is up
            with contextlib.suppress(OSError):
                up = bool(_pages(port))
            if up:
                break
            if chrome.poll() is not None or time.time() - opened > OPENING:
                raise RuntimeError(f"Chrome didn't open: is another Chrome using {profile} (a recording)?")
            time.sleep(0.5)
        deadline = time.time() + wait
        while time.time() < deadline:  # until the window's closed (on a Mac, Chrome stays open without windows)
            try:
                if not _pages(port):
                    break
            except OSError:  # Chrome quit
                break
            time.sleep(1)
    finally:
        _quit(port)
        try:
            chrome.wait(30)
        except subprocess.TimeoutExpired:
            chrome.kill()
        if made and not up:
            shutil.rmtree(profile, ignore_errors=True)
    return profile
