"""Footage from instructions: browser-use's agent does a task in Chromium while the screen is recorded.

At each step browser-use shows the model the page (its elements and a screenshot) and runs the
actions the model picks, so you write what to show, not the clicks. Each step's goal and actions
are kept with when they happened, so the script can say what's on screen at each moment.

browser-use's own recorder (`record_video_dir`) writes Chrome's screencast frames as they arrive,
at a fixed rate. Chrome only sends a frame when the page changes, so that video runs fast and skips
pauses (27 s of agent became 7.6 s), and it's squashed unless its size is given. This keeps each
frame's timestamp instead, so the recording is in real time, and `cut_pauses` then takes out the
time the model spent thinking, and the parts of its waits where nothing changes.

Headless Chrome draws no mouse pointer, so `Cursor` draws one into the page and glides it to each
element before the agent clicks or types into it, in place of browser-use's highlight box.

browser-use pins its own google-genai and numpy, so it runs in its own notebook (or virtualenv),
not the one with Chatterbox.
"""

import asyncio
import base64
import contextlib
import json
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .media import changes, ffmpeg, frame_size

FPS = 30

# The pointer and the ripple of a click, added to every page of the tab. They're in a shadow root, so
# the page's CSS can't restyle them; clicks go through them (pointer-events: none); and browser-use
# doesn't count them as covering what's under them (transparent background, a faint ripple).
CURSOR_JS = """(() => {
  if (window.__cursor) return;
  const ARROW = '<svg xmlns="http://www.w3.org/2000/svg" width="26" height="30" viewBox="0 0 26 30" style="display:block">'
    + '<path d="M3 2v22l6-5.6 4.2 9.4 3.6-1.6-4.1-9.2H21z" fill="#111" stroke="#fff" stroke-width="2" stroke-linejoin="round"/></svg>';
  const fixed = 'position:fixed;left:0;top:0;margin:0;padding:0;pointer-events:none;z-index:2147483647;';
  let pointer = null;
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
  window.__cursor = {
    glide(fromX, fromY, x, y, ms) {
      place(fromX, fromY, 0);
      pointer.getBoundingClientRect();  // start from there, then animate
      place(x, y, ms);
    },
    click(x, y) {
      const ring = document.createElement('div');
      ring.style.cssText = fixed + `left:${x - 22}px;top:${y - 22}px;width:44px;height:44px;border-radius:50%;`
        + 'background:rgba(79,70,229,.45);opacity:.7;transform:scale(.2);transition:transform .45s ease-out,opacity .45s ease-out';
      document.documentElement.appendChild(ring);
      ring.getBoundingClientRect();
      ring.style.transform = 'scale(1.3)';
      ring.style.opacity = '0';
      setTimeout(() => ring.remove(), 500);
    },
  };
})()"""


@dataclass
class Step:
    """One step of the agent's: what it set out to do, what it did, and when (seconds into the video)."""

    goal: str
    actions: list[dict[str, Any]]
    did: list[str]  # browser-use's account of each action, e.g. "Clicked button Generate"
    url: str
    start: float  # the actions start (the model has answered)
    end: float  # they've finished and the page has settled
    clicks: list[list[float]] = field(default_factory=list)  # [when, x, y]: x and y in the video's pixels


class Screencast:
    """Records Chrome's screencast of the tab the agent works in: JPEG frames with their timestamps."""

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
        """Records the tab the agent is in (it can open and switch tabs)."""
        cdp = await self.session.get_or_create_cdp_session()
        if cdp.session_id == self.target:
            return
        if self.target:
            with contextlib.suppress(Exception):  # the old tab may be closed
                await self.session.cdp_client.send.Page.stopScreencast(session_id=self.target)
        self.target = cdp.session_id
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
        ffmpeg(
            "-f", "concat", "-i", listing,
            "-vf", f"fps={FPS},scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", out,
        )  # fmt: skip
        shutil.rmtree(self.frames)
        return out


