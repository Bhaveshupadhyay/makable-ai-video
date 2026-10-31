"""Chrome, recorded: browser-use's Chrome and its actions, with the screen recorded while Claude Code drives it a
command at a time (`shorts.drive`). Each step's goal and actions are kept with when they happened, so the script can
say what's on screen at each moment.

browser-use's own recorder (`record_video_dir`) writes Chrome's screencast frames as they arrive,
at a fixed rate. Chrome only sends a frame when the page changes, so that video runs fast and skips
pauses, and it's squashed unless its size is given. This keeps each frame's timestamp instead, so the
recording is in real time, and `cut_pauses` then takes out the time between the steps (whoever drives
it thinking), and the parts of its waits where nothing changes.

Headless Chrome draws no mouse pointer, so `Cursor` draws one into the page and glides it to each
element before it's clicked or typed into, in place of browser-use's highlight box. It fades out
2 s after a click.

browser-use pins its own packages, so it runs in a virtualenv of its own (SHORTS_BROWSE_PYTHON).
"""

import asyncio
import base64
import contextlib
import json
import logging
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .media import changes, ffmpeg, frame_size

FPS = 30

# browser-use reads these when it's imported: no usage reports (it would also sync runs to its cloud), and time
# to type a long prompt a key at a time (more than its 60 s).
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("TIMEOUT_TypeTextEvent", "180")


