"""The sidecars of a screenshot: what the phone said when it was taken, as JSON.

Every screenshot `<name>.png` of a run has two files next to it:

    <name>.png.raw.json   what the phone said: the JSON answer of `phonectl shot`, which ran ON THE PHONE,
                          took the picture and read the facts in one call, on the phone's clock.
    <name>.png.json       the structured sidecar, built from the raw one and from what the run knows (the
                          phone, the apps, the code). It is what publish_png.py reads.

A screenshot without both files is not evidence: device.Shot.write writes the three together, and a
sidecar that cannot be written removes the picture and fails the shot. verify_run lists the pictures
of a run that lack a file.

The status bar is measured per screenshot, from the window list in the raw answer (the system UI window
that spans the top of the display). A measurement that fails is recorded as such (`status_bar: null` and
the reason), never replaced by a number. This module has no phone in it: the raw answer is given to it, so
it can be checked offline (check_shot_meta.py).

The facts that do not change within a run (device, environment, code) come from one collection at the
start of the run: `phonectl env`, parsed by parse_env. Every sidecar embeds them, so a picture and its
sidecar are complete without the rest of the run folder.

Structured sidecar, schema 2:

    schema            2
    file              the picture's file name
    taken             ISO time with the host's time zone: the moment the screencap finished, on the
                      phone's clock
    taken_source      "device-clock" (measured) or "mtime" (backfilled from the file's time)
    clock             {device_start_ns, device_screencap_done_ns, device_windows_done_ns, host_before_ns,
                      host_after_ns, skew_estimate_ms, skew_uncertainty_ms, skew_basis}
    capture_ms        how long the screencap took on the phone
    png_sha256        SHA-256 of the file as captured
    image             {width, height} of the picture
    display           {size: [w, h], density, rotation} as the phone says at the capture
    status_bar        {rect: [l, t, r, b], height_px, node, measured, dumped_at} or null.
                      height_px is the number of rows to cut off the top (bottom minus top, 81 on the FP4).
                      measured: "phonectl-windows" (at capture), "windows-dump" (an older run), "inferred-from-dump"
                      or "inferred-from-sidecar" (backfilled), "given" (a person gave the height)
    status_bar_error  why status_bar is null
    navigation_bar    the same for the bar at the bottom, or null (a phone with gestures has none)
    focus             the window in front, package/activity
    device            the phone (see parse_env); `private` holds the firmware build id and fingerprint, which
                      are never published
    environment       the profile, the default apps (roles and handlers) with versions, the app under test
                      with its APK SHA-256, the settings that change what a shot shows, the preconditions
    code              git HEAD, whether the tree was dirty, SHA-256 of the fixture, the spec, the cases
    context           run id, environment profile
    step              what the run was doing: entry, scenario, label
    raw               {file, device_path}
    clipboard         only after a copy: {value, expected, after, read_by}
"""

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

SCHEMA = 2
SYSTEM_UI = "com.android.systemui"
# the window of the status bar in an XML dump (older runs), most specific first
STATUS_BAR_NODES = (f"{SYSTEM_UI}:id/status_bar", f"{SYSTEM_UI}:id/status_bar_container")


def sidecar_path(png: Path) -> Path:
    """`<name>.png` -> `<name>.png.json`."""
    return png.with_name(png.name + ".json")


def raw_path(png: Path) -> Path:
    """`<name>.png` -> `<name>.png.raw.json`."""
    return png.with_name(png.name + ".raw.json")


# --- what phonectl says ---------------------------------------------------------------------------


def _number(value, kind=float):
    try:
        return kind(value)
    except (TypeError, ValueError):
        return None


def parse_shot(answer: dict) -> dict:
    """The answer of `phonectl shot` as the facts of a capture. A part the phone did not give is None;
    nothing is filled in."""
    return {
        "start_ns": answer.get("start_ns"),
        "screencap_done_ns": answer.get("screencap_done_ns"),
        "windows_done_ns": answer.get("windows_done_ns"),
        "size": answer.get("size"),
        "density": answer.get("density"),
        "rotation": answer.get("rotation"),
        "focus": answer.get("focus") or "?",
        "status_bar": answer.get("status_bar"),
        "navigation_bar": answer.get("navigation_bar"),
        "windows_error": answer.get("windows_error"),
    }