class Cursor:
    """A mouse pointer drawn into the page, gliding to what the agent clicks or types into."""

    def __init__(self, session: Any, size: tuple[int, int], glide: float = 0.6):
        self.session = session
        self.glide = glide  # seconds
        self.at = (size[0] * 0.6, size[1] * 0.7)
        self.clicks: list[tuple[float, float, float]] = []  # (Unix seconds, x, y), for zooming in on them
        self._tabs: set[str] = set()  # the CDP sessions it's been added to

    async def _run(self, expression: str) -> None:
        cdp = await self.session.get_or_create_cdp_session()
        if cdp.session_id not in self._tabs:  # a new tab: add it to this page and every one it loads
            await cdp.cdp_client.send.Page.addScriptToEvaluateOnNewDocument(
                params={"source": CURSOR_JS}, session_id=cdp.session_id
            )
            await cdp.cdp_client.send.Runtime.evaluate(params={"expression": CURSOR_JS}, session_id=cdp.session_id)
            self._tabs.add(cdp.session_id)
        await cdp.cdp_client.send.Runtime.evaluate(params={"expression": expression}, session_id=cdp.session_id)

    async def show(self) -> None:
        """Draws it where it was (a page the agent just opened doesn't have it yet)."""
        x, y = self.at
        with contextlib.suppress(Exception):  # the page may be in the middle of loading
            await self._run(f"window.__cursor?.glide({x}, {y}, {x}, {y}, 0)")

    async def move(self, x: float, y: float, *, click: bool) -> None:
        (from_x, from_y), self.at = self.at, (x, y)
        await self._run(f"window.__cursor?.glide({from_x}, {from_y}, {x}, {y}, {self.glide * 1000:.0f})")
        await asyncio.sleep(self.glide)
        if click:
            self.clicks.append((time.time(), x, y))
            await self._run(f"window.__cursor?.click({x}, {y})")


async def _target(params: dict[str, Any], session: Any) -> tuple[float, float] | None:
    """Where an action will click or type, in the page's coordinates, if anywhere."""
    if params.get("coordinate_x") is not None and params.get("coordinate_y") is not None:
        return params["coordinate_x"], params["coordinate_y"]
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
    return (rect.x + rect.width / 2, rect.y + rect.height / 2) if rect else None


def _tools_with(cursor: Cursor) -> Any:
    """browser-use's actions, with the pointer gliding to each one's element first."""
    from browser_use import Tools

    class CursorTools(Tools):
        async def act(self, action: Any, browser_session: Any, **kwargs: Any) -> Any:
            for name, params in action.model_dump(exclude_unset=True).items():
                if params is None:
                    continue
                try:
                    target = await _target(params, browser_session)
                    if target:
                        await cursor.move(*target, click=name in ("click", "input"))
                except Exception:
                    pass  # the pointer is only for show: never fail an action over it
            result = await super().act(action, browser_session, **kwargs)
            await cursor.show()
            return result

    return CursorTools()


def steps_file(video: Path) -> Path:
    return video.with_suffix(".steps.json")


def save_steps(video: Path, steps: list[Step]) -> None:
    steps_file(video).write_text(json.dumps([asdict(step) for step in steps], indent=1, ensure_ascii=False) + "\n")


def load_steps(video: Path) -> list[Step]:
    return [Step(**step) for step in json.loads(steps_file(video).read_text())]