# The pointer, the ripple of a click and the spotlight, added to every page of the tab. They're in a shadow
# root, so the page's CSS can't restyle them, and clicks go through them (pointer-events: none). browser-use
# doesn't count the pointer and the ripple as covering what's under them (transparent background, a faint
# ripple). The spotlight covers the whole page, so it's gone before browser-use reads the page again.
CURSOR_JS = """(() => {
  if (window.__cursor) return;
  const ARROW = '<svg xmlns="http://www.w3.org/2000/svg" width="26" height="30" viewBox="0 0 26 30" style="display:block">'
    + '<path d="M3 2v22l6-5.6 4.2 9.4 3.6-1.6-4.1-9.2H21z" fill="#111" stroke="#fff" stroke-width="2" stroke-linejoin="round"/></svg>';
  const fixed = 'position:fixed;left:0;top:0;margin:0;padding:0;pointer-events:none;z-index:2147483647;';
  let pointer = null, fade = null;
  const place = (x, y, ms) => {
    if (!pointer || !pointer.isConnected) {
      pointer = document.createElement('div');
      pointer.style.cssText = fixed + 'filter:drop-shadow(0 1px 2px rgba(0,0,0,.35))';
      pointer.attachShadow({ mode: 'closed' }).innerHTML = ARROW;
      document.documentElement.appendChild(pointer);
    }
    pointer.style.transition = ms ? `transform ${ms}ms cubic-bezier(.45,0,.2,1)` : 'none';
    pointer.style.transform = `translate(${x - 3}px, ${y - 2}px)`;  // the arrow's tip on (x, y)
  };
  // It fades out in `hide` ms (at once, if that's passed), or stays (null). The fade is an animation, not a
  // timer, so Chrome plays it on time even while the page is busy, as it can be for seconds after a click.
  const hideIn = (hide) => {
    fade?.cancel();
    pointer.style.opacity = hide === null || hide > 0 ? '1' : '0';
    fade = hide > 0
      ? pointer.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 300, delay: hide, easing: 'ease-out', fill: 'forwards' })
      : null;
  };
  let spot = null;  // the spotlight: its layer, and the parts that fade
  const PAD = 6;  // px between the element and the spotlight's ring
  const BUTTONS = 'button, [role="button"], input[type="button"], input[type="submit"], input[type="reset"], input[type="image"]';
  const painted = (el) => {
    const style = getComputedStyle(el);
    return style.backgroundColor !== 'rgba(0, 0, 0, 0)' || style.backgroundImage !== 'none' || style.boxShadow !== 'none'
      || (style.borderTopStyle !== 'none' && parseFloat(style.borderTopWidth) > 0);
  };
  // What the spotlight lights for `el`: a text field with no border or background of its own is drawn by
  // the box it's in (a chat app's prompt often is), so that box.
  const framed = (el) => {
    if (!(el.matches('input, textarea') || el.isContentEditable) || painted(el)) return el;
    const { width, height } = el.getBoundingClientRect();
    for (let up = el.parentElement; up && up !== document.body; up = up.parentElement) {
      const box = up.getBoundingClientRect();
      if (box.width * box.height > 4 * width * height) break;  // a panel, not the field's box
      if (painted(up)) return up;
    }
    return el;
  };
  const hole = (x, y, w, h, r) => `M${x + r} ${y}h${w - 2 * r}a${r} ${r} 0 0 1 ${r} ${r}v${h - 2 * r}`
    + `a${r} ${r} 0 0 1 ${-r} ${r}h${2 * r - w}a${r} ${r} 0 0 1 ${-r} ${-r}v${2 * r - h}a${r} ${r} 0 0 1 ${r} ${-r}z`;
  window.__cursor = {
    glide(fromX, fromY, x, y, ms, hide = null) {
      place(fromX, fromY, 0);
      hideIn(hide);
      pointer.getBoundingClientRect();  // start from there, then animate
      place(x, y, ms);
    },
    click(x, y, hide = null) {
      if (pointer) hideIn(hide);
      const ring = document.createElement('div');
      ring.style.cssText = fixed + `left:${x - 22}px;top:${y - 22}px;width:44px;height:44px;border-radius:50%;`
        + 'background:rgba(79,70,229,.45);opacity:.7;transform:scale(.2);transition:transform .45s ease-out,opacity .45s ease-out';
      document.documentElement.appendChild(ring);
      ring.getBoundingClientRect();
      ring.style.transform = 'scale(1.3)';
      ring.style.opacity = '0';
      setTimeout(() => ring.remove(), 500);
    },
    // The spotlight: the page blurred and dimmed but for a hole where `el` is, with a ring and a shadow around
    // the hole, so `el` looks raised. `el` itself isn't touched: it's sharp because nothing covers it. The hole
    // follows it each frame, as the page scrolls or a text box grows. Whether it's lit: never in a frame, whose
    // window isn't the page's, nor on a button, since on a small one it's a ring round a speck.
    spotlight(el, ms = 350) {
      if (window !== window.top || el.closest(BUTTONS)) return false;
      this.unspot(0);
      const lit = framed(el);
      const host = document.createElement('div');
      host.style.cssText = fixed + 'right:0;bottom:0;z-index:2147483646';  // under the pointer
      const root = host.attachShadow({ mode: 'closed' });
      const dim = root.appendChild(document.createElement('div'));
      const ring = root.appendChild(document.createElement('div'));
      dim.style.cssText = 'position:absolute;inset:0;backdrop-filter:blur(6px) brightness(.6)';
      ring.style.cssText = 'position:absolute;box-shadow:0 0 0 3px rgba(79,70,229,.9),0 16px 44px 4px rgba(0,0,0,.5)';
      document.documentElement.appendChild(host);
      const follow = () => {
        if (!host.isConnected) return;
        const box = lit.getBoundingClientRect();
        if (lit.isConnected && box.width) {  // else it stays where it was
          const [x, y, w, h] = [box.left - PAD, box.top - PAD, box.width + 2 * PAD, box.height + 2 * PAD];
          const r = Math.min((parseFloat(getComputedStyle(lit).borderTopLeftRadius) || 0) + PAD, w / 2, h / 2);
          dim.style.clipPath = `path(evenodd, "M0 0H${innerWidth}V${innerHeight}H0Z${hole(x, y, w, h, r)}")`;
          Object.assign(ring.style, { left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${h}px`, borderRadius: `${r}px` });
        }
        requestAnimationFrame(follow);
      };
      follow();
      const timing = { duration: ms, easing: 'cubic-bezier(.2,.7,.2,1)' };
      dim.animate([{ opacity: 0 }, { opacity: 1 }], timing);
      ring.animate([{ opacity: 0, scale: 1.1 }, { opacity: 1, scale: 1 }], timing);
      spot = { host, parts: [dim, ring] };
      return true;
    },
    // Fades the spotlight out in `ms`, or takes it away at once (0).
    unspot(ms = 300) {
      if (!spot) return;
      if (!ms) {
        spot.host.remove();
        spot = null;
        return;
      }
      // Each part fades on its own: fading the layer they're in would turn the blur off at once. Then it's
      // taken away, even in a tab that's no longer the one in use (a click that opened another).
      const { host, parts } = spot;
      const timing = { duration: ms, easing: 'ease-in', fill: 'forwards' };
      const fades = parts.map((part) => part.animate([{ opacity: 1 }, { opacity: 0 }], timing));
      fades[0].finished.then(() => host.remove(), () => {});
    },
  };
})()"""


