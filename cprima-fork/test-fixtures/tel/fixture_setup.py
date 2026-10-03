"""Initialize and End of a UI test run, the way an RPA process does it, with no person involved.

Initialize ensures the automated systems are closed and starts from nothing, always the same way:
    1. the lock screen and the notification panel are out of the way (a person is needed only if the
       phone itself is locked: that is a handover, as in the runner);
    2. the app under test and the apps a tap can open (browser, mail, dialer) are force-stopped;
    3. the fixture file is on the phone (pushed if the checksum differs);
    4. the app is started fresh, the fixture is opened from the app's list of databases, or through the
       system file picker when the app does not know the file yet;
    5. on the credentials screen the toggles are set and the documented test password is typed;
    6. the entry list is checked against the file: its first and its last entry.
End closes the same apps again, which also locks the database.

What belongs to the fixture comes from fixture-spec.json (`database`); what belongs to the phone comes
from the environment profile (environments/<name>.json) and from Android itself (the default apps are
detected); the order of the entries comes from the file, because KeePassDX lists a database in file
order.
"""

import hashlib
import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import device as dv
from ui import ui

PHONE_DIR = "/sdcard/Download"
CACHE = Path(__file__).parent / "runs" / ".cache"


class SetupError(Exception):
    """The fixture could not be brought up on the phone, or what is open is not the fixture. The run
    cannot start; no repeat helps."""


@dataclass
class Setup:
    file_name: str
    sha256: str
    order: list[str]
    steps: list[str] = field(default_factory=list)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_order(path: Path, password: str, sha: str) -> list[str]:
    """The titles of the entries in file order, which is the order of the list on the phone. Reading
    a database takes a while (the key derivation), so the result is cached by checksum."""
    cache = CACHE / f"order-{sha[:16]}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    from pykeepass import PyKeePass

    titles = [e.title for e in PyKeePass(str(path), password=password).root_group.entries]
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(titles), encoding="utf-8")
    return titles


def apps_to_close(env: dict, detected: dict) -> list[str]:
    """The automated systems: the app under test, the apps the environment profile names, and the apps
    that Android says handle what a tap or Call in the entry view opens (dial, web address, mail
    address, and the dialer, browser and SMS roles). The home screen and system apps are never closed."""
    detected_apps = [p for key, p in detected.items() if key != "home-role"]
    apps = [env["target"], *env.get("closeBeforeAndAfter", []), *detected_apps]
    return [p for i, p in enumerate(apps) if p not in apps[:i] and (p == env["target"] or dv.may_force_stop(p))]


def close_apps(env: dict, detected: dict, log) -> None:
    """Close the automated systems."""
    apps = apps_to_close(env, detected)
    dv.adb("shell", "cmd", "statusbar", "collapse")
    for package in apps:
        dv.adb("shell", "am", "force-stop", package)
    log(event="setup", step="closed", apps=apps)  # `am force-stop` returns when the app is stopped: no wait


def ensure_file_on_phone(path: Path, sha: str, log) -> str:
    name = f"kp-test-tel-fixture-{sha[:8]}.kdbx"
    target = f"{PHONE_DIR}/{name}"
    on_phone = dv.adb("shell", "sha256sum", target).split()
    if not on_phone or on_phone[0] != sha:
        out = subprocess.run(["adb", "push", str(path), target], capture_output=True, text=True)
        on_phone = dv.adb("shell", "sha256sum", target).split()
        if not on_phone or on_phone[0] != sha:
            raise SetupError(f"the fixture could not be put on the phone as {name}: {out.stdout.strip()} {out.stderr.strip()}")
        log(event="setup", step="pushed", file=name)
    else:
        log(event="setup", step="already on the phone", file=name)
    return name


