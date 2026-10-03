"""Access to the phone over adb: screen dump, screenshots, input, and navigation inside KeePassDX.

Navigation never presses Back a fixed number of times: `back_until` checks a condition before each
press and gives up after a limit.
"""

import contextlib
import hashlib
import io
import json
import os
import re
import statistics
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from PIL import Image

from errors import (  # noqa: F401  (re-exported: the rest of the code says dv.DeviceError and so on)
    DeviceError, ElementMissing, Locked, NeedsPerson, ScreenshotFailed, SystemException, UnknownModal, WaitTimeout,
    WrongState,
)
import shot_meta  # the sidecar of a screenshot
from ui import ui  # the object repository: elements by name

# Git Bash rewrites paths like /sdcard; adb must get them unchanged.
os.environ["MSYS_NO_PATHCONV"] = "1"

APP = "com.kunzisoft.keepass"  # package prefix of every build flavour


def adb(*args: str, binary: bool = False):
    result = subprocess.run(["adb", *args], capture_output=True)
    return result.stdout if binary else result.stdout.decode("utf8", "replace")


def window_info() -> tuple[str, bool]:
    """The window with the focus (`package/activity`, or "?" while windows change) and whether the
    lock screen is showing. Answered by phonectl, which keeps the last answer until a window event arrives
    (or 1.5 s have passed): a loop that asks again and again costs nothing while nothing changes."""
    answer = phonectl("focus")
    return answer.get("focus", "?"), bool(answer.get("keyguard"))


def focus() -> str:
    """`package/activity` of the window that has the focus."""
    return window_info()[0]


def _flag(value) -> str:
    return "true" if value else "false"


def tree_element(answer: dict) -> ET.Element:
    """The answer of `phonectl tree` as the same tree `uiautomator dump` wrote: a `hierarchy` of `node`
    elements with the same attributes, so that every locator of the object repository works unchanged."""
    root = ET.Element("hierarchy", {"rotation": "0"})

    def add(parent: ET.Element, data: dict, index: int) -> None:
        left, top, right, bottom = data["bounds"]
        element = ET.SubElement(parent, "node", {
            "index": str(index), "text": data["text"], "resource-id": data["resource-id"], "class": data["class"],
            "package": data["package"], "content-desc": data["content-desc"], "checkable": _flag(data["checkable"]),
            "checked": _flag(data["checked"]), "clickable": _flag(data["clickable"]), "enabled": _flag(data["enabled"]),
            "focusable": _flag(data["focusable"]), "focused": _flag(data["focused"]), "scrollable": _flag(data["scrollable"]),
            "long-clickable": _flag(data["long-clickable"]), "password": _flag(data["password"]),
            "selected": _flag(data["selected"]), "bounds": f"[{left},{top}][{right},{bottom}]"})
        for i, child in enumerate(data["children"]):
            add(element, child, i)

    for i, data in enumerate(answer.get("roots") or []):
        add(root, data, i)
    return root


def dump(windows: bool = False) -> ET.Element:
    """The screen as a tree, read on the phone by `phonectl tree` straight from UiAutomation: no wait for the
    screen to go idle, which is what made `uiautomator dump` take 2 to 12 s. With `windows` the floating
    selection toolbar is included. A screen that cannot be read (no window has a tree, the notification
    panel is open) is a technical problem, to be recovered from, not a verdict on the app."""
    problem = "no window has a tree"
    for _ in range(3):
        try:
            answer = phonectl("tree", *(["windows"] if windows else []))
            if answer.get("roots"):
                return tree_element(answer)
        except DeviceError as error:
            problem = str(error)
        time.sleep(0.2)  # a retry after a failed read, not a wait for the screen
    raise DeviceError(f"the screen could not be read ({problem[:100]})")


def screenshot() -> tuple[Image.Image, bytes]:
    """A screenshot, checked: no picture, or an all-black one (what a secure window gives), is a
    ScreenshotFailed, a system exception that fails fast. The evidence is the product of a run."""
    data = adb("exec-out", "screencap", "-p", binary=True)
    return check_picture(data), data


def check_picture(data: bytes) -> Image.Image:
    """The picture in `data`, or a ScreenshotFailed: no picture at all, or an all-black one (what a
    secure window gives), is a system exception that fails fast."""
    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
    except OSError:
        raise ScreenshotFailed(f"screencap returned no picture ({len(data)} bytes): {data[:60]!r}") from None
    if max(high for _, high in image.getextrema()) <= 2:
        raise ScreenshotFailed(
            "the screenshot is black: the window is secure. For KeePassDX the setting Screenshot mode "
            "(enable_screenshot_mode_key) must be on; for a system window there is no picture by design")
    return image


# --- a screenshot with its sidecar (see shot_meta.py) ---------------------------------------------

SHOT_STATIC: dict = {}  # what the run collects once (run_facts.collect): device, environment, code, context
PHONE_SCRIPTS = "/data/local/tmp/kp"  # where phonectl.dex lives on the phone
PHONE_SHOTS = "/sdcard/kpshots"  # the pictures and raw sidecars on the phone, one folder per run
_SEQUENCE = [0]


def phone_shot_dir() -> str:
    """The folder on the phone that holds this run's pictures and raw sidecars."""
    return f"{PHONE_SHOTS}/{SHOT_STATIC.get('context', {}).get('run', 'adhoc')}"