@dataclass
class Step:
    """One step: what it set out to do, what it did, and when (seconds into the video)."""

    goal: str
    actions: list[dict[str, Any]]
    did: list[str]  # browser-use's account of each action, e.g. "Clicked button Generate"
    url: str
    start: float  # the actions start (whoever drives it has decided on them)
    end: float  # they've finished and the page has settled
    clicks: list[list[float]] = field(default_factory=list)  # [when, x, y]: x and y in the video's pixels
    typing: list[list[float]] = field(default_factory=list)  # [from, to]: when it typed (none kept: all of it)


class Screencast:
    """Records Chrome's screencast of the tab in use: JPEG frames with their timestamps."""

    def __init__(self, session: Any, frames: Path, size: tuple[int, int]):
        self.session = session
        self.frames = frames
        self.size = size
        self.shots: list[tuple[float, Path]] = []
        self.target: str | None = None  # the CDP session of the recorded tab
        self.stopped = 0.0
        self._acks: set[asyncio.Task] = set()

    @property
    def origin(self) -> float:
        """When the video starts: the first frame's time (Unix seconds)."""
        return self.shots[0][0]

    async def start(self) -> None:
        from browser_use.browser.events import AgentFocusChangedEvent

        self.frames.mkdir(parents=True, exist_ok=True)
        self.session.cdp_client.register.Page.screencastFrame(self._on_frame)
        self.session.event_bus.on(AgentFocusChangedEvent, self._follow_focus)
        await self._follow_focus()

    async def _follow_focus(self, event: Any = None) -> None:
        """Records the tab in use (a step can open and switch tabs)."""
        cdp = await self.session.get_or_create_cdp_session()
        if cdp.session_id == self.target:
            return
        if self.target:
            with contextlib.suppress(Exception):  # the old tab may be closed
                await self.session.cdp_client.send.Page.stopScreencast(session_id=self.target)
        self.target = cdp.session_id
        # A tab the page opened (a link to a new tab) stays in the background, where Chrome doesn't paint it, so its
        # screencast sends a frame now and then instead of every change.
        with contextlib.suppress(Exception):
            await cdp.cdp_client.send.Page.bringToFront(session_id=cdp.session_id)
        width, height = self.size
        await cdp.cdp_client.send.Page.startScreencast(
            params={"format": "jpeg", "quality": 90, "maxWidth": width, "maxHeight": height},
            session_id=cdp.session_id,
        )

    def _on_frame(self, event: dict[str, Any], session_id: str | None) -> None:
        if session_id != self.target:
            return
        shot = self.frames / f"{len(self.shots):05d}.jpg"
        shot.write_bytes(base64.b64decode(event["data"]))
        self.shots.append((event["metadata"].get("timestamp") or time.time(), shot))
        # Chrome sends the next frame once this one is acknowledged.
        ack = asyncio.ensure_future(self._ack(event["sessionId"], session_id))
        self._acks.add(ack)
        ack.add_done_callback(self._acks.discard)

    async def _ack(self, frame: int, session_id: str | None) -> None:
        with contextlib.suppress(Exception):
            await self.session.cdp_client.send.Page.screencastFrameAck(
                params={"sessionId": frame}, session_id=session_id
            )

    async def stop(self) -> None:
        self.stopped = time.time()
        if self.target:
            with contextlib.suppress(Exception):
                await self.session.cdp_client.send.Page.stopScreencast(session_id=self.target)

    def save(self, out: Path) -> Path:
        """Writes the frames as a 30 fps MP4 in real time (each frame lasts until the next), then deletes them."""
        if not self.shots:
            raise RuntimeError("Chrome sent no screencast frames")
        entries = ["ffconcat version 1.0"]
        untils = [at for at, _ in self.shots[1:]] + [self.stopped]
        for (at, shot), until in zip(self.shots, untils, strict=True):
            entries += [f"file {shot.name}", f"duration {max(until - at, 0.001):.3f}"]
        entries.append(f"file {self.shots[-1][1].name}")  # the last entry's duration is ignored
        listing = self.frames / "frames.ffconcat"
        listing.write_text("\n".join(entries) + "\n")
        out.parent.mkdir(parents=True, exist_ok=True)
        for _, shot in self.shots:
            _fit(shot, self.size)
        ffmpeg(
            "-f", "concat", "-i", listing,
            "-vf", f"fps={FPS},scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", out,
        )  # fmt: skip
        shutil.rmtree(self.frames)
        return out


