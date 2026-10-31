"""Footage recorded by driving Chrome a command at a time, as Claude Code does.

    python -m shorts drive RUN start --url https://app.example.com [--name demo] [--signed-in] [--window 720x1280]
    python -m shorts drive RUN look                  the page: its tabs, its elements by number, a screenshot
    python -m shorts drive RUN click NUMBER          each of these with --goal "what it's for", for the steps
    python -m shorts drive RUN type NUMBER TEXT      click and type take --spotlight, to make the element stand out
    python -m shorts drive RUN keys Enter
    python -m shorts drive RUN scroll down|up [--pages 1] [--number N]
    python -m shorts drive RUN wait SECONDS
    python -m shorts drive RUN wait-for TEXT [--timeout 240]
    python -m shorts drive RUN hold SECONDS          stay on the result: unlike a wait's, its still parts are kept
    python -m shorts drive RUN tab TAB
    python -m shorts drive RUN open URL [--new-tab]
    python -m shorts drive RUN act ACTION [JSON]     any other of browser-use's actions, such as go_back
    python -m shorts drive RUN stop --report "what it showed" [--failed]

`start` opens Chrome on the page (`shorts.browse.open_browser`: recorded, with the pointer, and with --signed-in, in
the profile `python -m shorts signin` signed in to the site), in a process of its own that keeps running, and prints
the page. Each command after it is a step: it runs one of browser-use's actions in that Chrome, with the pointer
gliding to what it clicks or types into, notes the step's goal, what it did and when, and prints the page as it is
now, numbered the way the next command takes them. With --spotlight (it's off without), a click or a type blurs and
dims the rest of the page first, so its element stands out, unless the element's a button
(`shorts.browse.tools_with`). Afterwards, the time between commands (whoever drives it thinking) is cut out, and so
are the parts of the waits where nothing changes. `stop` ends the recording and brings it in as the footage, with
its steps.

It needs no model and no key: whoever sends the commands is the model. Only the process that holds Chrome needs
browser-use (SHORTS_BROWSE_PYTHON); the commands talk to it on a local port, with a token from
RUN/recordings/<name>.driving.json, there while it runs, so they run in any Python. Its log is <name>.drive.log
next to it. A driver that's sent nothing for IDLE seconds stops by itself, and keeps what it recorded.
"""

import asyncio
import base64
import json
import os
import secrets
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .run import Run
from .stages.base import NotReady

IDLE = 30 * 60  # seconds without a command before the driver stops by itself
OPENING = 180  # seconds for Chrome to open before `start` gives up (browser-use's launch can hang)
SETTLE = 0.8  # seconds after an action, for the page to show what it did


def driving_file(run: Run, name: str) -> Path:
    """Where the driver recording `name` listens: its port, its token and its process, while it runs."""
    return run.path(f"recordings/{name}.driving.json")


def log_file(run: Run, name: str) -> Path:
    return run.path(f"recordings/{name}.drive.log")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # someone else's
        pass
    return True


def _log(run: Run, name: str, lines: int = 15) -> str:
    """The end of the driver's log, to say why it stopped."""
    log = log_file(run, name)
    end = "\n".join(log.read_text(errors="replace").splitlines()[-lines:]) if log.exists() else "(it's empty)"
    return f"Its log, {log}:\n{end}"


def start(
    run: Run,
    name: str,
    url: str,
    signed_in: bool,
    window: tuple[int, int],
    python: str,
    environment: dict[str, str],
) -> str:
    """Starts a driver recording `name` from `url` in a `window` (width, height), in `python` (one with browser-use),
    and returns the page."""
    where = driving_file(run, name)
    if where.exists():
        if _alive(json.loads(where.read_text())["pid"]):
            raise NotReady(f"{name!r} is recording already: stop it first (drive {run.folder} stop --name {name})")
        where.unlink()  # its driver died
    log = log_file(run, name)
    log.parent.mkdir(parents=True, exist_ok=True)
    command = [python, "-m", "shorts", "drive", str(run.folder), "serve", "--name", name, "--url", url]
    command += ["--window", "x".join(map(str, window))]
    with log.open("w") as output:
        driver = subprocess.Popen(
            [*command, *(["--signed-in"] if signed_in else [])],
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            env={**environment, "PYTHONUNBUFFERED": "1"},
            start_new_session=True,  # it keeps running after this command
        )
    deadline = time.time() + OPENING
    while not where.exists():
        if driver.poll() is not None:
            raise NotReady(f"the driver stopped before Chrome opened. {_log(run, name)}")
        if time.time() > deadline:
            os.killpg(driver.pid, signal.SIGKILL)  # and the Chrome it started, in its process group
            raise NotReady(f"Chrome didn't open in {OPENING} s, so the driver was stopped. {_log(run, name)}")
        time.sleep(0.5)
    return send(run, name, "look")