async def record_task(
    task: str,
    out: Path,
    llm: Any,
    *,
    fallback: Any = None,
    url: str | None = None,
    size: tuple[int, int] = (720, 1280),
    max_steps: int = 25,
    storage_state: Path | None = None,
    cookies: list[dict[str, Any]] | None = None,
    cursor: bool = True,
) -> tuple[Path, list[Step]]:
    """Has browser-use's agent do `task`, recording it to `out` (MP4) and its steps to `out.steps.json`.

    Args:
        task: What to do and show, in plain words: "Add three todos, then mark the second one done".
        out: Where to save the MP4.
        llm: browser-use's chat model, e.g. `ChatGoogle(model=..., vertexai=True, project=..., location="global")`.
        fallback: Another model the agent switches to, for the rest of the run, when `llm` answers
            429 or 5xx (Vertex runs out of shared capacity for a model now and then).
        url: The page to start on. It's open before the recording starts, so the video starts on it.
        size: The window, in CSS pixels: 720x1280 gets a site's phone layout. Chrome's screencast
            sends frames at this size whatever the pixel ratio, and `compose` scales them up.
        max_steps: The most steps the agent may take.
        storage_state: Cookies and local storage to start with (a Playwright storage_state JSON), for
            pages behind a sign-in.
        cookies: Cookies to set before `url` opens, as CDP's `Network.CookieParam`s: `signin.signed_in`
            makes makable's. Unlike `storage_state`, which browser-use prints in some warnings, they're
            set straight in Chrome, never logged or saved.
        cursor: Draw a mouse pointer that glides to what the agent clicks, instead of browser-use's
            highlight box.
    """
    from browser_use import Agent, BrowserProfile, BrowserSession

    width, height = size
    profile = BrowserProfile(
        headless=True,
        viewport={"width": width, "height": height},
        chromium_sandbox=os.geteuid() != 0,  # Chrome's sandbox doesn't run as root (Colab)
        keep_alive=True,  # closed below, once the recording has stopped
        storage_state=storage_state,
        highlight_elements=not cursor,  # the box around what it clicks
    )
    session = BrowserSession(browser_profile=profile)
    marks: dict[int, tuple[float, str, list[dict[str, Any]], str]] = {}

    def on_step(state: Any, output: Any, number: int) -> None:  # the model has answered; the actions come next
        actions = [action.model_dump(exclude_none=True) for action in output.action]
        marks[number] = (time.time(), output.next_goal or "", actions, state.url)

    await session.start()
    try:
        if cookies:
            cdp = await session.get_or_create_cdp_session()
            await cdp.cdp_client.send.Storage.setCookies(params={"cookies": cookies}, session_id=cdp.session_id)
        if url:
            await session.navigate_to(url)
            await asyncio.sleep(1.0)  # let it finish drawing
        screencast = Screencast(session, out.parent / f"{out.stem}-frames", size)
        await screencast.start()
        pointer = Cursor(session, size) if cursor else None
        if pointer:
            await pointer.show()
        agent = Agent(
            task=task,
            llm=llm,
            fallback_llm=fallback,
            browser_session=session,
            tools=_tools_with(pointer) if pointer else None,
            register_new_step_callback=on_step,
            directly_open_url=False,  # it's open already
            use_judge=False,  # a second model call that grades the run
            enable_signal_handler=False,  # Jupyter owns Ctrl+C
        )
        history = await agent.run(max_steps=max_steps)
        await asyncio.sleep(1.0)  # hold the end a moment
        await screencast.stop()
    finally:
        await session.kill()

    screencast.save(out)
    steps = []
    for item in history.history:
        if item.metadata is None or item.metadata.step_number not in marks:
            continue
        at, goal, actions, page = marks[item.metadata.step_number]
        # The final report in full: browser-use's memory of it keeps only the first 100 characters.
        did = [
            (result.is_done and result.extracted_content)
            or result.long_term_memory
            or result.extracted_content
            or result.error
            or ""
            for result in item.result
        ]
        clicks = [
            [round(when - screencast.origin, 2), round(x), round(y)]
            for when, x, y in (pointer.clicks if pointer else [])
            if at <= when <= item.metadata.step_end_time
        ]
        steps.append(
            Step(
                goal=goal,
                actions=actions,
                did=did,
                url=page,
                start=round(max(at - screencast.origin, 0.0), 2),
                end=round(item.metadata.step_end_time - screencast.origin, 2),
                clicks=clicks,
            )
        )
    save_steps(out, steps)
    return out, steps


def _waits(step: Step) -> bool:
    """Whether all the step does is wait (say, 30 s while makable builds)."""
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
    """Cuts out the time the model spent thinking, and the parts of its waits where nothing changes.

    Steps that type play `typing` times as fast: browser-use types a key at a time, so a long prompt
    takes 20 s. The video zooms in `zoom` times on each click, and out after (1: no zooming).

    Keeps each step's actions, from `lead` seconds before them. A step that only waits (say, 30 s while
    makable builds) keeps each change on the page, from `before` seconds before it to `after` seconds
    after: a new line in makable's chat, the preview loading. A wait with nothing new is cut whole.
    makable's ticking timer and shimmering "Thinking…" don't count: they change up to 0.12 % of the
    frame, under `changes`' 0.15 %; a new line in the chat changes 0.3 % or more, the preview 10-60 %.
    Changes while the model thinks are cut too: makable's home page swaps its headline every 2 s.

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

    typed = [[step.start, step.end] for step in steps if _types(step)]  # all within `spans`

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
            }
        )
        for step in steps
    ]
    save_steps(out, timed)
    return out, timed