def _fit(shot: Path, size: tuple[int, int]) -> None:
    """Fits a frame of another size into `size`, centred on black. Chrome can send some (a first frame before the
    viewport is set, say), and ffmpeg would stretch every frame to the first one's size, or drop frames where the
    size changes."""
    from PIL import Image, ImageOps

    with Image.open(shot) as frame:
        if frame.size == size:
            return
        fitted = ImageOps.pad(frame.convert("RGB"), size, color="black")
    fitted.save(shot, quality=90)


FADE = 0.3  # seconds the pointer and the spotlight take to fade out, as CURSOR_JS fades them
LIT = 0.5  # seconds the spotlight is on before the pointer moves to its element


class Cursor:
    """A mouse pointer drawn into the page, gliding to what's clicked or typed into, and fading out a
    moment after a click. It can put a spotlight on the element too, blurring the rest of the page."""

    def __init__(self, session: Any, size: tuple[int, int], glide: float = 0.6, hide: float | None = 2.0):
        self.session = session
        self.glide = glide  # seconds
        self.hide = hide  # seconds after a click that it fades out (None: it stays)
        self.at = (size[0] * 0.6, size[1] * 0.7)
        self.hides_at: float | None = None  # when it fades out (Unix seconds), after the last click
        self.lit = False  # whether the spotlight's on
        self.unlit_at: float | None = None  # when the spotlight's faded out (Unix seconds), till it's taken away
        self.clicks: list[tuple[float, float, float]] = []  # (Unix seconds, x, y), for zooming in on them
        self.typing: list[tuple[float, float]] = []  # (Unix seconds) when the actions typed, to play that fast
        self._tabs: set[str] = set()  # the CDP sessions it's been added to

    def _hide_in(self) -> str:
        """In how many ms it fades out, for CURSOR_JS: null if it stays."""
        return "null" if self.hides_at is None else f"{(self.hides_at - time.time()) * 1000:.0f}"

    async def _tab(self) -> Any:
        """The CDP session of the tab in use, with CURSOR_JS added to it."""
        cdp = await self.session.get_or_create_cdp_session()
        if cdp.session_id not in self._tabs:  # a new tab: add it to this page and every one it loads
            await cdp.cdp_client.send.Page.addScriptToEvaluateOnNewDocument(
                params={"source": CURSOR_JS}, session_id=cdp.session_id
            )
            await cdp.cdp_client.send.Runtime.evaluate(params={"expression": CURSOR_JS}, session_id=cdp.session_id)
            self._tabs.add(cdp.session_id)
        return cdp

    async def _run(self, expression: str) -> None:
        cdp = await self._tab()
        await cdp.cdp_client.send.Runtime.evaluate(params={"expression": expression}, session_id=cdp.session_id)

    async def show(self) -> None:
        """Draws it where it was (a page just opened doesn't have it yet), or not, if it's faded out."""
        x, y = self.at
        with contextlib.suppress(Exception):  # the page may be in the middle of loading
            await self._run(f"window.__cursor?.glide({x}, {y}, {x}, {y}, 0, {self._hide_in()})")

    async def move(self, x: float, y: float, *, click: bool) -> None:
        (from_x, from_y), self.at = self.at, (x, y)
        self.hides_at = None
        await self._run(f"window.__cursor?.glide({from_x}, {from_y}, {x}, {y}, {self.glide * 1000:.0f})")
        await asyncio.sleep(self.glide)
        if click:
            self.clicks.append((time.time(), x, y))
            if self.hide is not None:
                self.hides_at = time.time() + self.hide
            await self._run(f"window.__cursor?.click({x}, {y}, {self._hide_in()})")

    async def spotlight(self, node: int) -> None:
        """Puts the spotlight on an element (its backend node id), then waits LIT seconds, so it's lit before the
        pointer moves to it. A button isn't lit (CURSOR_JS says no), and then there's no wait."""
        try:
            cdp = await self._tab()
            found = await cdp.cdp_client.send.DOM.resolveNode(params={"backendNodeId": node}, session_id=cdp.session_id)
            reply = await cdp.cdp_client.send.Runtime.callFunctionOn(
                params={
                    "functionDeclaration": "function () { return window.__cursor?.spotlight(this) ?? false }",
                    "objectId": found["object"]["objectId"],
                    "returnByValue": True,
                },
                session_id=cdp.session_id,
            )
        except Exception:  # it's only for show: the pointer still glides to the element
            return
        if not reply.get("result", {}).get("value"):
            return
        self.lit = True
        await asyncio.sleep(LIT)

    async def unspot(self) -> None:
        """Fades the spotlight out, if it's on."""
        if not self.lit:
            return
        self.lit, self.unlit_at = False, time.time() + FADE
        with contextlib.suppress(Exception):  # a click that opened another page has taken it away
            await self._run(f"window.__cursor?.unspot({FADE * 1000:.0f})")

    async def faded(self) -> None:
        """Waits until it's faded out after the last click, and the spotlight too, so the step it's in shows that,
        not a cut. Then the spotlight's taken away, before browser-use reads the page."""
        if self.hides_at is not None:
            await asyncio.sleep(max(self.hides_at + FADE - time.time(), 0.0))
        if self.unlit_at is not None:
            await asyncio.sleep(max(self.unlit_at - time.time(), 0.0))
            self.unlit_at = None
            with contextlib.suppress(Exception):
                await self._run("window.__cursor?.unspot(0)")