def start_app(log) -> None:
    dv.bring_app_to_front()
    if not dv.soft_wait(lambda: dv.in_app(), timeout=15):
        raise SetupError(f"KeePassDX did not start; the phone shows {dv.describe_screen()}")
    # a fresh start shows the file selection, or the credentials of the default database
    if not dv.soft_wait(lambda: dv.state() in (dv.State.FILE_SELECT, dv.State.LOCKED), timeout=15):
        raise SetupError(f"KeePassDX started in an unexpected screen: {dv.describe_screen()}")
    log(event="setup", step="started", state=dv.state().value)


def credentials_file_name() -> str:
    node = ui.find(dv.dump(), "keepassdx.credentials.file_name")
    return node.get("text", "") if node is not None else ""


def open_file(name: str, log) -> None:
    """Get from the file selection to the credentials screen of `name`."""
    if dv.state() == dv.State.LOCKED and credentials_file_name().startswith(name[:25]):
        return  # the app opened the credentials of this file by itself (the default database)
    if dv.state() == dv.State.LOCKED:
        dv.tap(*dv.centre(dv.bounds(ui.require(dv.dump(), "keepassdx.credentials.navigate_up"))))
        dv.wait_until(lambda: dv.state() == dv.State.FILE_SELECT, 10, what="the file selection")
    known = [row for row in ui.find_all(dv.dump(), "keepassdx.file_select.known_file") if row.get("text") == name]
    if known:
        dv.tap(*dv.centre(dv.bounds(known[0])))
        log(event="setup", step="opened from the list of known databases", file=name)
    else:
        pick_in_picker(name, log)
    dv.wait_until(lambda: dv.state() == dv.State.LOCKED, 20, what="the credentials screen")
    shown = credentials_file_name()
    if not shown or not name.startswith(shown.rstrip(".…")[:25]):
        raise SetupError(f"the credentials screen is for {shown!r}, expected {name!r}")


def pick_in_picker(name: str, log) -> None:
    """The app does not know the file: choose it in the system file picker (the Downloads folder)."""
    dv.tap(*dv.centre(dv.bounds(ui.require(dv.dump(), "keepassdx.file_select.open_vault"))))
    dv.wait_until(lambda: "documentsui" in dv.focus(), 10, what="the file picker")
    for _ in range(8):
        for node in ui.find_all(dv.dump(), "android.picker.file_title"):
            if node.get("text") == name:
                dv.tap(*dv.centre(dv.bounds(node)))
                log(event="setup", step="picked in the file picker", file=name)
                return
        dv.swipe(540, 1700, 540, 800, 900)
        dv.wait_stable()  # the list has stopped scrolling
    raise SetupError(f"{name} is not in the file picker's folder")


def set_toggle(element: str, wanted: str, log) -> None:
    """A credentials-screen toggle shows its state in its description ("User Verification enabled")."""
    node = ui.require(dv.dump(), element)
    if node.get("content-desc", "").lower().endswith(wanted.lower()):
        return
    dv.tap(*dv.centre(dv.bounds(node)))

    def shows() -> str:
        found = ui.find(dv.dump(), element)
        return found.get("content-desc", "") if found is not None else ""

    # the toggle shows the new state in its description: wait for that, not for a second
    now = dv.soft_wait(lambda: (lambda d: d if d.lower().endswith(wanted.lower()) else None)(shows()), timeout=5.0, poll=0.15) or shows()
    if not now.lower().endswith(wanted.lower()):
        raise SetupError(f"the toggle {element} shows {now!r} after a tap, wanted {wanted!r}")
    log(event="setup", step=f"{element} set", value=now)