def send(run: Run, name: str, command: str, **args: Any) -> str:
    """Sends `command` to the driver recording `name`, and returns what it says.

    Raises:
        NotReady: Nothing's recording `name`, or the command didn't work (an action that failed, a wait-for whose
            text never showed): what the driver says, with the page as it is.
    """
    where = driving_file(run, name)
    if not where.exists():
        raise NotReady(f"nothing's recording {name!r}: start it with `drive {run.folder} start --name {name}`")
    address = json.loads(where.read_text())
    try:
        connection = socket.create_connection(("127.0.0.1", address["port"]), timeout=10)
    except OSError:
        raise NotReady(f"the driver recording {name!r} isn't answering. {_log(run, name)}") from None
    with connection:
        connection.settimeout(None)  # a wait, or saving the video at the end, takes minutes
        request = {"token": address["token"], "command": command, "args": args}
        connection.sendall((json.dumps(request) + "\n").encode())
        reply = connection.makefile(encoding="utf-8").readline()
    if not reply:
        raise NotReady(f"the driver stopped without answering. {_log(run, name)}")
    answer = json.loads(reply)
    if not answer["ok"]:
        raise NotReady(answer["text"])
    return answer["text"]


@dataclass
class Note:
    """A step as it happened, in Unix seconds: `Step` once the video's start is known."""

    goal: str
    actions: list[dict[str, Any]]
    did: list[str]
    url: str
    start: float
    end: float


class Driver:
    """Chrome, recording, and the commands it takes (see the module's docstring)."""

    def __init__(self, run: Run, name: str, url: str, signed_in: bool = False, window: tuple[int, int] = (720, 1280)):
        self.run, self.name, self.url, self.signed_in, self.window = run, name, url, signed_in, window
        self.video = run.path(f"recordings/{name}.mp4")
        self.notes: list[Note] = []

    async def open(self) -> None:
        from .browse import open_browser, tools_with
        from .signin import recording_profile

        profile = recording_profile(self.url) if self.signed_in else None
        self.browser = await open_browser(self.video, url=self.url, size=self.window, profile=profile)
        self.tools = tools_with(self.browser.pointer)
        self.action = self.tools.registry.create_action_model()

    async def handle(self, command: str, args: dict[str, Any]) -> tuple[bool, str]:
        """Runs a command: whether it worked, and what to say."""
        goal = args.pop("goal", None) or ""
        if command == "look":
            return True, await self.look()
        if command == "act":
            return await self.act(goal, args["action"], args.get("params") or {}, spotlight=bool(args.get("spotlight")))
        if command == "wait":
            return await self.wait(goal, args["seconds"])
        if command == "wait-for":
            return await self.wait(goal, args["timeout"], until=args["text"])
        if command == "hold":
            return await self.hold(goal, args["seconds"])
        if command == "stop":
            return True, await self.stop(args.get("report") or "", args.get("success", True))
        return False, f"No command {command!r}"

    async def look(self) -> str:
        """The page, as the next command finds it: the tabs, how far down it is, its elements, and a screenshot."""
        session = self.browser.session
        state = await session.get_browser_state_summary(include_screenshot=True)
        lines = [
            f"Tab {tab.target_id[-4:]}{' (this one)' if tab.target_id == session.agent_focus_target_id else ''}: "
            f"{tab.url} - {tab.title[:40]}"
            for tab in state.tabs
        ]
        if info := state.page_info:
            lines.append(f"{info.pixels_above} px above the window, {info.pixels_below} px below it")
        lines += ["", state.dom_state.llm_representation() or "(no elements)"]
        if state.screenshot:
            shot = base64.b64decode(state.screenshot)
            look = self.run.path(f"recordings/{self.name}-look.{'jpg' if shot[:2] == b'\xff\xd8' else 'png'}")
            look.write_bytes(shot)
            lines += ["", f"Screenshot: {look}"]
        return "\n".join(lines)

    async def act(self, goal: str, name: str, params: dict[str, Any], spotlight: bool = False) -> tuple[bool, str]:
        """One of browser-use's actions, as a step, with the pointer gliding to its element first, and the
        spotlight on it if `spotlight`."""
        try:
            action = self.action(**{name: params})
        except Exception as error:  # an action browser-use hasn't, or the wrong parameters for it
            return False, f"No action {name} with {json.dumps(params)}: {error}"
        page, start = await self.browser.session.get_current_page_url(), time.time()
        result = await self.tools.act(action, browser_session=self.browser.session, spotlight=spotlight)
        await asyncio.sleep(SETTLE)
        did = result.error or result.extracted_content or result.long_term_memory or ""
        self.notes.append(Note(goal or did, [{name: params}], [did], page, start, time.time()))
        return not result.error, f"{did}\n\n{await self.look()}"

    async def shows(self, text: str) -> bool:
        """Whether the tab's page shows `text`, ignoring case."""
        cdp = await self.browser.session.get_or_create_cdp_session()
        expression = f"(document.body?.innerText ?? '').toLowerCase().includes({json.dumps(text.lower())})"
        try:
            reply = await cdp.cdp_client.send.Runtime.evaluate(
                params={"expression": expression, "returnByValue": True}, session_id=cdp.session_id
            )
        except Exception:  # in the middle of loading another page
            return False
        return bool(reply.get("result", {}).get("value"))

    async def wait(self, goal: str, seconds: float, *, until: str | None = None) -> tuple[bool, str]:
        """Waits `seconds`, or until the page shows `until`: a step of only waiting, whose still parts are cut."""
        page, start = await self.browser.session.get_current_page_url(), time.time()
        seen = False
        while time.time() - start < seconds:
            if until and await self.shows(until):
                seen = True
                break
            await asyncio.sleep(min(2.0, max(seconds - (time.time() - start), 0.0)))
        waited = time.time() - start
        did = f"Waited {waited:.0f} s"
        if until:
            did += f": the page shows {until!r}" if seen else f", and the page doesn't show {until!r}"
        params = {"seconds": round(waited), **({"until": until} if until else {})}
        self.notes.append(Note(goal or did, [{"wait": params}], [did], page, start, time.time()))
        return seen or not until, f"{did}\n\n{await self.look()}"

    async def hold(self, goal: str, seconds: float) -> tuple[bool, str]:
        """Stays on the page for `seconds`, all of it kept (a wait's still parts are cut): to end on the result."""
        page, start = await self.browser.session.get_current_page_url(), time.time()
        await asyncio.sleep(seconds)
        did = f"Held {seconds:g} s"
        self.notes.append(Note(goal or did, [{"hold": {"seconds": seconds}}], [did], page, start, time.time()))
        return True, f"{did}\n\n{await self.look()}"

    async def stop(self, report: str, success: bool) -> str:
        """Ends the recording, cuts the pauses out, and brings it in as the footage."""
        from .browse import Step, close_browser, cut_pauses, save_steps
        from .stages.bring_in import bring_in

        page, now = await self.browser.session.get_current_page_url(), time.time()
        self.notes.append(Note("Report", [{"done": {"text": report, "success": success}}], [report], page, now, now))
        await close_browser(self.browser, self.video)
        steps = [
            Step(
                note.goal,
                note.actions,
                note.did,
                note.url,
                self.browser.since(note.start),
                self.browser.since(note.end),
                clicks=self.browser.clicks(note.start, note.end),
                typing=self.browser.typing(note.start, note.end),
            )
            for note in self.notes
        ]
        save_steps(self.video, steps)
        tight, tight_steps = cut_pauses(self.video, steps, self.video.with_name(f"{self.name}-tight.mp4"))
        record = {"driver": "python -m shorts drive", "url": self.url, "signed_in": self.signed_in}
        record["window"] = "x".join(map(str, self.window))
        self.video.with_name(f"{self.name}.browse.json").write_text(json.dumps(record, indent=2) + "\n")
        bring_in(self.run, "footage", [tight], name=self.name)
        return f"{len(tight_steps)} steps, {tight_steps[-1].end:.1f} s, in as the footage {self.name!r}: {tight}"