# How far in from an element's left edge the pointer lands, in CSS pixels: on the start of a button's
# label or a field's text, so the zoom shows that rather than the middle of a wide one. It's only where
# the pointer is drawn: browser-use still clicks the element's middle.
POINTER_INSET = 24


async def _target(params: dict[str, Any], session: Any) -> tuple[float, float, int | None] | None:
    """Where the pointer goes for an action, in the page's coordinates, if anywhere: the left of its element. And
    the element's backend node id, for the spotlight (None for an action at coordinates)."""
    if params.get("coordinate_x") is not None and params.get("coordinate_y") is not None:
        return params["coordinate_x"], params["coordinate_y"], None
    if params.get("index") is None:
        return None
    node = await session.get_element_by_index(params["index"])
    if node is None:
        return None
    cdp = await session.cdp_client_for_node(node)
    if cdp.session_id != (await session.get_or_create_cdp_session()).session_id:
        return None  # in a cross-site iframe, whose coordinates aren't the page's
    with contextlib.suppress(Exception):  # browser-use scrolls it into view to click it too
        await cdp.cdp_client.send.DOM.scrollIntoViewIfNeeded(
            params={"backendNodeId": node.backend_node_id}, session_id=cdp.session_id
        )
    rect = await session.get_element_coordinates(node.backend_node_id, cdp)
    if not rect:
        return None
    return rect.x + min(rect.width / 2, POINTER_INSET), rect.y + rect.height / 2, node.backend_node_id