def parse_env(answer: dict) -> dict:
    """The answer of `phonectl env` as {device, roles, packages}. `device` holds the phone and its settings,
    with the firmware build id and fingerprint under `private` (never published); `roles` the package that
    holds each default-app role; `packages` {package: {version_name, version_code, apk_path, apk_sha256}}."""
    props = answer.get("props") or {}
    settings = answer.get("settings") or {}
    display = answer.get("display") or {}
    night = re.search(r"Night mode: (\w+)", answer.get("night") or "")
    private = answer.get("private") or {}
    navigation = settings.get("secure.navigation_mode")
    device = {
        "manufacturer": props.get("ro.product.manufacturer"),
        "brand": props.get("ro.product.brand"),
        "model": props.get("ro.product.model"),
        "device": props.get("ro.product.device"),
        "android": props.get("ro.build.version.release"),
        "sdk": props.get("ro.build.version.sdk"),
        "security_patch": props.get("ro.build.version.security_patch"),
        "abi": props.get("ro.product.cpu.abi"),
        "locale": props.get("persist.sys.locale") or props.get("ro.product.locale"),
        "timezone": props.get("persist.sys.timezone"),
        "display": {"size": display.get("size"), "density": display.get("density")},
        "font_scale": _number(settings.get("system.font_scale")),
        "screen_off_timeout_ms": _number(settings.get("system.screen_off_timeout"), int),
        "animation_scales": {
            "window": _number(settings.get("global.window_animation_scale")),
            "transition": _number(settings.get("global.transition_animation_scale")),
            "animator": _number(settings.get("global.animator_duration_scale")),
        },
        "navigation_mode": {"0": "buttons", "1": "two-button", "2": "gestures"}.get(navigation, navigation),
        "default_ime": settings.get("secure.default_input_method"),
        "night_mode": night.group(1).lower() if night else None,
        "private": {"build_id": private.get("ro.build.id"), "build_fingerprint": private.get("ro.build.fingerprint")},
    }
    return {"device": device, "roles": {k: v for k, v in (answer.get("roles") or {}).items()}, "packages": answer.get("packages") or {}}


# --- the windows dump of older runs -----------------------------------------------------------------


def parse_bounds(text: str) -> tuple[int, int, int, int]:
    left, top, right, bottom = map(int, re.findall(r"-?\d+", text))
    return left, top, right, bottom


def parse_dump(text: str) -> ET.Element:
    """A saved dump as a tree. Dumps written before 2026-10-02 22:30 hold the placeholder `<redacted>`
    inside an attribute, which is not well-formed XML; it is repaired here (the placeholder is now
    `[redacted]`). A dump that is still not XML raises ET.ParseError."""
    return ET.fromstring(text.replace("<redacted>", "[redacted]"))


def status_bar(root: ET.Element) -> dict | None:
    """The status bar of a windows dump (older runs, backfill): its rectangle and the node it came from, or
    None when the dump holds no status bar (full-screen app, a dump of another display)."""
    nodes = [n for n in root.iter("node") if n.get("package") == SYSTEM_UI and n.get("bounds")]
    for wanted in STATUS_BAR_NODES:
        for node in nodes:
            if node.get("resource-id") == wanted:
                left, top, right, bottom = parse_bounds(node.get("bounds"))
                if top == 0 and bottom > top:  # it sits at the top edge of the display
                    return {"rect": [left, top, right, bottom], "node": wanted}
    return None


# --- building and keeping the sidecar ---------------------------------------------------------------


def ns_to_iso(ns: int | None) -> str | None:
    """Nanoseconds since the epoch as an ISO time with the host's time zone."""
    if ns is None:
        return None
    return datetime.fromtimestamp(ns / 1e9).astimezone().isoformat(timespec="milliseconds")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _bar(found: dict | None, measured: str, dumped_at: str | None) -> dict | None:
    if not found:
        return None
    left, top, right, bottom = found["rect"]
    return {"rect": [left, top, right, bottom], "height_px": found.get("height_px", bottom - top),
            "node": "system UI window (accessibility window list)", "measured": measured, "dumped_at": dumped_at}


