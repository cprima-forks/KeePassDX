"""Test every entry of the fixture on the phone, with one verdict per scenario of the entry.

The data is the same that builds the fixture: `fixture-spec.json` (entries, scenarios, the links an
entry must show) and the case file. This script holds no entry list, no value and no expectation of
its own.

Each scenario ends in one of three states:
    pass   the app did what the entry expects
    fail   the app did not do what the entry expects (an expectation is never adapted to this)
    error  the script could not test it; the reason is in the report

Setup is manual: open the fixture database on the phone, unlock it, leave KeePassDX on the entry
list. Then:

    uv run python ui_test.py                       # all entries
    uv run python ui_test.py --only tel-url works-capitals
"""

import argparse
from urllib.parse import urlparse
import datetime
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from PIL import ImageChops

import device as dv
import fixture_setup
import fixture_spec
import ocr
import run_facts
import shot_meta
from errors import BusinessException, DataMismatch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))  # publish_png, strip_png_metadata, crop_png
import publish_png  # noqa: E402
from ui import ui

HERE = Path(__file__).parent
RUNS = HERE / "runs"
DATABASE = HERE / os.environ.get("TEL_DATABASE", "kp-test-tel.kdbx")  # TEL_DATABASE with TEL_SPEC: the near-life database

PASS, FAIL, ERROR = "pass", "fail", "error"
LINK_MIN_PIXELS = 100  # a link box must hold at least this many pixels of the link colour
NOLINK_MAX_PIXELS = 20  # a box that is not a link holds at most this many
COLOUR_DISTANCE = 70  # RGB distance that still counts as the link colour
SCREEN_BOTTOM = 2178  # above the "screenshot mode" banner and the navigation bar
BREAKER_ENTRIES = 3  # entries in a row with only errors that stop the run (--breaker; 0: never)
HANDOVER_SECONDS = 600  # how long a handover to the person may wait before the run ends


@dataclass
class Result:
    scenario: str
    state: str
    detail: str = ""
    shots: list[str] = field(default_factory=list)
    attempts: int = 1  # more than 1: a system exception was recovered from and the scenario repeated
    evidence: list[str] = field(default_factory=list)  # screen and dumps saved when it went wrong
    cause: str = ""  # why it ended as it did: "expectation" (fail), "data", "system", "script" (error)


class Abort(Exception):
    """The run cannot go on without a person (a locked database, a modal nobody told us how to
    answer) or the phone keeps failing."""


# --- colour -------------------------------------------------------------------------------------