def tools_with(cursor: Cursor) -> Any:
    """browser-use's actions, with the pointer gliding to each one's element first.

    An action given `spotlight=True` puts the spotlight on its element first (unless it's a button), and takes it
    away once it's done what it's for: as it clicks, so what the click does shows clearly, or once it's typed. It's
    off unless asked for.
    """
    from browser_use import Tools

    class CursorTools(Tools):
        async def act(self, action: Any, browser_session: Any, *, spotlight: bool = False, **kwargs: Any) -> Any:
            typed = False
            for name, params in action.model_dump(exclude_unset=True).items():
                if params is None:
                    continue
                typed = typed or name == "input"
                try:
                    target = await _target(params, browser_session)
                    if target:
                        x, y, node = target
                        if spotlight and node is not None:
                            await cursor.spotlight(node)
                        await cursor.move(x, y, click=name in ("click", "input"))
                except Exception:
                    pass  # the pointer is only for show: never fail an action over it
            if not typed:
                await cursor.unspot()
            start = time.time()
            try:
                result = await super().act(action, browser_session, **kwargs)
            finally:
                if typed:
                    cursor.typing.append((start, time.time()))
                await cursor.unspot()
                await cursor.show()
                await cursor.faded()
            return result

    return CursorTools()


def steps_file(video: Path) -> Path:
    return video.with_suffix(".steps.json")


def save_steps(video: Path, steps: list[Step]) -> None:
    steps_file(video).write_text(json.dumps([asdict(step) for step in steps], indent=1, ensure_ascii=False) + "\n")


@dataclass
class Browser:
    """Chrome, being recorded: browser-use's session, the screencast of the tab in use, and the pointer."""

    session: Any
    screencast: Screencast
    pointer: Cursor | None

    def clicks(self, start: float, end: float) -> list[list[float]]:
        """The clicks between `start` and `end` (Unix seconds), as a Step keeps them: [seconds into the video, x, y]."""
        origin = self.screencast.origin
        clicks = self.pointer.clicks if self.pointer else []
        return [[round(when - origin, 2), round(x), round(y)] for when, x, y in clicks if start <= when <= end]

    def typing(self, start: float, end: float) -> list[list[float]]:
        """When it typed between `start` and `end` (Unix seconds), as a Step keeps it: [from, to], seconds into the
        video."""
        spans = self.pointer.typing if self.pointer else []
        return [[self.since(begin), self.since(until)] for begin, until in spans if start <= begin <= end]

    def since(self, at: float) -> float:
        """Seconds into the video at `at` (Unix seconds)."""
        return round(max(at - self.screencast.origin, 0.0), 2)


async def open_browser(
    out: Path,
    *,
    url: str | None = None,
    size: tuple[int, int] = (720, 1280),
    profile: Path | None = None,
    cursor: bool = True,
) -> Browser:
    """Starts Chrome on `url`, then records it, for a video at `out`.

    Args:
        out: Where the MP4 will be saved (`close_browser`): its frames are kept next to it until then.
        url: The page to start on. It's open before the recording starts, so the video starts on it.
        size: The window, in CSS pixels: 720x1280 gets a site's phone layout, and a wider one its desktop
            layout, which the video shows whole. Chrome's screencast sends frames at this size whatever the
            pixel ratio, and `compose` scales them up.
        profile: A Chrome profile to record in, used as it is: one signed in to the site (`signin`), for
            pages behind a sign-in. None: a new, empty one.
        cursor: Draw a mouse pointer that glides to what's clicked, instead of browser-use's highlight box.
    """
    from browser_use import BrowserProfile, BrowserSession

    width, height = size
    chrome = BrowserProfile(
        headless=True,
        viewport={"width": width, "height": height},
        chromium_sandbox=os.geteuid() != 0,  # Chrome's sandbox doesn't run as root (in a container, say)
        keep_alive=True,  # closed by `close_browser`, once the recording has stopped
        user_data_dir=profile,  # None: a new, empty one
        highlight_elements=not cursor,  # the box around what it clicks
    )
    if profile and not _uses(chrome, profile):
        # browser-use works in a copy of a profile whose path says "chrome". The profile's used as it is, so what
        # the site saves while it's recorded (a refreshed session) is there for the next recording.
        shutil.rmtree(chrome.user_data_dir, ignore_errors=True)
        chrome.user_data_dir = profile
    session = BrowserSession(browser_profile=chrome)
    await session.start()
    try:
        if profile and not _uses(session.browser_profile, profile):  # it fell back to an empty one
            raise RuntimeError(f"Chrome couldn't open {profile}: is another Chrome using it (`signin`, a recording)?")
        if url:
            await session.navigate_to(url)
            await asyncio.sleep(1.0)  # let it finish drawing
        screencast = Screencast(session, out.parent / f"{out.stem}-frames", size)
        await screencast.start()
        pointer = Cursor(session, size) if cursor else None
        if pointer:
            await pointer.show()
    except BaseException:
        await session.kill()
        raise
    return Browser(session, screencast, pointer)