def unlock(db: dict, log) -> None:
    set_toggle("keepassdx.credentials.user_verification", db["userVerification"], log)
    set_toggle("keepassdx.credentials.read_mode", db["mode"], log)
    dv.tap(*dv.centre(dv.bounds(ui.require(dv.dump(), "keepassdx.credentials.password"))))
    # the password field has the focus before anything is typed
    dv.soft_wait(lambda: (lambda n: n is not None and n.get("focused") == "true")(ui.find(dv.dump(), "keepassdx.credentials.password")),
                 timeout=3.0, poll=0.1)
    dv.keys("KEYCODE_MOVE_END", *["KEYCODE_DEL"] * 40)  # clear what may be there (the password field has no 'x')
    dv.type_text(db["password"])
    # Unlock is enabled once the credentials are filled: that is the signal, not 0.4 s
    dv.soft_wait(lambda: (lambda n: n is not None and n.get("enabled") == "true")(ui.find(dv.dump(), "keepassdx.credentials.unlock")),
                 timeout=3.0, poll=0.1)
    dv.tap(*dv.centre(dv.bounds(ui.require(dv.dump(), "keepassdx.credentials.unlock"))))
    dv.wait_until(lambda: dv.state() == dv.State.LIST, 60, what="the entry list after Unlock")
    log(event="setup", step="unlocked")


def verify_list(order: list[str], log) -> None:
    """The open database must be this fixture. By search, with no scrolling: an empty search shows the
    number of entries, which must be the file's, and the file's first and last entry must be found."""
    problems = []
    count, _ = dv.search_for("")
    if count != len(order):
        problems.append(f"the database has {count} entries, the file has {len(order)}")
    for title in (order[0], order[-1]):
        _, rows = dv.search_for(title)
        if title not in [text for text, _ in rows]:
            problems.append(f"{title!r} is not found by the search")
    if problems:
        raise SetupError("the open database is not this fixture: " + "; ".join(problems))
    log(event="setup", step="database verified by search", entries=count, first=order[0], last=order[-1])
    close = ui.find(dv.dump(), "keepassdx.search.close")
    if close is not None:
        dv.tap(*dv.centre(dv.bounds(close)))
        dv.soft_wait(lambda: ui.find(dv.dump(), "keepassdx.search.field") is None, timeout=3.0, poll=0.15)  # the search is closed


def initialize(spec: dict, env: dict, detected: dict, path: Path, log) -> Setup:
    """Close everything, start the app fresh, open and unlock the fixture, verify it."""
    sha = sha256_of(path)
    db = spec["database"]
    # the lock screen of the phone itself is not ours to open: the runner's modal table waits for the
    # person ("screen-locked"); deal_with_modals returns once it is gone
    dv.deal_with_modals()
    close_apps(env, detected, log)
    name = ensure_file_on_phone(path, sha, log)
    order = file_order(path, db["password"], sha)
    start_app(log)
    open_file(name, log)
    unlock(db, log)
    verify_list(order, log)
    return Setup(file_name=name, sha256=sha, order=order)


def read_app_preferences(package: str) -> dict | None:
    """The app's settings, read with run-as (possible for a debug build). None when it is not
    readable. Values are strings; a boolean shows as "true" or "false"."""
    import xml.etree.ElementTree as ET

    text = dv.adb("shell", "run-as", package, "cat", f"shared_prefs/{package}_preferences.xml")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    return {e.get("name"): e.get("value") if e.get("value") is not None else (e.text or "") for e in root}


def read_education_hints(package: str) -> dict | None:
    """Which one-time hint overlays the app has already shown (kdbxeducation.xml, run-as). Values are
    "true" once a hint was shown. None when the file is not readable."""
    import xml.etree.ElementTree as ET

    text = dv.adb("shell", "run-as", package, "cat", "shared_prefs/kdbxeducation.xml")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    return {e.get("name"): e.get("value") for e in root}


def environment_fingerprint(env: dict) -> dict:
    """What the phone and the app are configured to, as read now: the app's settings and the Android
    settings that change what a test sees. It goes in the report header and the matrix ("measured
    on")."""
    def setting(namespace: str, key: str) -> str:
        return dv.adb("shell", "settings", "get", namespace, key).strip()

    return {
        "app_preferences": read_app_preferences(env["target"]),
        "education_hints": read_education_hints(env["target"]),
        "android": {
            "font_scale": setting("system", "font_scale"),
            "screen_off_timeout_ms": setting("system", "screen_off_timeout"),
            "animation_scale": setting("global", "window_animation_scale"),
            "navigation_mode": setting("secure", "navigation_mode"),
            "locale": dv.adb("shell", "getprop", "persist.sys.locale").strip(),
            "night_mode": dv.adb("shell", "cmd", "uimode", "night").strip(),
            "density": dv.adb("shell", "wm", "density").strip(),
        },
    }