@dataclass
class Shot:
    """A checked screenshot with its raw sidecar and its structured one. Taken on the phone in one
    call (`phonectl shot`), so the facts are on the phone's clock and a moment apart at most."""

    image: Image.Image
    data: bytes
    raw: str  # the raw sidecar as the phone wrote it
    facts: dict
    device_name: str  # the file name on the phone
    device_dir: str

    def write(self, path: Path, clipboard: dict | None = None, selection: dict | None = None, **step) -> Path:
        """Save the picture, its raw sidecar `<name>.png.raw.json` and its structured sidecar
        `<name>.png.json`. Every screenshot has all three: a sidecar that cannot be written removes
        what was written and fails the shot (ScreenshotFailed), like a missing picture. `step` says what
        the run was doing (entry, scenario, label); `clipboard` is given when the shot follows a
        copy, `selection` when it shows a long-press whose text was read."""
        facts = {**self.facts, "file": path.name, "step": {**self.facts.get("step", {}), **step},
                 "raw": {"file": shot_meta.raw_path(path).name, "device_path": f"{self.device_dir}/{self.device_name}.png.raw.json"}}
        if clipboard is not None:
            facts["clipboard"] = clipboard
        if selection is not None:
            facts["selection"] = selection
        written = []
        try:
            for target, payload in ((path, self.data), (shot_meta.raw_path(path), self.raw.encode("utf8"))):
                target.write_bytes(payload)
                written.append(target)
            written.append(shot_meta.write(path, facts))
        except Exception as problem:
            for target in written:
                target.unlink(missing_ok=True)
            raise ScreenshotFailed(f"{path.name}: the picture and its sidecar could not be written together: {problem}") from None
        return path

def annotate(path: Path, **fields) -> None:
    """Add fields to the sidecar of a shot that was written (for example the selection, read after the
    picture was taken). The sidecar is rewritten whole; the picture and the raw file are not touched. A
    shot without a sidecar is a ScreenshotFailed: there is no such thing as a screenshot without one."""
    facts = shot_meta.read(path)
    if facts is None:
        raise ScreenshotFailed(f"{path.name}: no sidecar to add {sorted(fields)} to")
    facts.update(fields)
    shot_meta.write(path, facts)


def capture(label: str = "shot") -> Shot:
    """A screenshot with its raw and structured sidecars, taken on the phone in one call (`phonectl shot`):
    the screencap, the window list (the status bar is measured per shot from it), the display and the
    focus, on the phone's clock, with the raw JSON left next to the picture on the phone. The picture is checked as in
    `screenshot()`: none, or an all-black one, raises ScreenshotFailed. A fact that the phone does not
    give is recorded as missing in the sidecar, never filled in."""
    _SEQUENCE[0] += 1
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", label)
    name = f"{_SEQUENCE[0]:04d}-{safe}"
    folder = phone_shot_dir()
    before = time.time_ns()
    try:
        # the picture and its facts, taken on the phone in one call; the picture comes back on the same socket
        answer, data = phonectl_call(["shot", folder, name], inline=True)
    except DeviceError as problem:
        raise ScreenshotFailed(f"{name}: phonectl could not take the screenshot: {problem}") from None
    after = time.time_ns()
    if data is None:
        raise ScreenshotFailed(f"{name}: phonectl sent no picture")
    image = check_picture(data)
    raw = json.dumps(answer, ensure_ascii=False, indent=1)  # the same JSON the phone left next to the picture
    facts = shot_meta.build(
        file=f"{name}.png",
        png_sha256=hashlib.sha256(data).hexdigest(),
        image_size=image.size,
        raw=shot_meta.parse_shot(answer),
        host_before_ns=before,
        host_after_ns=after,
        static=SHOT_STATIC,
        step={},
        raw_file=f"{name}.png.raw.json",
        device_raw_path=f"{folder}/{name}.png.raw.json",
    )
    return Shot(image, data, raw, facts, name, folder)


def remove_phone_shots() -> None:
    """End: remove this run's pictures and raw sidecars from the phone. The pulled copies are the record."""
    adb("shell", "rm", "-rf", phone_shot_dir())


# --- phonectl: the utility that runs on the phone (cprima-fork/tools/phonectl) ----------------------------

PHONECTL_DEX = Path(__file__).resolve().parent.parent / "tools" / "phonectl" / "build" / "phonectl.dex"
_PHONECTL_PUSHED = [False]


def push_phonectl() -> None:
    """Put phonectl.dex on the phone when the one there is missing or different (compared by SHA-256), once
    per process. Build it first: `uv run python cprima-fork/tools/phonectl/build.py`."""
    if _PHONECTL_PUSHED[0]:
        return
    if not PHONECTL_DEX.exists():
        raise DeviceError(f"{PHONECTL_DEX} does not exist: build it with `uv run python cprima-fork/tools/phonectl/build.py`")
    wanted = hashlib.sha256(PHONECTL_DEX.read_bytes()).hexdigest()
    target = f"{PHONE_SCRIPTS}/phonectl.dex"
    on_phone = adb("shell", "sha256sum", target).split()
    if not on_phone or on_phone[0] != wanted:
        adb("shell", "mkdir", "-p", PHONE_SCRIPTS)
        result = subprocess.run(["adb", "push", str(PHONECTL_DEX), target], capture_output=True)
        if result.returncode != 0:
            raise DeviceError(f"phonectl.dex could not be put on the phone: {result.stderr.decode('utf8', 'replace').strip()}")
    _PHONECTL_PUSHED[0] = True