def _uses(chrome: Any, profile: Path) -> bool:
    """Whether browser-use's settings (or a session's) have Chrome use `profile` itself."""
    return Path(chrome.user_data_dir).resolve() == profile.resolve()


async def _quit(session: Any) -> None:
    """Has Chrome quit by itself, which saves what the site saved to its profile, and waits until it has (10 s at
    most). browser-use's `kill` doesn't wait for Chrome: a session the site refreshed while it was recorded was lost."""
    profile = Path(session.browser_profile.user_data_dir)
    session._intentional_stop = True  # as `kill` says first: else browser-use tries to reconnect, and logs errors
    with contextlib.suppress(Exception):
        await session.cdp_client.send.Browser.close()
    for _ in range(100):  # Chrome holds a profile with a lock file: SingletonLock, or lockfile on Windows
        if not any(os.path.lexists(profile / lock) for lock in ("SingletonLock", "lockfile")):
            return
        await asyncio.sleep(0.1)


async def close_browser(browser: Browser, out: Path) -> Path:
    """Holds the end a moment, stops the recording and Chrome, and saves the video to `out`."""
    try:
        await asyncio.sleep(1.0)
        await browser.screencast.stop()
    finally:
        await _quit(browser.session)
        # browser-use's kill saves the cookies first, through the Chrome that's quit: an error it logs, unasked for
        events = logging.getLogger("bubus")
        level = events.level
        events.setLevel(logging.CRITICAL)
        try:
            await browser.session.kill()
        finally:
            events.setLevel(level)
    return browser.screencast.save(out)


def _waits(step: Step) -> bool:
    """Whether all the step does is wait (say, 30 s while the product works on something)."""
    return bool(step.actions) and all(set(action) == {"wait"} for action in step.actions)


def _types(step: Step) -> bool:
    """Whether the step types into the page."""
    return any("input" in action for action in step.actions)


def _zoompan(
    clicks: list[tuple[float, float, float]], zoom: float, size: tuple[int, int], ease: float = 0.4, hold: float = 1.0
) -> str:
    """ffmpeg's zoompan, zooming in `zoom` times on each click (seconds into the video, x, y) and out after.

    It zooms in over the `ease` seconds before a click, stays `hold` seconds, then zooms out over `ease`.
    Clicks closer together than that stay zoomed in, panning from one to the next.
    """

    def eased(begin: float) -> str:  # 0 until `begin`, then smoothly up to 1 at `begin + ease`
        u = f"clip((on/{FPS}-{begin:.3f})/{ease},0,1)"
        return f"{u}*{u}*(3-2*{u})"

    clicks = sorted(clicks)
    groups: list[list[tuple[float, float, float]]] = []
    for click in clicks:
        if groups and click[0] - ease <= groups[-1][-1][0] + hold + ease:
            groups[-1].append(click)
        else:
            groups.append([click])
    level = "+".join(f"{eased(group[0][0] - ease)}-{eased(group[-1][0] + hold)}" for group in groups)
    # What it zooms in on: the first click, then it pans to each next one while zooming in on it.
    pans = list(zip(clicks, clicks[1:], strict=False))
    x = f"{clicks[0][1]:g}" + "".join(f"+({b[1] - a[1]:g})*{eased(b[0] - ease)}" for a, b in pans)
    y = f"{clicks[0][2]:g}" + "".join(f"+({b[2] - a[2]:g})*{eased(b[0] - ease)}" for a, b in pans)
    width, height = size
    # zoompan keeps the window inside the frame. on is the frame's number, so on/FPS its time.
    return f"zoompan=z='1+{zoom - 1:g}*({level})':x='{x}-iw/zoom/2':y='{y}-ih/zoom/2':d=1:s={width}x{height}:fps={FPS}"