def check_preconditions(env: dict, fingerprint: dict) -> list[dict]:
    """Evaluate the preconditions of the environment profile against the fingerprint: verify and
    record, never change. Returns one result per precondition."""
    results = []
    for rule in env.get("preconditions", []):
        source = fingerprint["app_preferences"] if rule["kind"] == "app_preference" else fingerprint["android"]
        actual = (source or {}).get(rule["key"])
        if actual is None:
            ok = False
        elif "equals" in rule:
            ok = actual == rule["equals"]
        else:
            ok = actual.startswith(rule["startswith"])
        if not ok and "orHintsShown" in rule:
            # no hint can appear when every hint that the run's screens can show was shown before
            shown = fingerprint.get("education_hints") or {}
            missing = [k for k in rule["orHintsShown"] if shown.get(k) != "true"]
            ok = not missing
            actual = f"{actual}; hints not yet shown: {missing}" if missing else f"{actual}; all {len(rule['orHintsShown'])} hints already shown"
        results.append({"id": rule["id"], "key": rule["key"], "actual": actual,
                        "expected": rule.get("equals") or f"starts with {rule.get('startswith')}",
                        "ok": ok, "why": rule["why"]})
    return results


def preflight(env: dict, log) -> dict:
    """Preconditions that make the run's evidence possible, checked before any entry is touched, by
    verifying and recording only. A violated precondition, or a screenshot that fails (missing or
    black: a system exception that fails fast), stops the run with its name and the value read."""
    fingerprint = environment_fingerprint(env)
    fingerprint["preconditions"] = check_preconditions(env, fingerprint)
    broken = [r for r in fingerprint["preconditions"] if not r["ok"]]
    if broken:
        raise SetupError("preflight: " + "; ".join(
            f"{r['id']}: {r['key']} is {r['actual']!r}, expected {r['expected']}. {r['why']}" for r in broken))
    try:
        dv.screenshot()
    except dv.ScreenshotFailed as problem:
        raise SetupError(f"preflight: {problem}") from None
    log(event="setup", step="preflight passed", preconditions=[r["id"] for r in fingerprint["preconditions"]], screenshot="ok")
    return fingerprint


def restore_preferences(env: dict, original: dict | None, log) -> None:
    """End: put back the app settings that the test changed by using the app (see `restoreAtEnd` in
    the profile). The app is stopped at this point, so it cannot overwrite the file."""
    keys = env.get("restoreAtEnd", [])
    if not keys or not original:
        return
    package = env["target"]
    current = read_app_preferences(package) or {}
    for key in keys:
        before, now = original.get(key), current.get(key)
        if before is None or now == before:
            continue
        path = f"shared_prefs/{package}_preferences.xml"
        edit = f"s/name=\"{key}\" value=\"{now}\"/name=\"{key}\" value=\"{before}\"/"
        dv.adb("shell", f"run-as {package} sed -i '{edit}' {path}")
        after = (read_app_preferences(package) or {}).get(key)
        log(event="setup", step="setting restored", key=key, was=now, restored_to=before, now=after)


def finish(env: dict, detected: dict, log, original_prefs: dict | None = None) -> None:
    """End: close the automated systems again (force-stopping the app also locks the database), then
    restore the settings that the test changed."""
    close_apps(env, detected, log)
    restore_preferences(env, original_prefs, log)
    dv.stop_phonectl()  # the server on the phone ends with the run
    log(event="setup", step="finished")
