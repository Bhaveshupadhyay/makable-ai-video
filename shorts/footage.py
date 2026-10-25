"""Footage: Playwright records the app in a browser window.

Async because Playwright's sync API can't run inside Colab's (Jupyter's) event loop: in the
notebook `await record_page(...)`, in a script `asyncio.run(record_page(...))`.
"""

import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .media import ffmpeg

# Scrolls the page from top to bottom over `ms` milliseconds.
SMOOTH_SCROLL = """(ms) => new Promise(done => {
  const start = performance.now(), from = scrollY;
  const to = document.documentElement.scrollHeight - innerHeight;
  const step = now => {
    const t = Math.min((now - start) / ms, 1);
    scrollTo(0, from + (to - from) * t);
    t < 1 ? requestAnimationFrame(step) : done();
  };
  requestAnimationFrame(step);
})"""


async def record_page(
    url: str,
    out: Path,
    *,
    seconds: float = 15.0,
    demo: Callable[[Any], Awaitable[None]] | None = None,
    size: tuple[int, int] = (720, 1280),
) -> Path:
    """Records a video of `url` in a browser window of `size`, without the blank frames while it loads.

    Playwright records at the window's own size (it never scales up), and `compose` scales the
    recording to the frame: 720x1280 still gets a site's phone layout (narrower than Tailwind's
    768 px `md`), and a landscape size like (1280, 720) is shown whole over a blurred copy.

    Args:
        url: The page to open.
        out: Where to save the MP4.
        seconds: How long to scroll down the page, when there's no `demo`.
        demo: Your own Playwright steps, e.g. `async def demo(page): await page.click("text=Publish")`.
            Without one, the page is scrolled from top to bottom.
        size: The window's width and height, in CSS pixels.
    """
    from playwright.async_api import async_playwright

    out.parent.mkdir(parents=True, exist_ok=True)
    width, height = size
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(
            viewport={"width": width, "height": height},
            record_video_dir=str(out.parent / "playwright"),
            record_video_size={"width": width, "height": height},
        )
        started = time.monotonic()
        page = await context.new_page()
        await page.goto(url, wait_until="networkidle")
        loaded = time.monotonic() - started
        if demo is not None:
            await demo(page)
        else:
            await page.wait_for_timeout(800)
            await page.evaluate(SMOOTH_SCROLL, seconds * 1000)
            await page.wait_for_timeout(800)
        await context.close()
        raw = Path(await page.video.path())
        await browser.close()

    ffmpeg("-ss", f"{loaded:.2f}", "-i", raw, "-an", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", out)
    raw.unlink()
    return out
