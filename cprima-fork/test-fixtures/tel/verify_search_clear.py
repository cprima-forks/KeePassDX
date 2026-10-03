"""Verify on the phone that the search field of KeePassDX is emptied by a tap on its 'x'.

One pass, every step timed and announced as it happens (run it with `python -u`):

  0. how long one screen read takes on this phone;
  1. Initialize: open KeePassDX with the fixture and unlock it (the runner's own);
  2. search for a term: the field holds it, the 'x' is on the screen (its id is shown);
  3. search for a second term: device.search_for taps the 'x' first; the field holds exactly the second term;
  4. a tap on the 'x' empties the field: the 'x' is gone;
  5. an empty search shows every entry of the file;
  6. no Backspace and no Delete was sent by the search code.

Every step has a time budget (STEP_SECONDS). A step that runs longer is reported as too slow and the
script goes to its End step (apps closed, the setting restored). Taps no Save, Call or Send.

    uv run python -u verify_search_clear.py
"""

import sys
import threading
import time
from pathlib import Path

import device as dv
import fixture_setup as fs
import fixture_spec
from ui import ui

HERE = Path(__file__).parent
STEP_SECONDS = 90
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("   ok    " if ok else "   FAIL  ") + name + (f": {detail}" if detail else ""), flush=True)
    if not ok:
        failures.append(name)


class TooSlow(Exception):
    pass


def step(name: str, work, budget: int = STEP_SECONDS):
    """Run `work` with a time budget; announce it, time it, return its result."""
    print(f"[{time.strftime('%H:%M:%S')}] {name} ...", flush=True)
    box: dict = {}

    def runner():
        try:
            box["value"] = work()
        except BaseException as problem:  # reported by the caller of step()
            box["error"] = problem

    started = time.time()
    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(budget)
    took = time.time() - started
    if thread.is_alive():
        raise TooSlow(f"{name}: still running after {budget} s")
    if "error" in box:
        raise box["error"]
    print(f"           took {took:.1f} s", flush=True)
    return box.get("value")


def cross_info() -> dict | None:
    node = ui.find(dv.dump(), "keepassdx.search.clear")
    if node is None:
        return None
    return {"id": node.get("resource-id"), "desc": node.get("content-desc"), "class": node.get("class", "").split(".")[-1],
            "bounds": node.get("bounds"), "clickable": node.get("clickable")}


def field_text() -> str | None:
    node = ui.find(dv.dump(), "keepassdx.search.field")
    return None if node is None else node.get("text")


def main() -> int:
    spec = fixture_spec.load_spec()
    env = fixture_spec.load_environment("cprima-dev")
    dv.configure(spec["dialogs"], env)
    detected = dv.detect_handlers()
    original = fs.read_app_preferences(env["target"])
    log = lambda **f: print("           ", f.get("step") or f, flush=True)
    sent: list[str] = []  # the key events the search code sends
    real_adb = dv.adb

    def watching_adb(*args, **kwargs):
        if args[:3] == ("shell", "input", "keyevent"):
            sent.extend(args[3:])
        return real_adb(*args, **kwargs)

    try:
        reads = []
        for _ in range(3):
            started = time.time()
            real_adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
            real_adb("exec-out", "cat", "/sdcard/ui.xml")
            reads.append(time.time() - started)
        print(f"[{time.strftime('%H:%M:%S')}] one screen read takes {min(reads):.1f} to {max(reads):.1f} s on this phone", flush=True)

        step("Initialize (open KeePassDX, unlock the fixture)", lambda: fs.initialize(spec, env, detected, HERE / "kp-test-tel.kdbx", log), budget=300)
        dv.adb = watching_adb
        first, second = "tel-url", "works-minimal"

        step(f"search {first!r}", lambda: dv.search_for(first))
        check("the field holds the term", field_text() == first, repr(field_text()))
        info = cross_info()
        check("the 'x' is on the screen while the field holds text", info is not None)
        print("           the 'x':", info, flush=True)
        check("its id is the search view's own, search_close_btn", bool(info) and info["id"].endswith("search_close_btn"), str(info))

        count, rows = step(f"search {second!r} (taps the 'x' first)", lambda: dv.search_for(second))
        check("the old term is gone, the field holds exactly the new one", field_text() == second, repr(field_text()))
        check("the result list shows the entry", second in [t for t, _ in rows], str([t for t, _ in rows][:4]))

        def tap_cross():
            cross = ui.require(dv.dump(), "keepassdx.search.clear")
            dv.tap(*dv.centre(dv.bounds(cross)))
            dv.wait_until(lambda: ui.find(dv.dump(), "keepassdx.search.clear") is None, 8, what="the 'x' to disappear")

        step("tap the 'x' by hand", tap_cross)
        check("the 'x' is gone: the field is empty", cross_info() is None, str(cross_info()))

        count_empty, _ = step("empty search (every entry)", lambda: dv.search_for(""))
        check("an empty search shows every entry of the file", count_empty == 50, f"count {count_empty}")

        deletes = [k for k in sent if k in ("KEYCODE_DEL", "67", "KEYCODE_FORWARD_DEL", "112")]
        check("no Backspace or Delete was sent by the search code", not deletes, f"{len(deletes)} sent")
        print("           key events sent:", sorted(set(sent)) or "none", flush=True)
    except TooSlow as problem:
        check("every step within its time budget", False, str(problem))
    finally:
        dv.adb = real_adb
        print(f"[{time.strftime('%H:%M:%S')}] End ...", flush=True)
        fs.finish(env, detected, log, original)
    print()
    print("all checks passed" if not failures else f"{len(failures)} failed: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