async def serve(driver: Any, where: Path, *, idle: float = IDLE) -> None:
    """Opens `driver`, then answers its commands on a local port, one at a time, until it's stopped.

    The port and a token go in `where` once it's open, and `where` is removed when it ends. After `idle` seconds
    without a command, it stops by itself.
    """
    await driver.open()
    token = secrets.token_urlsafe(16)
    stopped = asyncio.Event()
    one_at_a_time = asyncio.Lock()
    last = time.time()

    async def answer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal last
        try:
            request = json.loads(await reader.readline())
            if request.get("token") != token:
                ok, text = False, "Wrong token"
            else:
                async with one_at_a_time:
                    last = time.time()
                    try:
                        ok, text = await driver.handle(request["command"], request.get("args") or {})
                    finally:
                        last = time.time()
                        if request["command"] == "stop":  # done with, even if saving it failed
                            stopped.set()
        except Exception as error:
            ok, text = False, f"{type(error).__name__}: {error}"
        writer.write((json.dumps({"ok": ok, "text": text}) + "\n").encode())
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(answer, "127.0.0.1", 0)
    listening = where.with_name(f"{where.name}.new")
    listening.write_text(json.dumps({"port": server.sockets[0].getsockname()[1], "token": token, "pid": os.getpid()}))
    listening.replace(where)  # all at once: a command never reads half of it
    try:
        async with server:
            while not stopped.is_set():
                try:
                    await asyncio.wait_for(stopped.wait(), timeout=min(60.0, idle))
                except TimeoutError:
                    if time.time() - last > idle and not one_at_a_time.locked():
                        report = f"Stopped by itself: no command for {idle / 60:.0f} minutes."
                        async with one_at_a_time:
                            print(await driver.handle("stop", {"report": report, "success": False}))
                        stopped.set()
    finally:
        where.unlink(missing_ok=True)