def build(
    *,
    file: str,
    png_sha256: str,
    image_size: tuple[int, int],
    raw: dict,
    host_before_ns: int,
    host_after_ns: int,
    static: dict,
    step: dict,
    raw_file: str,
    device_raw_path: str | None,
) -> dict:
    """The structured sidecar of one screenshot, from its parsed raw answer (parse_shot) and the run's
    static facts (`static` has device, environment, code, context)."""
    done = raw["screencap_done_ns"]
    host_mid = (host_before_ns + host_after_ns) // 2
    run_skew = static.get("clock_skew") or {}
    if run_skew.get("skew_estimate_ms") is not None:  # measured once per run with quick calls: narrow
        skew, uncertainty, basis = run_skew["skew_estimate_ms"], run_skew["skew_uncertainty_ms"], "run: " + run_skew.get("basis", "")
    else:  # from the span of this call, which is wide: only a rough figure
        skew = round((done - host_mid) / 1e6) if done else None
        uncertainty, basis = round((host_after_ns - host_before_ns) / 2e6), "this shot's call span"
    windows_at = ns_to_iso(raw["windows_done_ns"])
    facts: dict = {
        "schema": SCHEMA,
        "file": file,
        "taken": ns_to_iso(done) or now_iso(),
        "taken_source": "device-clock" if done else "host-clock",
        "clock": {
            "device_start_ns": raw["start_ns"],
            "device_screencap_done_ns": done,
            "device_windows_done_ns": raw["windows_done_ns"],
            "host_before_ns": host_before_ns,
            "host_after_ns": host_after_ns,
            "skew_estimate_ms": skew,
            "skew_uncertainty_ms": uncertainty,
            "skew_basis": basis,
        },
        "capture_ms": round((done - raw["start_ns"]) / 1e6) if done and raw["start_ns"] else None,
        "png_sha256": png_sha256,
        "image": {"width": image_size[0], "height": image_size[1]},
        "display": {"size": raw["size"], "density": raw["density"], "rotation": raw["rotation"]},
        "status_bar": _bar(raw["status_bar"], "phonectl-windows", windows_at),
        "navigation_bar": _bar(raw["navigation_bar"], "phonectl-windows", windows_at),
        "focus": raw["focus"],
        "device": static.get("device", {}),
        "environment": static.get("environment", {}),
        "code": static.get("code", {}),
        "context": static.get("context", {}),
        "step": step,
        "raw": {"file": raw_file, "device_path": device_raw_path},
    }
    if facts["status_bar"] is None:
        facts["status_bar_error"] = raw.get("windows_error") or "the phone's window list holds no status bar"
    return facts


def write(png: Path, facts: dict) -> Path:
    path = sidecar_path(png)
    path.write_text(json.dumps(facts, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def read(png: Path) -> dict | None:
    path = sidecar_path(png)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def top_rows(facts: dict) -> int | None:
    """The number of rows to cut off the top: the bottom edge of the measured status bar, or None
    when it was not measured. The bar must sit at the top and span the picture's width."""
    bar = facts.get("status_bar")
    if not bar:
        return None
    left, top, right, bottom = bar["rect"]
    if top != 0 or left != 0 or right != facts["image"]["width"]:
        return None
    return bottom


def verify_run(run: Path) -> list[str]:
    """The pictures of a run that lack their raw file or their sidecar, as paths relative to the run.
    Every screenshot has both; an empty list is the only good answer."""
    missing = []
    for png in sorted(run.rglob("*.png")):
        if png.relative_to(run).parts[0] == "published":  # the cropped, stripped copies: not screenshots of the phone
            continue
        sidecar = sidecar_path(png)
        if not sidecar.exists():
            missing.append(sidecar.relative_to(run).as_posix())
            continue
        backfilled = bool(json.loads(sidecar.read_text(encoding="utf-8")).get("backfilled"))
        if not backfilled and not raw_path(png).exists():  # a backfilled picture has no raw file by nature
            missing.append(raw_path(png).relative_to(run).as_posix())
    return missing