class PhoneServer:
    """The connection to `phonectl serve`, which runs on the phone for as long as the run does. One
    `adb shell` starts it, one `adb forward` makes its local socket reachable, and from then on every
    command is a JSON line on that socket: a few milliseconds, with no `adb` process and no process start on
    the phone. The picture of a `shot` comes back on the same socket."""

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.port: int | None = None
        self.sock = None
        self.file = None

    @property
    def alive(self) -> bool:
        return self.file is not None and self.process is not None and self.process.poll() is None

    def start(self) -> None:
        import socket
        import threading

        push_phonectl()
        name = f"phonectl-{os.getpid()}-{int(time.time())}"
        self.process = subprocess.Popen(
            ["adb", "shell", f"CLASSPATH={PHONE_SCRIPTS}/phonectl.dex app_process /system/bin PhoneCtl serve {name}"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        first: list[bytes] = []
        reader = threading.Thread(target=lambda: first.append(self.process.stdout.readline()), daemon=True)
        reader.start()
        reader.join(20)
        try:
            ready = json.loads(first[0].decode("utf8", "replace")) if first else None
        except ValueError:
            ready = None
        if not ready or not ready.get("ready"):
            self.process.kill()
            raise DeviceError(f"phonectl serve did not start: {first[0][:160]!r}" if first else "phonectl serve did not start in 20 s")
        forward = subprocess.run(["adb", "forward", "tcp:0", f"localabstract:{name}"], capture_output=True, text=True)
        if forward.returncode != 0 or not forward.stdout.strip().isdigit():
            self.process.kill()
            raise DeviceError(f"adb forward failed: {forward.stderr.strip() or forward.stdout.strip()}")
        self.port = int(forward.stdout.strip())
        self.sock = socket.create_connection(("127.0.0.1", self.port), timeout=60)
        self.file = self.sock.makefile("rwb")

    def call(self, args: list[str], inline: bool = False) -> tuple[dict, bytes | None]:
        """One command: its JSON answer and, for a `shot` with `inline`, the picture's bytes."""
        request = {"args": args, **({"inline": True} if inline else {})}
        try:
            self.file.write((json.dumps(request) + "\n").encode("utf8"))
            self.file.flush()
            line = self.file.readline()
            if not line:
                raise ConnectionError("the server closed the connection")
            answer = json.loads(line)
            binary = self.file.read(answer["png_bytes"]) if answer.get("png_bytes") else None
        except (OSError, ValueError, KeyError) as problem:
            self.stop(quiet=True)  # the next call starts a fresh server
            raise DeviceError(f"phonectl server: the connection was lost ({type(problem).__name__}: {problem})") from None
        return answer, binary

    def stop(self, quiet: bool = False) -> None:
        if self.file is not None and not quiet:
            try:
                self.call(["quit"])
            except DeviceError:
                pass
        for closer in (getattr(self.file, "close", None), getattr(self.sock, "close", None)):
            try:
                if closer:
                    closer()
            except OSError:
                pass
        if self.port is not None:
            subprocess.run(["adb", "forward", "--remove", f"tcp:{self.port}"], capture_output=True)
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
        self.process = self.sock = self.file = self.port = None


_SERVER = PhoneServer()


def stop_phonectl() -> None:
    """End: stop the server on the phone and close the connection. Safe to call when it is not running."""
    _SERVER.stop()


import atexit  # noqa: E402

atexit.register(stop_phonectl)


def phonectl_call(args: list[str], inline: bool = False) -> tuple[dict, bytes | None]:
    """Run one phonectl command on the phone through the server (started on first use) and return its JSON answer
    (and the picture's bytes for an inline `shot`). A command that fails on the phone ({"ok": false}) is a
    DeviceError."""
    if not _SERVER.alive:
        _SERVER.stop(quiet=True)
        _SERVER.start()
    answer, binary = _SERVER.call(args, inline)
    if not answer.get("ok"):
        raise DeviceError(f"phonectl {args[0]}: {answer.get('error', 'failed')}")
    return answer, binary


def phonectl(command: str, *args: str) -> dict:
    """Run one phonectl command and return its JSON answer."""
    return phonectl_call([command, *args])[0]


def clipboard_set(text: str) -> None:
    """Put `text` on the clipboard: the marker before a Copy."""
    phonectl("clip-set", text)


def clipboard_get() -> str | None:
    """The text on the clipboard, or None when it holds none."""
    return phonectl("clip-get").get("text")


def bounds(node: ET.Element) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = map(int, re.findall(r"-?\d+", node.get("bounds")))
    return x1, y1, x2, y2


def centre(box: tuple[int, int, int, int]) -> tuple[int, int]:
    return (box[0] + box[2]) // 2, (box[1] + box[3]) // 2


def tap(x: int, y: int) -> None:
    phonectl("tap", str(x), str(y))


def long_press(x: int, y: int) -> None:
    phonectl("long-press", str(x), str(y), "1200")


def swipe(x1: int, y1: int, x2: int, y2: int, ms: int = 350) -> None:
    phonectl("swipe", str(x1), str(y1), str(x2), str(y2), str(ms))


def keys(*names: str) -> None:
    """Key presses, by name (KEYCODE_BACK, BACK) or number, injected on the phone."""
    phonectl("key", *names)


def type_text(text: str) -> None:
    """Type text with key events, injected on the phone."""
    phonectl("text", text)


def toolbar_nodes(root: ET.Element) -> list[ET.Element]:
    return ui.find_all(root, "android.selection_toolbar.item")


def toolbar_present() -> bool:
    return bool(toolbar_nodes(dump(windows=True)))


def on_list() -> bool:
    return "GroupActivity" in focus()


def on_entry_clean() -> bool:
    """The entry is in front and no selection toolbar is showing."""
    return "EntryActivity" in focus() and not toolbar_present()


def in_app() -> bool:
    return APP in focus()


def back_until(done, limit: int = 6) -> bool:
    """Press Back until `done()` holds, at most `limit` times. The condition is checked before each
    press, so nothing is pressed when the screen is already right."""
    for _ in range(limit):
        if done():
            return True
        press_back()
    return done()


def press_back() -> None:
    """Back, then wait until the screen has reacted (the focus changed), at most 1.5 s, and let the
    popup handler answer a dialog that Back may have raised."""
    before = focus()
    keys("BACK")
    deadline = time.time() + 1.5
    while time.time() < deadline and focus() == before:
        time.sleep(0.1)
    deal_with_modals()


# --- dialogs and prompts ------------------------------------------------------------------------
#
# Two kinds of modal were seen on the phone:
#   system  Android's own prompt (user verification before an entry can be edited). Its window has
#           no `package/Activity` name: mCurrentFocus is "Window{... u0 BiometricPrompt}", and its
#           nodes in the dump belong to com.android.systemui.
#   dialog  an AlertDialog of the app ("Discard changes?"). The plain dump then holds only the
#           dialog, with android:id/message and android:id/button1..3.
# What to do with each is a table in the spec (`dialogs`); a modal that is not in the table is an
# error that says what it shows. Back is never pressed blindly.

DIALOGS: list[dict] = []


@dataclass
class Modal:
    kind: str  # "system" or "dialog"
    window: str
    title: str = ""
    message: str = ""
    buttons: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)
    texts: list[str] = field(default_factory=list)


ENV: dict = {"target": "com.kunzisoft.keepass.cprima_fork"}


def configure(dialogs: list[dict], env: dict | None = None) -> None:
    """The table of known dialogs (from the spec) and the environment profile of the phone."""
    global DIALOGS
    DIALOGS = dialogs
    if env:
        ENV.update(env)
        # the systems of this phone (its default apps), one file each in environments/<profile>/
        folder = Path(__file__).parent / "environments" / env.get("key", "")
        if folder.is_dir():
            ui.load_folder(folder)


def detect_handlers() -> dict[str, str]:
    """The apps this phone uses by default, asked from Android: the holders of the dialer, browser,
    home and SMS roles, and what handles a dial, a web address and a mail address. `tel:` links have
    no default (the "Open with" sheet), so they are not listed."""
    found: dict[str, str] = {}
    for key, role in (("dialer-role", "DIALER"), ("browser-role", "BROWSER"), ("home-role", "HOME"), ("sms-role", "SMS")):
        holder = adb("shell", "cmd", "role", "get-role-holders", f"android.app.role.{role}").strip()
        if holder and "/" not in holder and " " not in holder:
            found[key] = holder
    for key, args in (
        ("dial", ["-a", "android.intent.action.DIAL", "-d", "tel:123"]),
        ("web", ["-a", "android.intent.action.VIEW", "-d", "https://example.com"]),
        ("mail", ["-a", "android.intent.action.SENDTO", "-d", "mailto:a@example.com"]),
    ):
        out = adb("shell", "cmd", "package", "resolve-activity", "--brief", *args).strip().splitlines()
        target = out[-1].split("/")[0] if out else ""
        if target and target != "android":  # "android/ResolverActivity" means: no default, ask the person
            found[key] = target
    return found


def dialed_number(root: ET.Element) -> tuple[str | None, str]:
    """The number a dialer shows, and how it was found. With the environment profile's element
    `dialer.number`, that field; otherwise by content: the edit field with a phone-like text, else
    the phone-like text with the most digits (a keypad key is one digit, so the number wins)."""
    try:
        node = ui.find(root, "dialer.main.number")
    except KeyError:  # the profile has no element for the dialer
        node = None
    if node is not None:
        return node.get("text", ""), "profile element dialer.number"
    best, best_key = None, (-1, -1)
    for n in root.iter("node"):
        text = n.get("text", "")
        digits = sum(c.isdigit() for c in text)
        if digits and re.fullmatch(r"[+\d\s().\-*#]+", text):
            key = (1 if n.get("class", "").endswith("EditText") else 0, digits)
            if key > best_key:
                best, best_key = text, key
    return best, "content"


def detect_modal() -> Modal | None:
    window, locked = "?", False
    for _ in range(3):  # the focus is empty for a moment while windows change
        window, locked = window_info()
        if locked:
            # the lock screen: only a person can unlock it; wake the display so it can be seen
            adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
            return Modal("system", "Keyguard", title="the screen is locked")
        if window != "?":
            break
        time.sleep(0.3)  # the focus is empty for a moment while windows change
    if window != "?" and "/" not in window:
        try:
            screen = dump(windows=True)
            clock = ui.find_all(screen, "android.status_bar.clock")
            texts = [
                n.get("text") for n in screen.iter("node")
                if n.get("package") == "com.android.systemui" and n.get("text") and n not in clock
            ]
        except DeviceError:  # the dump fails under some system windows (the notification panel)
            texts = []
        title = next((t for t in texts), "")
        return Modal("system", window, title=title, texts=texts)
    root = dump()
    buttons = {n.get("text"): bounds(n)
               for name in ("android.dialog.panel.positive", "android.dialog.panel.negative", "android.dialog.panel.neutral")
               for n in ui.find_all(root, name) if n.get("text")}
    if not buttons:
        return None

    def text_of(name: str) -> str:
        node = ui.find(root, name)
        return node.get("text", "") if node is not None else ""

    return Modal("dialog", window, text_of("android.dialog.panel.title"), text_of("android.dialog.panel.message"), buttons,
                 [n.get("text") for n in root.iter("node") if n.get("text")])


def _matches(rule: dict, modal: Modal) -> bool:
    wanted = rule["match"]
    return (
        ("window_prefix" not in wanted or modal.window.startswith(wanted["window_prefix"]))
        and ("window" not in wanted or wanted["window"] == modal.window)
        and ("title" not in wanted or wanted["title"] == modal.title)
        and ("message" not in wanted or wanted["message"] == modal.message)
        and ("text" not in wanted or wanted["text"] in modal.texts)
        and ("text_contains" not in wanted or any(wanted["text_contains"] in t for t in modal.texts))
        and ("has_button" not in wanted or wanted["has_button"] in modal.buttons)
    )


def deal_with_modals(limit: int = 6) -> list[str]:
    """Answer the modals that are showing, as the table says; return the names of the rules used.
    A person-only prompt is waited out. A modal that is not in the table raises UnknownModal."""
    used: list[str] = []
    for _ in range(limit):
        modal = detect_modal()
        if modal is None:
            return used
        rule = next((r for r in DIALOGS if _matches(r, modal)), None)
        if rule is None:
            raise UnknownModal(
                f"unknown {modal.kind}: window {modal.window}, title {modal.title!r}, message {modal.message!r}, "
                f"buttons {list(modal.buttons)}, texts {modal.texts[:6]}"
            )
        if rule["answer"] == "wait":
            wait_for_person(modal, rule)
        elif rule["answer"].startswith("command:"):
            adb("shell", *rule["answer"][len("command:"):].split())
            soft_wait(lambda: modal_gone(modal), timeout=3.0, poll=0.15)  # the panel is gone, not "a second later"
        elif rule["answer"] == "back":
            keys("BACK")  # closes a popup menu
            soft_wait(lambda: modal_gone(modal), timeout=3.0, poll=0.15)
        else:
            button = modal.buttons.get(rule["answer"])
            if button is None:
                raise DeviceError(f"{rule['name']}: no button {rule['answer']!r}, there are {list(modal.buttons)}")
            tap(*centre(button))
            soft_wait(lambda: modal_gone(modal), timeout=3.0, poll=0.15)
        used.append(rule["name"])
    raise DeviceError(f"modals keep coming: {used}")


def modal_gone(modal: Modal) -> bool:
    """The modal that was answered is no longer in front: none at all, or another one (the next in a row)."""
    now = detect_modal()
    return now is None or (now.window, now.title, now.message) != (modal.window, modal.title, modal.message)


def wait_for_person(modal: Modal, rule: dict) -> None:
    """The prompt needs the person at the phone (a PIN, a fingerprint): say so and wait."""
    seconds = int(rule.get("waitSeconds", 180))
    print(f"   waiting for you on the phone ({modal.window}: {modal.title}); {seconds} s", flush=True)
    deadline = time.time() + seconds
    while time.time() < deadline:
        time.sleep(3.0)
        if detect_modal() is None:
            return
    raise DeviceError(f"{rule['name']}: still showing after {seconds} s, nobody answered it")


# --- states, explicit waits, recovery, evidence ---------------------------------------------------
#
# The patterns of Selenium and of RPA frameworks, applied to the phone:
#   explicit waits   `wait_until` polls a condition with a timeout and a message; no blind sleeps.
#                    Every poll first lets the popup handler answer known modals, like a handler for
#                    unexpected alerts, so a dialog cannot block a wait.
#   known states     `state()` says which screen is in front; actions end by expecting the state
#                    they lead to.
#   recovery         `recover_to_list()` brings the app back to the known start state.
#   evidence         `evidence()` saves the screen and its dumps when something goes wrong.
#   two exception    SystemException (the phone is in the wrong state: retried after recovery,
#   kinds            reported as error) and a failed expectation of the entry (a fail, never retried).

class State(Enum):
    LIST = "list"
    ENTRY = "entry"
    EDIT = "edit"
    LOCKED = "locked"
    FILE_SELECT = "file selection"
    SYSTEM_MODAL = "system modal"
    OTHER_APP = "other app"
    UNKNOWN = "unknown"


def state() -> State:
    """Which screen is in front, from the focus window (cheap, no dump)."""
    window = focus()
    if window == "?":
        return State.UNKNOWN
    if "/" not in window:
        return State.SYSTEM_MODAL
    if APP not in window:
        return State.OTHER_APP
    for name, found in (("GroupActivity", State.LIST), ("EntryEditActivity", State.EDIT),
                        ("EntryActivity", State.ENTRY), ("MainCredentialActivity", State.LOCKED),
                        ("FileDatabaseSelectActivity", State.FILE_SELECT)):
        if window.endswith("." + name):
            return found
    return State.UNKNOWN


def describe_screen() -> str:
    """What the phone shows, for messages: the focus window and the first texts."""
    try:
        texts = [n.get("text") for n in dump().iter("node") if n.get("text")][:6]
    except Exception:
        texts = ["(dump failed)"]
    return f"{focus()} {texts}"


def _holds(value) -> bool:
    """Whether a condition's result counts as true. An XML node is true even without children
    (`bool(element)` is False for those, which would hide a found node)."""
    return True if isinstance(value, ET.Element) else bool(value)


def wait_until(condition, timeout: float = 10.0, poll: float = 0.1, what: str = "the expected state"):
    """Explicit wait: poll `condition` until it is truthy and return its value. Before every poll the
    popup handler answers known modals. Raises WaitTimeout, saying what was waited for."""
    deadline = time.time() + timeout
    while True:
        deal_with_modals()
        value = condition()
        if _holds(value):
            return value
        if time.time() >= deadline:
            raise WaitTimeout(f"after {timeout:g} s still waiting for {what}; the phone shows {describe_screen()}")
        time.sleep(poll)


def settled(read, quiet: float = 0.3, timeout: float = 8.0, poll: float = 0.1, what: str = "the screen to settle"):
    """Call `read()` until its value has not changed for `quiet` seconds, and return it. This replaces a
    fixed sleep after an action: nothing is guessed about how long the phone needs, the value itself says
    when it is done. Judged by what is read (element positions included), so a list that is still
    scrolling is not settled. Running out of time is a WaitTimeout."""
    deadline = time.time() + timeout
    value = read()
    since = time.time()
    while time.time() - since < quiet:
        if time.time() >= deadline:
            raise WaitTimeout(f"after {timeout:g} s still waiting for {what}")
        time.sleep(poll)
        current = read()
        if current != value:
            value, since = current, time.time()
    return value


def _signature(root: ET.Element) -> tuple:
    """What the screen shows, with positions: ids, texts and bounds of every node."""
    return tuple((n.get("resource-id"), n.get("text"), n.get("bounds")) for n in root.iter("node"))


def wait_stable(quiet: float = 0.25, timeout: float = 4.0, windows: bool = False) -> bool:
    """Wait until the screen has not changed for `quiet` seconds (after a swipe, an open, a tap).
    False when it never settled: the caller decides what that means."""
    try:
        settled(lambda: _signature(dump(windows)), quiet=quiet, timeout=timeout, poll=0.05)
        return True
    except WaitTimeout:
        return False


def soft_wait(condition, timeout: float = 3.0, poll: float = 0.3):
    """Like `wait_until`, but running out of time is an answer, not an error: it returns None. For
    what the entry is expected to do (a tap opens an app, a long-press shows a toolbar): that it did
    not is a fail of the entry, not a problem of the phone."""
    deadline = time.time() + timeout
    while True:
        value = condition()
        if _holds(value):
            return value
        if time.time() >= deadline:
            return None
        time.sleep(poll)


def person_needed() -> bool:
    """True while something is in the way that only a person can clear: a lock, or any modal."""
    return state() == State.LOCKED or detect_modal() is not None


def expect_state(expected: State, timeout: float = 10.0) -> None:
    wait_until(lambda: state() == expected, timeout, what=f"the {expected.value} screen")


def recover_to_list(limit: int = 8) -> None:
    """Back to the known start state, the entry list. Answers modals, leaves entries, edit screens and
    other apps with Back, and stops with an error when the app is locked or gone: that needs a
    person."""
    backs_in_foreign_app = 0
    for _ in range(limit):
        deal_with_modals()
        current = state()
        if current == State.LIST:
            return
        if current == State.LOCKED:
            raise Locked("the database is locked (KeePassDX shows its unlock screen)")
        if current == State.UNKNOWN and focus() == "?":
            time.sleep(0.3)  # the focus is empty for a moment while windows change
            continue
        if current == State.OTHER_APP:
            package = focus().split("/")[0]
            if package == home_package():
                bring_app_to_front()  # Back went past the app, to the home screen
            elif backs_in_foreign_app < MAX_BACKS_IN_FOREIGN_APP:
                backs_in_foreign_app += 1
                press_back()
            elif may_force_stop(package):
                # Back did not lead out of the other app (it may keep a draft, ask a question, or
                # start another screen): end it, then return to the app under test
                adb("shell", "am", "force-stop", package)  # returns when the app is stopped: nothing to wait for
                bring_app_to_front()
                backs_in_foreign_app = 0
            else:
                raise DeviceError(f"stuck in {package}, which the script must not force-stop")
            continue
        press_back()
    raise DeviceError(f"could not get back to the entry list; the phone shows {describe_screen()}")


MAX_BACKS_IN_FOREIGN_APP = 2
_HOME_PACKAGE: str | None = None


def home_package() -> str:
    """The package of the home screen (the launcher), asked once."""
    global _HOME_PACKAGE
    if _HOME_PACKAGE is None:
        out = adb("shell", "cmd", "package", "resolve-activity", "--brief",
                  "-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME").strip().splitlines()
        _HOME_PACKAGE = out[-1].split("/")[0] if out else ""
    return _HOME_PACKAGE


def may_force_stop(package: str) -> bool:
    """Only an ordinary app that the test itself started may be force-stopped: never the app under
    test, the home screen, the system UI or other system packages."""
    protected = ("android", "com.android.systemui", home_package())
    return not (package.startswith(APP) or package in protected or package.startswith("com.android.")
                or package.startswith("com.google.android.inputmethod"))


def bring_app_to_front() -> None:
    """Resume the app under test where it was (its task, not a fresh start)."""
    adb("shell", "monkey", "-p", ENV["target"], "-c", "android.intent.category.LAUNCHER", "1")
    soft_wait(in_app, timeout=8.0, poll=0.15)  # until the app is in front, not "1.5 s later"


PRIVATE_WINDOWS = ("ChooserActivity",)  # the share sheet lists contacts: neither picture nor dump is kept
_PRIVATE_TEXT = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|\+?\d[\d\s().-]{6,}\d")  # an e-mail address, a phone number


def snapshot() -> dict:
    """What is on the UI, as data: the focus window, the state, the lock screen, and every node of
    the screen with its id, text, description, class and bounds. Texts that look like an e-mail
    address or a phone number are replaced by a placeholder. Never raises."""
    info: dict = {"time": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        window, locked = window_info()
        info.update(focus=window, keyguard=locked, state=state().value)
    except Exception as problem:
        info["focus_error"] = f"{type(problem).__name__}: {problem}"
        return info
    if any(p in window for p in PRIVATE_WINDOWS):
        info["private_window"] = "not saved: the window shows contacts"
        return info
    try:
        nodes = []
        for n in dump(windows=True).iter("node"):
            text = _PRIVATE_TEXT.sub("<redacted>", n.get("text", ""))[:80]
            if n.get("resource-id") or text or n.get("content-desc"):
                nodes.append({"id": n.get("resource-id"), "text": text, "desc": n.get("content-desc"),
                              "class": n.get("class", "").split(".")[-1], "package": n.get("package"),
                              "clickable": n.get("clickable") == "true", "bounds": n.get("bounds")})
        info["nodes"] = nodes
    except Exception as problem:
        info["dump_error"] = f"{type(problem).__name__}: {problem}"
    return info


def evidence(out: Path, name: str) -> list[str]:
    """Capture the UI for an error handler: the snapshot (data), both XML dumps and the screenshot.
    A private window (the share sheet) is not saved at all. Never raises, so it can run inside any
    catch; a screenshot that cannot be taken is recorded in the snapshot, not hidden."""
    out.mkdir(parents=True, exist_ok=True)
    info = snapshot()
    saved = []
    private = "private_window" in info
    if not private:
        try:
            capture(name).write(out / f"{name}.png", label=name, evidence=True)
            saved.append(f"{name}.png")
        except Exception as problem:
            info["screenshot_error"] = f"{type(problem).__name__}: {str(problem)[:120]}"
        for suffix, windows in (("dump", False), ("windows", True)):
            try:
                (out / f"{name}-{suffix}.xml").write_text(
                    # no angle brackets in the placeholder: this is XML text, and a "<" would make the file invalid
                    _PRIVATE_TEXT.sub("[redacted]", ET.tostring(dump(windows=windows), encoding="unicode")), encoding="utf8")
                saved.append(f"{name}-{suffix}.xml")
            except Exception:
                pass
    try:
        (out / f"{name}-ui.json").write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf8")
        saved.append(f"{name}-ui.json")
    except Exception:
        pass
    return saved


@contextlib.contextmanager
def dump_on_error(out: Path, name: str):
    """In a catch the UI can be dumped: any exception inside the block saves the UI (see `evidence`),
    gets the saved files as `exc.ui_evidence`, and goes on. Use it around any step whose failure
    should come with what the phone showed."""
    try:
        yield
    except BaseException as exc:
        try:
            exc.ui_evidence = evidence(out, name)
        except Exception:
            exc.ui_evidence = []
        raise


def entry_rows(root: ET.Element) -> dict[str, tuple[int, int, int, int]]:
    """The rows of the entry list in view, by title. Only rows inside the list: an open search keeps
    the list underneath, with the same ids, and its own rows are `search.result_title`."""
    return {n.get("text"): bounds(n) for n in ui.find_all(root, "keepassdx.list.rows.title") if n.get("text")}


def scroll_list_to(title: str, order: list[str], limit: int = 60) -> dict | None:
    """Scroll the entry list until the row `title` is in view and return the visible rows.

    `order` is the order of the entries on the list. It tells which way to scroll: towards the start
    when the wanted entry comes before every visible one, else towards the end. Every drag is proved
    by the positions of the rows (see `drag_list`); the end of the list is proved by its geometry, not
    guessed from two equal reads. Returns None when the wanted entry is not on the list.
    """
    for _ in range(limit):
        rows = settled_rows()
        if title in rows:
            return rows
        visible = [order.index(t) for t in rows if t in order]
        towards_start = not visible or order.index(title) < min(visible)
        if drag_list(towards_start, before=rows) == "edge":
            rows = settled_rows()  # the edge is reached; the entry may be in the last view
            return rows if title in rows else None
    return None


def ensure_ready(*expected: State, deep: bool = True) -> None:
    """Precondition of an action: the app is in the expected screen and nothing covers it. Known
    modals are answered first; anything else that is in the way is a WrongState. `deep=False` is the
    cheap check for loops (one window query: system windows and the lock screen are caught, an app
    dialog is not); the full check runs at the boundaries of an action."""
    if deep:
        deal_with_modals()
    else:
        window, locked = window_info()
        if locked or ("/" not in window and window != "?"):
            deal_with_modals()
    current = state()
    if current not in expected:
        raise WrongState(f"expected {[s.value for s in expected]}, the phone shows {describe_screen()}")


def list_viewport(root: ET.Element) -> tuple[int, int, int, int]:
    """The area of the entry list on the screen: the largest scrollable node of the app."""
    best, area = None, 0
    for n in root.iter("node"):
        if n.get("scrollable") == "true" and n.get("package", "").startswith(APP):
            x1, y1, x2, y2 = bounds(n)
            if (x2 - x1) * (y2 - y1) > area:
                best, area = (x1, y1, x2, y2), (x2 - x1) * (y2 - y1)
    return best or (0, 350, 1080, SCREEN_BOTTOM)


SCREEN_BOTTOM = 2178  # above the "screenshot mode" banner and the navigation bar
DRAG_MIN_SHIFT = 150  # a drag moves the rows by about 800 px; this much counts as "it moved"


def drag_list(towards_start: bool, before: dict | None = None) -> str:
    """One drag of the entry list, with proof of what it did, from the positions of the rows.

    Returns "moved" when the rows seen before the drag are now somewhere else (by at least
    DRAG_MIN_SHIFT px, or all gone). When they did not move there are two explanations: the list is at
    its edge, or the drag did not reach the list (a notification panel, another window, a missed
    gesture). A probe tells them apart: drag the OTHER way. If the rows then move, the gesture works
    and the first drag hit the edge ("edge", after dragging back to it). If they move neither way, it
    is a WrongState: never "the end"."""
    ensure_ready(State.LIST, deep=False)
    if before is None:
        before = entry_rows(dump())  # the caller usually has the rows already and passes them
    scroll_list(towards_start)
    after = settled_rows()
    if not after:
        raise WrongState(f"no entry rows after the drag; the phone shows {describe_screen()}")
    if _moved(before, after):
        return "moved"
    scroll_list(not towards_start)  # the probe
    probe = settled_rows()
    if probe and _moved(after, probe):
        scroll_list(towards_start)  # back to the edge it came from
        settled_rows()
        return "edge"
    raise WrongState(
        f"the list moved neither way: the drag did not reach it; the phone shows {describe_screen()}")


def _moved(before: dict, after: dict) -> bool:
    """Did the rows move between two looks? By their positions: the rows that are in both views."""
    shifts = [after[t][1] - before[t][1] for t in before if t in after]
    return not shifts or abs(statistics.median(shifts)) >= DRAG_MIN_SHIFT


def scroll_list(towards_start: bool) -> None:
    """One slow, short drag. A fast swipe flings: the list runs on after the finger lifts and can
    pass the wanted row between two looks at the screen. A drag at this speed stops where it ends."""
    if towards_start:
        swipe(540, 700, 540, 1500, 900)
    else:
        swipe(540, 1500, 540, 700, 900)


def settled_rows(limit: int = 8) -> dict:
    """The rows in view, once the list no longer moves (two looks, 0.3 s apart, show the same)."""
    previous, rows = None, {}
    for _ in range(limit):
        rows = entry_rows(dump())
        if rows == previous:
            return rows
        previous = rows
        time.sleep(0.15)  # the poll between two looks at the rows
    return rows


def read_list_order(limit: int = 120) -> list[str]:
    """The titles of the entry list from top to bottom, read by scrolling from the start to the end."""
    scroll_to_edge(towards_start=True)
    order: list[str] = []
    for _ in range(limit):
        rows = settled_rows()
        titles = [t for t, _ in sorted(rows.items(), key=lambda item: item[1][1])]
        order += [t for t in titles if t not in order]
        if drag_list(towards_start=False, before=rows) == "edge":  # proved by a probe, see drag_list
            rows = settled_rows()
            order += [t for t, _ in sorted(rows.items(), key=lambda item: item[1][1]) if t not in order]
            return order
    raise WrongState(f"the end of the list was not reached after {limit} drags")


def scroll_to_edge(towards_start: bool, limit: int = 80) -> list[str]:
    """Scroll the entry list to its start or its end and return the visible titles from top to
    bottom. The edge is proved by `drag_list`, not guessed."""
    for _ in range(limit):
        if drag_list(towards_start) == "edge":
            rows = settled_rows()
            return [t for t, _ in sorted(rows.items(), key=lambda item: item[1][1])]
    raise WrongState(f"the {'start' if towards_start else 'end'} of the list was not reached after {limit} drags")


def _type(text: str) -> None:
    type_text(text)


def clear_search_field() -> bool:
    """Empty the search field the way a person does: tap the 'x' at its right end
    (keepassdx.search.clear). Never Backspace and never Delete. The 'x' is shown only while the field holds
    text, so no 'x' means the field is empty. After the tap the 'x' must be gone; if it is not, the field
    was not cleared and that is a WrongState, not something to paper over with key presses.
    Returns whether the 'x' was tapped (the field held text)."""
    cross = ui.find(dump(), "keepassdx.search.clear")
    if cross is None:
        return False
    tap(*centre(bounds(cross)))
    if not soft_wait(lambda: ui.find(dump(), "keepassdx.search.clear") is None, timeout=5.0, poll=0.05):
        raise WaitTimeout(f"after 5 s still waiting for the search field to be empty after a tap on its 'x'; the phone shows {describe_screen()}")
    return True


TRACE = os.environ.get("KP_TRACE") == "1"  # set KP_TRACE=1 to see where the time goes inside a step
_TRACE_LAST = [time.time()]


def trace(label: str) -> None:
    """With KP_TRACE=1: the time since the last trace point, and what just finished."""
    if TRACE:
        now = time.time()
        print(f"      trace +{(now - _TRACE_LAST[0]) * 1000:6.0f} ms  {label}", flush=True)
        _TRACE_LAST[0] = now


def search_for(term: str) -> tuple[int, list[tuple[str, ET.Element]]]:
    """Type `term` into the search of the entry list and read the answer: the number of results that
    the app shows, and the result rows in view as (title, node). The search is opened first when it
    is not open. Only rows inside the result list count: the entry list underneath has the same ids."""
    trace(f"search {term!r}: start")
    ensure_ready(State.LIST)
    trace("ensure_ready")
    if ui.find(dump(), "keepassdx.search.field") is None:
        tap(*centre(bounds(ui.require(dump(), "keepassdx.list.search_icon"))))
        wait_until(lambda: ui.find(dump(), "keepassdx.search.field") is not None, 8, what="the search field")
        trace("search opened")
    field = ui.require(dump(), "keepassdx.search.field")
    tap(*centre(bounds(field)))
    trace("tap on the field")
    # the field has the focus (the cursor is in it) before anything is typed or cleared
    soft_wait(lambda: (lambda n: n is not None and n.get("focused") == "true")(ui.find(dump(), "keepassdx.search.field")),
              timeout=2.0, poll=0.1)
    trace("field focused")
    latest: dict = {}

    def look() -> tuple:
        root = dump()
        count_node = ui.find(root, "keepassdx.search.count")
        count = int(count_node.get("text")) if count_node is not None and count_node.get("text", "").isdigit() else None
        rows = [(n.get("text"), n) for n in ui.find_all(root, "keepassdx.search.results.title") if n.get("text")]
        latest["count"], latest["rows"] = count, rows
        return count, tuple(t for t, _ in rows)

    before = look()  # what the results show now: after the clear and the typing they must differ from it
    cleared = clear_search_field()  # a tap on the 'x', not Backspace or Delete
    trace("cleared by the 'x'")
    if term:
        _type(term)
        trace("typed (events injected)")
        # what the field holds must be the term: an old term that was not cleared would give a wrong answer
        def field_holds_term() -> bool:
            node = ui.find(dump(), "keepassdx.search.field")
            return node is not None and node.get("text") == term  # `is not None`: a node without children is falsy

        # one tight loop: the events are queued and dispatched in order, the field fills within a frame or two
        if not soft_wait(field_holds_term, timeout=5.0, poll=0.03):
            raise WaitTimeout(f"after 5 s still waiting for the search field to hold {term!r}; the phone shows {describe_screen()}")
        trace("field holds the term")
    # The field changes first, the list a few milliseconds later: a look right after the field has changed
    # can still show the old list (that is how an entry was once "not found"). So when the field was changed
    # the results are waited for until they differ from what they showed before; if they never do (the new
    # term legitimately gives the same list) the wait ends after 0.8 s. Then the value must hold briefly.
    if cleared or term:
        deadline = time.time() + 0.8
        while look() == before and time.time() < deadline:
            time.sleep(0.03)
    try:
        settled(look, quiet=0.1, timeout=12.0, poll=0.03, what=f"the results of the search for {term!r}")
    except WaitTimeout:
        raise WrongState(f"the search for {term!r} did not settle; the phone shows {describe_screen()}") from None
    trace("results settled")
    if latest["count"] is None:
        raise WrongState(f"the search for {term!r} shows no result count; the phone shows {describe_screen()}")
    return latest["count"], latest["rows"]


def open_entry_by_search(title: str) -> dict:
    """The procedure, the way a person does it: type the title into the search, count the results
    (more than one is normal: a title can be the start of another), check for the exact title, open
    that result. No exact match, or more than one, is a data problem (BusinessException), not a
    problem of the phone. Returns what happened, for the log."""
    from errors import DataMismatch

    count, rows = search_for(title)
    exact = [node for text, node in rows if text == title]
    info = {"term": title, "results": count, "visible": len(rows), "exact": len(exact)}
    if len(exact) == 0:
        raise DataMismatch(
            f"searched {title!r}: {count} results ({[t for t, _ in rows][:4]}), none is exactly that title; "
            f"the entry is not in the database on the phone")
    if len(exact) > 1:
        raise DataMismatch(f"searched {title!r}: {len(exact)} entries have exactly that title")
    tap(*centre(bounds(exact[0])))
    if not soft_wait(lambda: state() == State.ENTRY, timeout=8.0):
        raise WrongState(f"the result {title!r} did not open the entry; the phone shows {describe_screen()}")
    return info


LAST_SEARCH: dict = {}


def open_entry(title: str, order: list[str] | None = None) -> bool:
    """Open the entry by searching for it (`order` is not needed any more, it stays for callers)."""
    LAST_SEARCH.clear()
    LAST_SEARCH.update(open_entry_by_search(title))
    return True


def scroll_to_end(limit: int = 12) -> None:
    """Scroll the entry view down until the screen no longer changes."""
    previous = None
    for _ in range(limit):
        current = adb("exec-out", "screencap", "-p", binary=True)
        if current == previous:
            return
        previous = current
        swipe(540, 1700, 540, 500)
        wait_stable()  # the fling has ended: positions unchanged for a moment


def scroll_to_top(limit: int = 12) -> None:
    previous = None
    for _ in range(limit):
        current = adb("exec-out", "screencap", "-p", binary=True)
        if current == previous:
            return
        previous = current
        swipe(540, 500, 540, 1700)
        wait_stable()  # the fling has ended: positions unchanged for a moment