def cut_pauses(
    video: Path,
    steps: list[Step],
    out: Path,
    *,
    lead: float = 0.6,
    before: float = 0.5,
    after: float = 1.0,
    typing: float = 4.0,
    zoom: float = 1.5,
) -> tuple[Path, list[Step]]:
    """Cuts out the time between the steps (whoever drives it thinking), and the parts of its waits where nothing
    changes.

    Typing plays `typing` times as fast: browser-use types a key at a time, so a long prompt takes 20 s.
    That's the stretches of a step that typed, or the whole step, if it doesn't say when it typed; the
    pointer gliding to the field, and the spotlight on it, play at their own speed. The video zooms in
    `zoom` times on each click, and out after (1: no zooming).

    Keeps each step's actions, from `lead` seconds before them. A step that only waits (say, 30 s while
    the product works on something) keeps each change on the page, from `before` seconds before it to
    `after` seconds after: a new line in a chat, a preview loading. A wait with nothing new is cut whole.
    A ticking timer or a shimmering "Thinking…" doesn't count: in the app this was tuned on, they change
    up to 0.12 % of the frame, under `changes`' 0.15 %; a new line in its chat changed 0.3 % or more, its
    preview 10-60 %. Changes between the steps are cut too: a home page that swaps its headline
    every 2 s, say.

    Returns the new video and the steps timed for it (also saved as `out.steps.json`).
    """
    waits = [step for step in steps if _waits(step)]
    wanted = [[max(step.start - lead, 0.0), step.end] for step in steps if not _waits(step)]
    wanted += [
        [max(at - before, 0.0), at + after]
        for at in (changes(video, FPS) if waits else [])
        if any(step.start <= at <= step.end for step in waits)
    ]
    spans: list[list[float]] = []
    for begin, end in sorted(wanted):
        if spans and begin <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([begin, end])

    # When it typed, all within `spans`.
    typed = [span for step in steps if _types(step) for span in step.typing or [[step.start, step.end]]]

    def moved(at: float) -> float:  # a time in `video` -> the same moment in `out`
        kept = sum(max(min(end, at) - begin, 0.0) for begin, end in spans)
        fast = sum(max(min(end, at) - begin, 0.0) for begin, end in typed)
        return round(kept - fast * (1 - 1 / typing), 2)

    def between(spans: list[list[float]]) -> str:
        return "+".join(f"between(t,{begin:.3f},{end:.3f})" for begin, end in spans) or "0"

    # While typing, only every `typing`th frame (n is the frame's number in `video`, at FPS).
    keep = f"({between(spans)})*if({between(typed)},lt(mod(n,{typing}),1),1)"
    edit = f"select='{keep}',setpts=N/{FPS}/TB"
    clicks = [(moved(when), x, y) for step in steps for when, x, y in step.clicks]
    if zoom > 1 and clicks:  # in 4:4:4, or zoompan moves in steps of 2 pixels
        edit += f",format=yuv444p,{_zoompan(clicks, zoom, frame_size(video))}"
    ffmpeg(
        "-i", video, "-vf", edit, "-an",
        "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", out,
    )  # fmt: skip
    timed = [
        Step(
            **{
                **asdict(step),
                "start": moved(step.start),
                "end": moved(step.end),
                "clicks": [[moved(when), x, y] for when, x, y in step.clicks],
                "typing": [[moved(begin), moved(end)] for begin, end in step.typing],
            }
        )
        for step in steps
    ]
    save_steps(out, timed)
    return out, timed