def _distance(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def _crop(image, box, pad=4):
    x1, y1, x2, y2 = box
    return image.crop((max(0, x1 - pad), max(0, y1 - pad), min(image.width, x2 + pad), min(image.height, y2 + pad)))


def colour_of_link(image, box):
    """The colour of the glyphs and the underline in `box`, or None when the box holds no ink."""
    part = _crop(image, box)
    colours = part.getcolors(maxcolors=part.width * part.height)
    background = max(colours)[1]
    ink = [(n, c) for n, c in colours if _distance(c, background) > 90]
    total = sum(n for n, _ in ink)
    if total < 30:
        return None
    return tuple(int(sum(n * c[i] for n, c in ink) / total) for i in range(3))


def _chroma(colour) -> int:
    return max(colour) - min(colour)


def link_pixels(image, box, colour, pad: int = 4) -> int:
    """Pixels that are the link colour: near it, and coloured. The anti-aliased edge of plain grey
    text lies near the link colour too, but it has no colour of its own, so a pixel also needs at
    least half the chroma of the link colour."""
    part = _crop(image, box, pad)
    need = _chroma(colour) * 0.5
    return sum(
        n for n, c in part.getcolors(maxcolors=part.width * part.height)
        if _distance(c, colour) <= COLOUR_DISTANCE and _chroma(c) >= need
    )


# --- one entry on the phone ---------------------------------------------------------------------


class Entry:
    """Everything the scenarios need to know about one entry that is open on the phone."""

    def __init__(self, runner, entry: dict):
        self.runner = runner
        self.spec = runner.spec
        self.entry = entry
        self.evidence: list[str] = []
        self.id = entry["id"]
        self.case = runner.cases.get(entry.get("valueFrom", ""))
        self.value = fixture_spec.value_of(entry, runner.cases)
        self.field = entry["field"]
        self.links = fixture_spec.links_of(entry, self.case)
        self.tel_links = [link for link in self.links if fixture_spec.is_tel(link)]
        self.other_links = [link for link in self.links if not fixture_spec.is_tel(link)]
        self.out = runner.run_dir / self.id
        self.out.mkdir(parents=True, exist_ok=True)
        self.selection_open = False
        self.region = None
        self.words: list[dict] = []
        self._words_x2: list[dict] | None = None
        self.view_image = None
        self.view_png: Path | None = None
        self.current_scenario = ""  # set by the runner: the sidecar of a screenshot names it

    # evidence
    def save(self, name: str, shot: "dv.Shot", **extra) -> str:
        """Save a captured screenshot with its sidecar `<name>.png.json` (see shot_meta.py): the
        entry, the scenario and the label say what the run was doing. `extra` is passed on, for
        example `clipboard=` for a shot that follows a copy."""
        shot.write(self.out / f"{name}.png", entry=self.id, scenario=self.current_scenario, label=name, **extra)
        return f"{self.id}/{name}.png"

    def annotate(self, name: str, **fields) -> None:
        """Add fields to the sidecar of a screenshot of this entry that was already saved."""
        dv.annotate(self.out / f"{name}.png", **fields)

    def shot(self, name: str, **extra) -> str:
        """A screenshot as evidence. A missing or black one raises ScreenshotFailed (a system
        exception that fails fast); it is never replaced by a note."""
        return self.save(name, dv.capture(name), **extra)

    # opening and locating
    def prepare(self) -> None:
        self.selection_open = False
        self._words_x2 = None
        dv.open_entry(self.id)  # by search; a missing or doubled title raises a DataMismatch
        self.runner.log(entry=self.id, event="opened by search", **dv.LAST_SEARCH)
        if self.field in ("notes", "custom"):  # below the long instructions in Notes
            dv.scroll_to_end()
        root = dv.dump()
        label = {"url": "URL", "custom": self.spec["customFieldName"], "notes": "Notes"}[self.field]
        node = self._value_node(root, label)
        x1, y1, x2, y2 = dv.bounds(node)
        y2 = min(y2, SCREEN_BOTTOM)
        if self.field == "notes":
            y1 = max(y1, y2 - 320)  # the tested value is the last line
        self.region = (x1, y1, x2, y2)
        view = dv.capture("01-view")
        self.view_image = view.image
        self.view_png = self.out / "01-view.png"
        view.write(self.view_png, entry=self.id, scenario="", label="01-view")
        words = ocr.ocr_words(self.view_png)
        self.words = [w for w in words if ocr.inside(w, self.region)]

    def _value_node(self, root, label: str):
        """The value of the field: the text node that follows the field's label."""
        nodes = list(root.iter("node"))
        for i, n in enumerate(nodes):
            if n.get("class", "").endswith("TextView") and n.get("text", "").strip() == label:
                for m in nodes[i + 1 :]:
                    if m.get("class", "").endswith("TextView") and m.get("text"):
                        text = m.get("text")
                        ok = text.rstrip().endswith(self.value) if self.field == "notes" else text == self.value
                        if not ok:
                            raise DataMismatch(f"the field shows {text[:60]!r}, the spec says {self.value!r}")
                        return m
        raise dv.DeviceError(f"no field labelled {label!r} on the entry view")

    @property
    def words_x2(self) -> list[dict]:
        if self._words_x2 is None:
            words = ocr.ocr_words(self.view_png, scale=2)
            self._words_x2 = [w for w in words if ocr.inside(w, self.region)]
        return self._words_x2

    def tel_boxes(self) -> list[tuple[dict, str]]:
        """Box of each expected tel link, in order, and how it was found."""
        numbers = [link["text"] for link in self.tel_links]
        found = ocr.locate_numbers(self.words, numbers)
        if any(box is None for box, _ in found):
            again = ocr.locate_numbers(self.words_x2, numbers)
            found = [(b, h) if b is not None else (again[i][0], again[i][1] + "-x2" if again[i][0] else "")
                     for i, (b, h) in enumerate(found)]
        missing = [numbers[i] for i, (b, _) in enumerate(found) if b is None]
        if missing:
            raise dv.DeviceError(f"no position found for {missing}")
        return found

    def link_word(self, link: dict) -> dict:
        word = ocr.word_for_text(self.words, link["text"]) or ocr.word_for_text(self.words_x2, link["text"])
        if word is None:
            # OCR may misread the characters of the link (an @ as an a). The value says what stands
            # before the link ("mailto:"): position it by that prefix, which OCR reads reliably.
            at = self.value.rfind(link["text"])
            prefix = self.value[:at] if at > 0 else ""
            if prefix:
                word = ocr.box_after(self.words, prefix) or ocr.box_after(self.words_x2, prefix)
        if word is None:
            raise dv.DeviceError(f"no position found for {link['text']!r}")
        return word

    # leaving
    def clean(self) -> None:
        if not dv.back_until(dv.on_entry_clean):
            raise dv.DeviceError(f"could not get back to the entry, focus: {dv.focus()}")
        self.selection_open = False

    def finish(self) -> None:
        if not dv.back_until(dv.on_list):
            raise dv.DeviceError(f"could not get back to the list, focus: {dv.focus()}")


# --- the scenarios ------------------------------------------------------------------------------


def need_colour(e: Entry):
    if e.runner.link_colour is None:
        raise dv.DeviceError("the link colour could not be calibrated")
    return e.runner.link_colour


def launched(e: Entry, x: int, y: int, name: str, expect_change: bool = True) -> tuple[str, str]:
    """Tap at (x, y); the window in front afterwards and the screenshot. Waits for the focus to
    change (up to 3 s; 1.5 s when nothing is expected to open), not for a fixed time."""
    before = dv.focus()
    dv.tap(x, y)

    def changed():
        current = dv.focus()
        return current if current not in (before, "?") else None

    focus = dv.soft_wait(changed, timeout=3.0 if expect_change else 1.5) or dv.focus()
    return focus, e.shot(name)


def long_press_toolbar(point, e: Entry | None = None, name: str = "longpress") -> tuple:
    """Long-press and wait for the selection toolbar (up to 3 s). Returns the screen it was seen on
    and its buttons: (root, nodes), or (None, []) if it never came. With an entry, a screenshot is
    taken right after the press and another one second later, to show whether the selection changes."""
    dv.long_press(*point)
    if e is not None:
        e.shot(f"{name}-0-right-after-press")
        time.sleep(1.0)
        e.shot(f"{name}-1-one-second-later")

    def seen():
        root = dv.dump(windows=True)
        nodes = dv.toolbar_nodes(root)
        return (root, nodes) if nodes else None

    return dv.soft_wait(seen, timeout=3.0, poll=0.5) or (None, [])


def button_names(nodes) -> list[str]:
    return list(dict.fromkeys(n.get("text") for n in nodes))  # the toolbar window is listed twice


CANARY = "KP-CANARY"


def new_canary() -> str:
    """A marker put on the clipboard BEFORE a Copy: if it is still there afterwards, the Copy did not happen.
    That also means that whatever the clipboard held before (a person's own copy) is never mistaken for the
    result, and is never read."""
    marker = f"{CANARY}-{time.time_ns()}"
    dv.clipboard_set(marker)
    return marker


def copied_after(canary: str, timeout: float = 4.0) -> str | None:
    """What the clipboard holds once it is no longer the marker, or None when it stayed the marker (the Copy
    did not happen). Read with phonectl on the phone: no share sheet, no paste."""
    return dv.soft_wait(lambda: (lambda text: text if text not in (None, canary) else None)(dv.clipboard_get()),
                        timeout=timeout, poll=0.5)


def press_call(e: Entry, call, expected: str, tag: str, scenario: str, shots: list[str]) -> Result:
    """Tap Call and compare what the dialer holds with `expected`."""
    dv.tap(*dv.centre(dv.bounds(call)))
    focus = dv.soft_wait(lambda: dv.focus() if dv.APP not in dv.focus() and dv.focus() != "?" else None, timeout=4.0) or dv.focus()
    shots.append(e.shot(f"{tag}-dialer"))
    shown = dv.soft_wait(lambda: (lambda r: r if r[0] else None)(dv.dialed_number(dv.dump(windows=True))),
                         timeout=4.0, poll=0.7)
    e.selection_open = False
    if shown is None:  # the app that opened shows no number the script can read
        return Result(scenario, ERROR, f"in front after Call: {focus}; no number found on its screen", shots)
    got, how = shown
    if got.replace(" ", "") != expected:
        return Result(scenario, FAIL, f"the dialer ({focus.split('/')[0]}) holds {got!r}, expected {expected!r} (read by {how})", shots)
    return Result(scenario, PASS, f"the dialer ({focus.split('/')[0]}) holds {got!r} (read by {how})", shots)


def is_dialer(e: Entry, focus: str) -> bool:
    """Whether `focus` is the phone's dialer: the package detected from Android at the start."""
    package = e.runner.detected.get("dial") or e.runner.detected.get("dialer-role")
    return bool(package) and focus.startswith(package)


def call_flow(e: Entry, point, expected: str, tag: str, scenario: str) -> Result:
    """Long-press at `point`, tap Call, and compare what the dialer holds with `expected`."""
    root, toolbar = long_press_toolbar(point, e, f"{tag}-longpress")
    shots = [e.shot(f"{tag}-longpress")]
    names = button_names(toolbar)
    call = ui.find(root, "android.selection_toolbar.call") if root is not None else None
    e.selection_open = bool(toolbar)
    if call is None:
        return Result(scenario, FAIL, f"the selection toolbar has no Call (it offers: {', '.join(names) or 'nothing'})", shots)
    return press_call(e, call, expected, tag, scenario, shots)


def s_link(e: Entry) -> Result:
    colour = need_colour(e)
    problems, details = [], []
    boxes = dict(zip((l["text"] for l in e.tel_links), e.tel_boxes())) if e.tel_links else {}
    for link in e.links:
        if fixture_spec.is_tel(link):
            word, how = boxes[link["text"]]
        else:
            word, how = e.link_word(link), "ocr"
        px = link_pixels(e.view_image, ocr.box_of(word), colour)
        details.append(f"{link['text'][:24]}: {px} px ({how})")
        if px < min(LINK_MIN_PIXELS, max(25, 8 * len(link["text"]))):
            problems.append(f"{link['text'][:24]!r} is not drawn as a link ({px} px of the link colour)")
    for anchor in ocr.anchors_of(e.words)[: len(e.tel_links)]:
        # the left half of the prefix, without padding: its right edge touches the number
        left_half = (anchor["x"], anchor["y"], anchor["x"] + anchor["w"] // 2, anchor["y"] + anchor["h"])
        px = link_pixels(e.view_image, left_half, colour, pad=0)
        if px > NOLINK_MAX_PIXELS:
            problems.append(f"the prefix {anchor['text']!r} is drawn as a link ({px} px)")
    return Result("UI-LINK", FAIL if problems else PASS, "; ".join(problems or details), ["01-view"] and [f"{e.id}/01-view.png"])


def resolver_rows():
    """The 'Open with' chooser as objects (repository: android.resolver): the screen, its list, its
    button bar, and its rows as (label, row node), in view. The list has no fixed length."""
    root = dv.dump(windows=True)
    lst = ui.find(root, "android.resolver.apps")
    if lst is None:
        raise dv.WrongState("the chooser's list is not on the screen")
    bar = ui.find(root, "android.resolver.button_bar")
    rows = []
    for row in ui.find_all(root, "android.resolver.apps.row"):
        label = ui.find(root, "android.resolver.apps.row.label", under=row)
        if label is not None and label.get("text"):
            rows.append((label.get("text"), row))
    return root, lst, bar, rows


def choose_resolver_row(label: str, limit: int = 6):
    """Find the row of `label` in the chooser, scrolling its list. Returns (row or None, the labels seen,
    whether the end of the list was proven). The list may hold fewer rows than fit (it then does not
    scroll) or more (the lower rows are not in the dump). A row counts only when its centre is clear of
    the button bar, which covers the lower part of the list. The end is proven as for the entry list: a
    drag that moves nothing is checked by a drag the other way; if the rows move neither way it is a
    WrongState, never "the end". The list's own `scrollable` flag is not used: it says false while the
    list scrolls."""
    seen: list[str] = []
    for _ in range(limit):
        _, lst, bar, rows = resolver_rows()
        top, bottom = dv.bounds(lst)[1], dv.bounds(lst)[3]
        floor = dv.bounds(bar)[1] if bar is not None else bottom
        for text, _row in rows:
            if text not in seen:
                seen.append(text)
        for text, row in rows:
            x1, y1, x2, y2 = dv.bounds(row)
            if text == label and (y1 + y2) // 2 <= floor - 20 and y1 >= top:
                return row, seen, False
        positions = [(t, dv.bounds(r)) for t, r in rows]
        x = (dv.bounds(lst)[0] + dv.bounds(lst)[2]) // 2
        dv.swipe(x, floor - 40, x, top + 40, 500)  # towards the later rows
        dv.wait_stable(windows=True)  # the list has stopped moving: positions unchanged for a moment
        if [(t, dv.bounds(r)) for t, r in resolver_rows()[3]] != positions:
            continue
        dv.swipe(x, top + 40, x, floor - 40, 500)  # the probe: the other way
        dv.wait_stable(windows=True)
        if [(t, dv.bounds(r)) for t, r in resolver_rows()[3]] != positions:
            return None, seen, True  # it moved back: the first drag had hit the end
        raise dv.WrongState("the chooser's list moved in neither direction: a drag did not reach it")
    return None, seen, False


def s_tap(e: Entry) -> Result:
    """A short tap on the number must end in the dialer holding the number. With more than one app
    for tel: Android first shows its 'Open with' chooser (ResolverActivity): the scenario reads what it
    offers, chooses the phone's dialer with Just once (never Always: that would change the phone's
    settings), and then reads the number the dialer holds. It never presses Call."""
    box, _ = e.tel_boxes()[0]
    focus, shot = launched(e, *dv.centre(ocr.box_of(box)), "tap")
    shots = [shot]
    if dv.APP in focus:
        return Result("UI-TAP", FAIL, f"the tap did not leave the app: {focus}", shots)
    expected = e.tel_links[0]["target"][4:]  # the target without "tel:"
    notes = [f"in front after the tap: {focus}"]
    if "ResolverActivity" in focus:
        dialer = ui.systems.get(ui.roles.get("dialer", ""), {})
        label = dialer.get("chooser_label")
        if not label:
            raise KeyError("the dialer's system file has no chooser_label: the script cannot tell which row is the dialer")
        row, seen, complete = choose_resolver_row(label)
        count = f"{len(seen)}" if complete else f"at least {len(seen)}"
        notes.append(f"the chooser offers {count} app(s): " + ", ".join(seen))
        if row is None:
            return Result("UI-TAP", FAIL, "; ".join(notes) + f"; the dialer ({label!r}) is not offered", shots)
        x1, y1, x2, y2 = dv.bounds(row)
        _, _, bar, _ = resolver_rows()[:4]
        floor = dv.bounds(bar)[1] if bar is not None else y2
        dv.system_tap((x1 + x2) // 2, (y1 + min(y2, floor)) // 2)  # the row's visible part: the button bar covers its lower rows
        once = dv.soft_wait(lambda: ui.find(dv.dump(windows=True), "android.resolver.just_once"), timeout=4.0)
        if once is None:
            return Result("UI-TAP", FAIL, "; ".join(notes) + f"; no 'Just once' button after choosing {label!r}", shots)
        dv.system_tap(*dv.centre(dv.bounds(once)))  # Just once: nothing becomes a default
        if dv.soft_wait(lambda: "ResolverActivity" not in dv.focus(), timeout=2.0) is None:
            dv.system_tap(*dv.centre(dv.bounds(once)))  # the chooser is still there: once more
        notes.append(f"chose {label!r}, Just once")
    else:
        notes.append("no chooser: an app opened directly")
    now = dv.soft_wait(lambda: dv.focus() if is_dialer(e, dv.focus()) else None, timeout=6.0)
    shots.append(e.shot("tap-dialer"))
    if now is None:
        return Result("UI-TAP", FAIL, "; ".join(notes) + f"; the dialer did not come to the front, {dv.focus()} did", shots)
    shown = dv.soft_wait(lambda: (lambda r: r if r[0] else None)(dv.dialed_number(dv.dump(windows=True))), timeout=4.0, poll=0.7)
    if shown is None:
        return Result("UI-TAP", ERROR, "; ".join(notes) + "; the dialer shows no number the script can read", shots)
    got, how = shown
    if got.replace(" ", "") != expected:
        return Result("UI-TAP", FAIL, "; ".join(notes) + f"; the dialer holds {got!r}, expected {expected!r} (read by {how})", shots)
    return Result("UI-TAP", PASS, "; ".join(notes) + f"; the dialer ({now.split('/')[0]}) holds {got!r} (read by {how})", shots)


def s_longpress(e: Entry) -> Result:
    if e.tel_links:
        box, _ = e.tel_boxes()[0]
        word = box
    else:
        word = e.link_word(e.links[0])
    canary = new_canary()  # on the clipboard before the Copy
    root, toolbar = long_press_toolbar(dv.centre(ocr.box_of(word)), e, "longpress")
    shot = e.shot("longpress")  # the toolbar with the selection
    names = button_names(toolbar)
    e.selection_open = bool(names)
    if not names:
        return Result("UI-LONGPRESS", FAIL, "no selection toolbar after the long-press", [shot])
    expected = (e.tel_links or e.links)[0]["text"]  # the link that was pressed: its text is what must be copied
    copy = ui.find(root, "android.selection_toolbar.copy")
    if copy is None:  # nothing to press: said as it is, the toolbar's buttons are in the detail
        e.selection_open = False
        e.annotate("longpress", clipboard={"value": None, "expected": expected, "toolbar": names, "after": "none: no Copy offered"})
        return Result("UI-LONGPRESS", FAIL, f"the toolbar offers no Copy (it offers: {', '.join(names)})", [shot])
    dv.tap(*dv.centre(dv.bounds(copy)))  # press Copy
    copied = copied_after(canary)
    e.selection_open = False  # Copy closes the selection
    e.runner.log(entry=e.id, event="clipboard", after="Copy in the selection toolbar", copied=copied, expected=expected, toolbar=names)
    # the picture was taken before the Copy: the sidecar gets the clipboard now
    e.annotate("longpress", clipboard={"value": copied, "expected": expected, "toolbar": names, "after": "Copy in the selection toolbar",
                                       "read_by": "phonectl clip-get, with a marker set before the Copy"})
    if copied is None:
        return Result("UI-LONGPRESS", ERROR, f"Copy did not change the clipboard: the marker is still there (toolbar: {', '.join(names)})", [shot])
    if copied != expected:
        return Result("UI-LONGPRESS", FAIL, f"copied {copied!r}, expected {expected!r}; toolbar: {', '.join(names)}", [shot])
    return Result("UI-LONGPRESS", PASS, f"copied {copied!r}; toolbar: {', '.join(names)}", [shot])


def s_call(e: Entry) -> Result:
    expected = e.tel_links[0]["target"][4:]
    if e.selection_open:
        root = dv.dump(windows=True)
        if not dv.toolbar_nodes(root):
            e.selection_open = False
    if not e.selection_open:
        box, _ = e.tel_boxes()[0]
        return call_flow(e, dv.centre(ocr.box_of(box)), expected, "call", "UI-CALL")
    # a long-press is still on the screen
    call = ui.find(root, "android.selection_toolbar.call")
    if call is None:
        offers = ", ".join(button_names(dv.toolbar_nodes(root)))
        return Result("UI-CALL", FAIL, f"the selection toolbar has no Call (it offers: {offers})", [f"{e.id}/longpress.png"])
    return press_call(e, call, expected, "call", "UI-CALL", [])


def s_longpress_two(e: Entry) -> Result:
    if len(e.tel_links) < 2:
        raise dv.DeviceError("the entry expects fewer than two tel links")
    box, _ = e.tel_boxes()[1]
    return call_flow(e, dv.centre(ocr.box_of(box)), e.tel_links[1]["target"][4:], "second", "UI-LONGPRESS-TWO")


def second_line_word(e: Entry) -> dict:
    anchor = ocr.anchors_of(e.words)[0]
    below = [w for w in e.words if w["y"] >= anchor["y"] + 0.8 * anchor["h"] and w is not anchor]
    if not below:
        raise dv.DeviceError("no word on a second line of the value")
    return min(below, key=lambda w: (w["y"], w["x"]))


def s_wrap(e: Entry) -> Result:
    word = second_line_word(e)
    x, y = dv.centre(ocr.box_of(word))
    focus, shot = launched(e, x, y, "wrap-tap")
    tapped = PASS if dv.APP not in focus else FAIL
    e.clean()
    result = call_flow(e, (x, y), e.tel_links[0]["target"][4:], "wrap", "UI-WRAP")
    result.detail = f"tap on the second line: {'launched ' + focus if tapped == PASS else 'nothing launched'}; long-press: {result.detail}"
    if tapped == FAIL and result.state == PASS:
        result.state = FAIL
    result.shots = [shot, *result.shots]
    return result


def probes(e: Entry) -> list[dict]:
    """Where the number would be if the value were a link: the word right of each `tel:` word, else
    the first word with a digit."""
    found = [w for w in (ocr.right_of(a, e.words) for a in ocr.anchors_of(e.words)) if w]
    if not found:
        found = [w for w in e.words if any(c.isdigit() for c in w["text"])][:1]
    if not found:
        found = [w for w in e.words_x2 if any(c.isdigit() for c in w["text"])][:1]
    if not found:
        raise dv.DeviceError("no word of the value could be located")
    return found


def s_nolink(e: Entry) -> Result:
    colour = need_colour(e)
    problems, details, shots = [], [], []
    for n, probe in enumerate(probes(e)):
        px = link_pixels(e.view_image, ocr.box_of(probe), colour)
        details.append(f"{probe['text'][:24]!r}: {px} px")
        if px > NOLINK_MAX_PIXELS:
            problems.append(f"{probe['text'][:24]!r} is drawn as a link ({px} px of the link colour)")
        before = dv.focus()
        focus, shot = launched(e, *dv.centre(ocr.box_of(probe)), f"tap-{n}", expect_change=False)
        shots.append(shot)
        if focus != before or dv.toolbar_present():
            problems.append(f"a tap on {probe['text'][:24]!r} did something: in front {focus}")
            e.clean()
    return Result("UI-NOLINK", FAIL if problems else PASS, "; ".join(problems or details), shots)


def s_notel(e: Entry) -> Result:
    word = e.link_word(e.other_links[0])
    x = word["x"] + word["w"] - 12  # the right end, where the number inside the address is
    y = word["y"] + word["h"] // 2
    focus, shot = launched(e, x, y, "notel-tap")
    if is_dialer(e, focus):
        return Result("UI-NOTEL", FAIL, f"the tap opened the dialer ({focus}), there is a phone link inside the address", [shot])
    if dv.APP in focus:
        return Result("UI-NOTEL", FAIL, "the tap opened nothing, the address is not a link there", [shot])
    problem, seen = browser_shows(e, e.other_links[0]["target"], focus)
    return Result("UI-NOTEL", FAIL if problem else PASS, problem or f"the tap opened {seen}, not the dialer", [shot])


def browser_shows(e: Entry, target: str, focus: str) -> tuple[str | None, str]:
    """Whether the browser that opened shows the link's address. Returns (problem or None, what was
    seen). The address box of the browser (repository element browser.page.address_box) carries the
    opened address; the host of the link target must be in it. For a browser the repository does not
    know, only the app that came to the front is reported."""
    if "browser" not in ui.roles or not focus.startswith(e.runner.detected.get("web", "\0")):
        return None, focus
    host = urlparse(target).netloc.lower()
    box = dv.soft_wait(lambda: ui.find(dv.dump(), "browser.page.address_box"), timeout=10.0, poll=1.0)
    if box is None:
        raise dv.DeviceError(f"the browser ({focus}) shows no address box; the phone shows {dv.describe_screen()}")
    desc = box.get("content-desc", "")
    if host not in desc.lower():
        return f"the browser shows the address {desc!r}, expected the host {host!r}", desc
    return None, f"{focus.split('/')[0]} at {desc.strip()!r}"


def s_web(e: Entry) -> Result:
    link = next(l for l in e.links if l["target"].lower().startswith("http"))
    word = e.link_word(link)
    focus, shot = launched(e, *dv.centre(ocr.box_of(word)), "web-tap")
    if dv.APP in focus:
        return Result("UI-WEB", FAIL, "the tap opened nothing", [shot])
    problem, seen = browser_shows(e, link["target"], focus)
    return Result("UI-WEB", FAIL if problem else PASS, problem or f"the tap opened {seen}", [shot])


def s_mail(e: Entry) -> Result:
    link = next(l for l in e.links if l["target"].lower().startswith("mailto:"))
    word = e.link_word(link)
    problems = []
    colour = need_colour(e)
    for w in e.words:
        if w["text"].lower().endswith("mailto:"):
            px = link_pixels(e.view_image, ocr.box_of(w), colour)
            if px > NOLINK_MAX_PIXELS:
                problems.append(f"the prefix {w['text']!r} is drawn as a link ({px} px)")
    focus, shot = launched(e, *dv.centre(ocr.box_of(word)), "mail-tap")
    seen = focus
    if dv.APP in focus:
        problems.append("the tap opened nothing")
    elif "mailer" in ui.roles and focus.startswith(e.runner.detected.get("mail", "\0")):
        # the composer shows who the mail is addressed to: it must be the link's address
        address = link["target"][len("mailto:"):].split("?")[0]
        to = dv.soft_wait(lambda: ui.find(dv.dump(), "mailer.compose.to"), timeout=10.0, poll=1.0)
        if to is None:
            raise dv.DeviceError(f"the composer ({focus}) shows no recipient field; the phone shows {dv.describe_screen()}")
        recipients = to.get("text", "")
        seen = f"{focus.split('/')[0]} to {recipients.strip()!r}"
        if address.lower() not in recipients.lower():
            problems.append(f"the composer is addressed to {recipients!r}, expected {address!r}")
    return Result("UI-MAIL", FAIL if problems else PASS, "; ".join(problems) or f"the tap opened {seen}", [shot])


def s_reopen(e: Entry) -> Result:
    e.clean()
    before = _crop(e.view_image, e.region, 0)
    e.finish()
    dv.open_entry(e.id)
    dv.wait_stable()  # the entry is drawn and nothing moves, before the picture is taken
    captured = dv.capture("reopen")
    shot = e.save("reopen", captured)
    after = _crop(captured.image, e.region, 0)
    differing = ImageChops.difference(before, after).getbbox()  # None when identical
    if differing:
        return Result("UI-REOPEN", FAIL, f"the value differs from the first view, inside {differing}", [shot])
    return Result("UI-REOPEN", PASS, "the value is pixel-identical to the first view", [shot])


def s_edit(e: Entry) -> Result:
    dv.tap(*dv.centre(dv.bounds(ui.require(dv.dump(), "keepassdx.entry.edit"))))
    # Editing asks the person to verify first (a system prompt). The explicit wait lets the table of
    # dialogs answer it, which for this prompt means: wait for the person.
    dv.wait_until(lambda: dv.state() == dv.State.EDIT, timeout=30, what="the edit screen")

    def edit_texts() -> list[str]:
        return [n.get("text", "") for n in ui.find_all(dv.dump(), "keepassdx.edit.text_field")]

    dv.soft_wait(lambda: e.value in edit_texts(), timeout=8.0, poll=1.0)  # the form needs a moment
    texts = edit_texts()
    shot = e.shot("edit")
    e.clean()  # back out of edit mode without saving
    if e.value in texts:
        return Result("UI-EDIT", PASS, "edit mode shows the plain value", [shot])
    return Result("UI-EDIT", FAIL, f"edit mode shows {texts[:3]!r}, expected {e.value!r}", [shot])


def s_copy(e: Entry) -> Result:
    """The copy button next to the value, in the entry view: press it and read what it put on the clipboard
    (phonectl, with a marker set before). It must be the field's value."""
    label = {"url": "URL", "custom": e.spec["customFieldName"], "notes": "Notes"}[e.field]
    canary = new_canary()
    root = dv.dump()
    value = ui.value_after_label(root, label)
    if value is None:
        return Result("UI-COPY", ERROR, f"no field labelled {label!r} on the entry view", [])
    vb = dv.bounds(value)
    buttons = [b for b in ui.find_all(root, "keepassdx.entry.fields.copy_button")
               if vb[1] - 110 <= (dv.bounds(b)[1] + dv.bounds(b)[3]) // 2 <= vb[3]]  # the button of this field's row
    if not buttons:
        return Result("UI-COPY", FAIL, f"the field {label!r} has no copy button on the screen", [])
    dv.tap(*dv.centre(dv.bounds(buttons[0])))
    copied = copied_after(canary)
    shot = e.shot("copy")
    e.runner.log(entry=e.id, event="clipboard", after="the copy button of the field", copied=copied, expected=e.value)
    e.annotate("copy", clipboard={"value": copied, "expected": e.value, "after": f"the copy button of the field {label!r}",
                                  "read_by": "phonectl clip-get, with a marker set before the Copy"})
    if copied is None:
        return Result("UI-COPY", ERROR, "the copy button did not change the clipboard: the marker is still there", [shot])
    if copied != e.value:
        return Result("UI-COPY", FAIL, f"copied {copied!r}, expected {e.value!r}", [shot])
    return Result("UI-COPY", PASS, f"copied {copied!r}", [shot])


SCENARIOS = {
    "UI-LINK": s_link,
    "UI-TAP": s_tap,
    "UI-LONGPRESS": s_longpress,
    "UI-CALL": s_call,
    "UI-LONGPRESS-TWO": s_longpress_two,
    "UI-WRAP": s_wrap,
    "UI-NOLINK": s_nolink,
    "UI-NOTEL": s_notel,
    "UI-WEB": s_web,
    "UI-MAIL": s_mail,
    "UI-REOPEN": s_reopen,
    "UI-EDIT": s_edit,
    "UI-COPY": s_copy,
}


# --- the run ------------------------------------------------------------------------------------


class Runner:
    def __init__(self, only: list[str] | None, run_setup: bool, environment: str):
        self.spec = fixture_spec.load_spec()
        self.cases = fixture_spec.load_cases(self.spec)
        self.env = fixture_spec.load_environment(environment)  # the phone and its apps
        dv.configure(self.spec["dialogs"], self.env)
        self.detected = dv.detect_handlers()  # the default apps, asked from Android
        self.roles = ui.bind_roles(self.detected)  # dialer, browser, mailer, sms -> a system file
        self.unbound_roles = dict(ui.unbound)  # a detected app that has no system file: said in the report
        self.order = [e["id"] for e in self.spec["entries"]]  # the order of the list on the phone
        self.entries =[e for e in self.spec["entries"] if not only or e["id"] in only]
        self.run_setup = run_setup
        self.original_prefs: dict | None = None
        self.link_colour = None
        sha = hashlib.sha256(DATABASE.read_bytes()).hexdigest()
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.run_dir = RUNS / f"{stamp}-{sha[:8]}"
        self.run_dir.mkdir(parents=True)
        self.meta = {
            "started": datetime.datetime.now().isoformat(timespec="seconds"),
            "fixture_sha256": sha,
            "device": dv.adb("shell", "getprop", "ro.product.model").strip(),
            "android": dv.adb("shell", "getprop", "ro.build.version.release").strip(),
            "environment": self.env["name"],
            "long_press_ms": dv.LONG_PRESS_MS,
            "detected_apps": self.detected,
            "roles": self.roles,
            "roles_without_system_file": self.unbound_roles,
            "app_version": next((l.split("=")[1] for l in dv.adb("shell", "dumpsys", "package", dv.ENV["target"]).splitlines() if "versionName" in l), "?"),
        }
        # the run's name is needed from the first picture on: it names the folder on the phone. The rest
        # of what every sidecar embeds is collected at the start of the run (run_facts.collect).
        dv.SHOT_STATIC.clear()
        dv.SHOT_STATIC.update(context={"run": self.run_dir.name, "environment": self.env["name"]})

    def log(self, **fields) -> None:
        """One JSON line per event, in run.log.jsonl: what was done, when, and how it ended."""
        fields = {"t": datetime.datetime.now().isoformat(timespec="seconds"), **fields}
        with (self.run_dir / "run.log.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(fields, ensure_ascii=False) + "\n")

    def start(self) -> None:
        """Initialize, with the UI dumped if anything in it fails (see dv.dump_on_error): a run that
        cannot start comes with what the phone showed."""
        with dv.dump_on_error(self.run_dir / "_start", "start-error"):
            self._start()

    def _start(self) -> None:
        """Initialize, the RPA way: close the automated systems, start the app fresh, open and unlock
        the fixture, verify it (see fixture_setup). With `--no-setup` a person has opened the fixture
        and the run starts from the list."""
        if self.meta["device"] != self.env["device"]["model"]:
            raise Abort(f"the environment {self.env['name']!r} is for a {self.env['device']['model']}, "
                        f"the phone is a {self.meta['device']!r}")
        # the app's settings as they are before the test touches anything: the settings that the test
        # changes by using the app are put back at End (restoreAtEnd in the profile)
        self.original_prefs = fixture_setup.read_app_preferences(self.env["target"])
        # the device, the default apps, the app under test with its APK checksum, the code: asked once,
        # written to env.raw.json and env.json, and embedded in the sidecar of every screenshot
        run_facts.collect(self.run_dir, self.run_dir.name, self.env, self.detected, self.meta["fixture_sha256"],
                          fixture_spec.HERE / "fixture-spec.json", (fixture_spec.HERE / self.spec["casesFile"]).resolve())
        self.log(event="setup", step="facts collected", files=["env.raw.json", "env.json"])
        try:
            if self.run_setup:
                setup = fixture_setup.initialize(self.spec, self.env, self.detected, DATABASE, self.log)
                self.order = setup.order
                self.meta["phone_file"] = setup.file_name
            else:
                self.order = fixture_setup.file_order(DATABASE, self.spec["database"]["password"], self.meta["fixture_sha256"])
                if not dv.in_app():
                    raise Abort(f"KeePassDX is not in front: {dv.focus()}")
                self.to_list()
        except fixture_setup.SetupError as problem:
            raise Abort(f"setup: {problem}")
        except dv.NeedsPerson as problem:
            raise Abort(f"a person is needed: {problem}")
        except dv.DeviceError as problem:
            raise Abort(f"could not set the fixture up: {problem}")
        try:
            self.meta["fingerprint"] = fixture_setup.preflight(self.env, self.log)
        except fixture_setup.SetupError as problem:
            raise Abort(str(problem))
        run_facts.add_preflight(self.run_dir, self.meta["fingerprint"])
        # the repo file must be the fixture of the spec, or the spec and the file have drifted apart
        wanted = {e["id"] for e in self.spec["entries"]}
        missing, extra = sorted(wanted - set(self.order)), sorted(set(self.order) - wanted)
        self.meta["entries_in_file"] = len(self.order)
        if missing or extra:
            raise Abort(f"the fixture file does not match the spec (run populate.py): missing {missing[:5]}, extra {extra[:5]}")
        self.calibrate()

    def reinitialize(self) -> None:
        """The same Initialize in the middle of a run, when the database locked itself."""
        self.log(event="re-initialising", reason="the database is locked")
        setup = fixture_setup.initialize(self.spec, self.env, self.detected, DATABASE, self.log)
        self.order = setup.order

    def calibrate(self) -> None:
        """The colour of a link, from the first entry whose URL value must be a tel link."""
        entry = next((e for e in self.spec["entries"]
                      if e["field"] == "url" and any(fixture_spec.is_tel(l) for l in fixture_spec.links_of(e, self.cases.get(e.get("valueFrom", ""))))), None)
        if entry is None:
            return
        probe = Entry(self, entry)
        probe.out = self.run_dir / "_calibration"
        probe.out.mkdir(exist_ok=True)
        try:
            probe.prepare()
            box, _ = probe.tel_boxes()[0]
            self.link_colour = colour_of_link(probe.view_image, ocr.box_of(box))
        except dv.ScreenshotFailed:
            raise  # no evidence, no run: fail fast
        except Exception as problem:  # the report says so, every colour check becomes an error
            self.meta["calibration_error"] = str(problem)
        finally:
            try:
                probe.finish()
            except dv.DeviceError:
                pass
        self.meta["link_colour"] = self.link_colour

    # --- the work item (an entry) as a transaction, the way RPA frameworks do it -------------------
    #
    #   business exception  the data or the process is wrong (the entry does not hold what the spec
    #                       says): never repeated, a repeat would read the same data. The scenario
    #                       ends as an error with cause "data".
    #   fail                the entry's expectation was not met: a result, never repeated.
    #   system exception   the phone or the app was in the wrong state (a lock screen, a dialog that
    #                       hid the target, the app gone to the background): the WHOLE item is
    #                       repeated from a clean slate: re-initialise to the entry list, a new Entry
    #                       object (no cached screen, no open selection), every scenario again. The
    #                       results of the failed attempt are discarded, not mixed with the new ones.
    #   needs a person     a locked database, a modal nobody described: the run stops.

    MAX_ATTEMPTS = 2  # one repeat after a system exception

    def hand_over(self, reason: str) -> None:
        """Handover to the person, a valid transition of the process: say what is needed, wait until
        the phone shows that the person has acted (no lock, no modal), then go on. Nobody acting
        within HANDOVER_SECONDS ends the run."""
        self.log(event="handover", reason=reason)
        print(f"   HANDOVER to you: {reason} (waiting up to {HANDOVER_SECONDS} s)", flush=True)
        if not dv.soft_wait(lambda: not dv.person_needed(), timeout=HANDOVER_SECONDS, poll=3.0):
            raise Abort(f"nobody resolved the handover within {HANDOVER_SECONDS} s: {reason}")
        self.log(event="handover resolved")
        print("   handover resolved, going on", flush=True)

    def to_list(self) -> None:
        """Bring the app to the entry list; a handover on the way is waited out."""
        while True:
            try:
                dv.recover_to_list()
                return
            except dv.Locked:  # no person needed: Initialize unlocks the fixture again
                self.reinitialize()
            except dv.NeedsPerson as problem:
                self.hand_over(str(problem))

    def reinit(self, e: Entry, reason: str) -> None:
        """Back to the clean start state after a system exception: the evidence is saved, then every
        modal is answered and the app is brought back to the entry list."""
        e.evidence = dv.evidence(e.out, f"error-{len(list(e.out.glob('error-*-dump.xml'))) + 1}")
        self.log(entry=e.id, event="system exception", reason=reason, evidence=e.evidence)
        self.to_list()
        self.log(entry=e.id, event="re-initialised")

    def scenario(self, e: Entry, name: str) -> Result:
        """One scenario. A system exception is not caught here: it ends the attempt of the item."""
        e.current_scenario = name
        try:
            if not (name == "UI-CALL" and e.selection_open):  # a Call follows its own long-press
                e.clean()
            result = SCENARIOS[name](e)
            if result.state == FAIL:
                result.cause = "expectation"
            return result
        except BusinessException as problem:
            e.evidence = dv.evidence(e.out, "error-data")
            return Result(name, ERROR, f"{type(problem).__name__}: {problem}", evidence=e.evidence, cause="data")
        except dv.SystemException:
            raise
        except Exception as problem:  # a bug of this script, not of the phone or the app
            e.evidence = dv.evidence(e.out, "error-script")
            try:
                e.clean()
            except dv.SystemException:
                pass
            return Result(name, ERROR, f"{type(problem).__name__}: {problem}", evidence=e.evidence, cause="script")

    def transaction(self, e: Entry, scenarios: list[str], done: list[Result]) -> None:
        """Open the entry and run its scenarios; results go to `done` as they come."""
        e.prepare()
        for name in scenarios:
            result = self.scenario(e, name)
            self.log(entry=e.id, scenario=name, state=result.state, cause=result.cause, detail=result.detail, shots=result.shots)
            done.append(result)

    def run_entry(self, entry: dict) -> list[Result]:
        scenarios = fixture_spec.scenarios_of(entry, self.cases.get(entry.get("valueFrom", "")))
        self.log(entry=entry["id"], event="start", scenarios=scenarios)
        attempt = 0
        while True:
            attempt += 1
            e = Entry(self, entry)  # a clean slate: nothing is carried over from an earlier attempt
            done: list[Result] = []
            try:
                self.transaction(e, scenarios, done)
                for result in done:
                    result.attempts = attempt
                self.to_list()  # leave the item at the start state, too
                return done
            except BusinessException as problem:  # the entry does not hold what the spec says
                e.evidence = dv.evidence(e.out, "error-data")
                self.log(entry=e.id, event="business exception", reason=str(problem), evidence=e.evidence)
                return [Result(s, ERROR, f"{type(problem).__name__}: {problem}", evidence=e.evidence, cause="data", attempts=attempt) for s in scenarios]
            except dv.NeedsPerson as problem:
                # a handover is no failure: wait for the person, start the item again from a clean
                # slate, and do not use up an attempt
                self.hand_over(f"{e.id}: {problem}")
                self.reinit(e, f"after a handover: {problem}")
                attempt -= 1
                continue
            except dv.SystemException as problem:
                reason = f"{type(problem).__name__}: {problem}"
                self.reinit(e, reason)
                if isinstance(problem, dv.ScreenshotFailed) and attempt >= self.MAX_ATTEMPTS:
                    # a run without its evidence has no use: stop here instead of going on
                    raise Abort(f"{e.id}: the screenshot failed twice: {problem}")
                if attempt < self.MAX_ATTEMPTS:
                    self.log(entry=e.id, event="repeating the item from a clean slate", attempt=attempt + 1)
                    continue
                # the last attempt failed too: report what it got, the failed scenario and the rest as errors
                failed = scenarios[len(done)]
                rest = scenarios[len(done) + 1:]
                for result in done:
                    result.attempts = attempt
                done.append(Result(failed, ERROR, reason, evidence=e.evidence, cause="system", attempts=attempt))
                done += [Result(s, ERROR, f"not run: {failed} ended in a system exception", cause="system", attempts=attempt) for s in rest]
                return done
        raise AssertionError("unreachable")

    def run(self) -> dict:
        report = {"meta": self.meta, "entries": {}}
        failing_in_a_row = 0
        try:
            for entry in self.entries:
                results = self.run_entry(entry)
                states = {r.state for r in results}
                state = FAIL if FAIL in states else ERROR if ERROR in states else PASS
                report["entries"][entry["id"]] = {"state": state, "scenarios": [r.__dict__ for r in results]}
                print(f"{state.upper():5} {entry['id']:50} " + "; ".join(f"{r.scenario} {r.state}" for r in results), flush=True)
                # circuit breaker: the phone is failing, not the app; more entries would only repeat it
                failing_in_a_row = failing_in_a_row + 1 if all(r.state == ERROR for r in results) else 0
                if BREAKER_ENTRIES and failing_in_a_row >= BREAKER_ENTRIES:
                    raise Abort(f"{failing_in_a_row} entries in a row ended only in errors; the phone is in a state the script cannot work with")
        except Abort as problem:
            self.meta["aborted"] = str(problem)
            shown = dv.evidence(self.run_dir / "_abort", "abort")  # what the UI showed when the run stopped
            self.log(event="aborted", reason=str(problem), evidence=shown)
            print(f"\nABORTED: {problem}", flush=True)
        self.meta["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
        # every screenshot has its raw file and its sidecar; one without is not evidence
        self.meta["sidecars_missing"] = shot_meta.verify_run(self.run_dir)
        # the pictures for publication: cropped at the measured status bar, metadata stripped, verified,
        # in <run>/published/ with their provenance (cprima-fork/tools/publish_png.py). The originals stay as taken.
        self.meta["published"] = publish_png.publish_run(self.run_dir)
        return report


def write_report(runner: Runner, report: dict) -> None:
    (runner.run_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    counts = {s: sum(1 for e in report["entries"].values() if e["state"] == s) for s in (PASS, FAIL, ERROR)}
    lines = [f"# UI test run {runner.run_dir.name}", "",
             f"Fixture SHA-256 `{runner.meta['fixture_sha256']}`, {runner.meta['device']}, Android {runner.meta['android']}, app {runner.meta['app_version']}.", "",
             f"**{len(report['entries'])} entries: {counts[PASS]} pass, {counts[FAIL]} fail, {counts[ERROR]} error.**", "",
             "A fail means the entry's expectation was not met (never repeated). An error has a cause: "
             "`data` (the phone does not hold what the spec says), `system` (the phone or app was in the wrong "
             "state, recovered and repeated once), `script` (a bug of this script).", "",
             "| Entry | Scenario | State | Cause | Tries | Detail |", "|---|---|---|---|---|---|"]
    for entry_id, entry in report["entries"].items():
        for s in entry["scenarios"]:
            lines.append(f"| `{entry_id}` | {s['scenario']} | {s['state']} | {s.get('cause', '')} | {s.get('attempts', 1)} | {s['detail'].replace('|', '/')} |")
    (runner.run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n{len(report['entries'])} entries: {counts[PASS]} pass, {counts[FAIL]} fail, {counts[ERROR]} error")
    print(f"report: {runner.run_dir / 'report.md'}")
    missing = report["meta"].get("sidecars_missing") or []
    if missing:
        print(f"INTEGRITY: {len(missing)} screenshot file(s) lack a raw file or a sidecar: {missing[:5]}")
    else:
        print("integrity: every screenshot has its raw file and its sidecar")
    published = report["meta"].get("published") or {}
    print(f"published: {published.get('count', 0)} cropped and stripped picture(s) in {runner.run_dir / 'published'}")
    for error in published.get("errors", []):
        print(f"NOT PUBLISHED: {error['file']}: {error['error']}")


def main() -> int:
    global BREAKER_ENTRIES
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--only", nargs="*", help="entry ids to test (default: all)")
    parser.add_argument("--environment", default="cprima-dev",
                        help="the profile of the phone and its apps (environments/<name>.json)")
    parser.add_argument("--no-setup", action="store_true",
                        help="skip Initialize: a person has opened and unlocked the fixture on the phone")
    parser.add_argument("--long-press-ms", type=int, default=dv.LONG_PRESS_MS,
                        help=f"how long the finger stays down on a long-press (default {dv.LONG_PRESS_MS})")
    parser.add_argument("--breaker", type=int, default=BREAKER_ENTRIES,
                        help="entries in a row with only errors that stop the run; 0: never (default %(default)s)")
    parser.add_argument("--leave-open", action="store_true",
                        help="skip End: leave the apps open (End force-stops them, which locks the database)")
    args = parser.parse_args()
    dv.LONG_PRESS_MS = args.long_press_ms
    BREAKER_ENTRIES = args.breaker
    runner = Runner(args.only, run_setup=not args.no_setup, environment=args.environment)
    try:
        runner.start()
    except (Abort, dv.SystemException) as problem:
        shown = getattr(problem, "ui_evidence", [])
        print(f"cannot start: {problem}" + (f"\n   the UI was dumped: {runner.run_dir / '_start'} {shown}" if shown else ""))
        runner.log(event="cannot start", reason=str(problem), evidence=shown)
        return 2
    try:
        report = runner.run()
        write_report(runner, report)
    finally:
        if runner.run_setup and not args.leave_open:  # End: close the automated systems again
            fixture_setup.finish(runner.env, runner.detected, runner.log, runner.original_prefs)
        if not args.leave_open:  # the pulled copies are the record; no screenshot stays on the phone
            dv.remove_phone_shots()
    if "aborted" in report["meta"]:
        return 3
    if report["meta"].get("sidecars_missing"):
        return 4
    if (report["meta"].get("published") or {}).get("errors"):
        return 5
    return 0 if all(e["state"] == PASS for e in report["entries"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
