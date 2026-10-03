"""Check the sidecar code without a phone: the JSON of `phonectl`, the status bar from the window list and
from an older XML dump, the structured sidecar, the rule that every screenshot has its sidecar, and the
refusal to give a number that was not measured.

    uv run python check_shot_meta.py
"""

import io
import json
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

import device as dv
import shot_meta
from errors import ScreenshotFailed

HERE = Path(__file__).parent
# a windows dump written by an older run (error evidence of ctl-bare): the FP4 with the status bar on top
DUMP_CANDIDATES = sorted((HERE / "runs").glob("*/ctl-bare/error-1-windows.xml"))

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("ok    " if ok else "FAIL  ") + name + (f": {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def shot_answer(**changes) -> dict:
    """What `phonectl shot` answers."""
    answer = {
        "ok": True, "command": "shot", "png": "/sdcard/kpshots/r/0001-a.png",
        "start_ns": 1790974336000000000, "screencap_done_ns": 1790974336600000000, "windows_done_ns": 1790974336900000000,
        "size": [1080, 2340], "density": 400, "rotation": 0,
        "focus": "com.kunzisoft.keepass.free/com.kunzisoft.keepass.activities.GroupActivity",
        "status_bar": {"rect": [0, 0, 1080, 81], "height_px": 81}, "navigation_bar": None,
        "windows": [{"type": 3, "rect": [0, 0, 1080, 81], "package": "com.android.systemui", "active": False, "focused": False}],
    }
    answer.update(changes)
    return answer


ENV_ANSWER = {
    "ok": True, "command": "env", "time_ns": 1790974336800737310,
    "props": {"ro.product.manufacturer": "Fairphone", "ro.product.brand": "Fairphone", "ro.product.model": "FP4", "ro.product.device": "FP4",
              "ro.build.version.release": "13", "ro.build.version.sdk": "33", "ro.build.version.security_patch": "2025-01-05",
              "ro.product.cpu.abi": "arm64-v8a", "persist.sys.locale": "en-DE", "ro.product.locale": "", "persist.sys.timezone": "Europe/Berlin"},
    "private": {"ro.build.id": "TEST.ID", "ro.build.fingerprint": "Fairphone/FP4/test"},
    "settings": {"system.font_scale": "1.3", "system.screen_off_timeout": "600000", "global.window_animation_scale": "1.0",
                 "global.transition_animation_scale": "1.0", "global.animator_duration_scale": "1.0", "secure.navigation_mode": "2",
                 "secure.default_input_method": "com.example.ime/.Service"},
    "night": "Night mode: no", "display": {"size": [1080, 2340], "density": 400},
    "roles": {"dialer": "org.fossify.phone", "browser": "org.mozilla.firefox", "sms": "org.fossify.messages", "home": "rasel.lunar.launcher"},
    "packages": {
        "com.kunzisoft.keepass.free": {"version_name": "4.6.0_beta01", "version_code": 98, "apk_path": "/data/app/x/base.apk", "apk_sha256": "abc123"},
        "org.fossify.phone": {"version_name": "1.2.3", "version_code": 12, "apk_path": "/data/app/y/base.apk", "apk_sha256": "def456"},
        "com.kunzisoft.keepass.tests": {"version_name": None, "version_code": None, "apk_path": "/data/app/z/base.apk", "apk_sha256": "789abc"},
    },
}


def main() -> int:
    check("the sidecar of a.png is a.png.json", shot_meta.sidecar_path(Path("x/a.png")) == Path("x/a.png.json"))
    check("the raw file of a.png is a.png.raw.json", shot_meta.raw_path(Path("x/a.png")) == Path("x/a.png.raw.json"))

    # --- the status bar in an XML dump of an older run (the backfill) ---
    dump_text = None
    for candidate in DUMP_CANDIDATES:
        try:
            shot_meta.parse_dump(candidate.read_text(encoding="utf-8"))
            dump_text = candidate.read_text(encoding="utf-8")
            print(f"using the old dump {candidate.relative_to(HERE)}")
            break
        except ET.ParseError:
            continue
    if dump_text is not None:
        root = shot_meta.parse_dump(dump_text)
        bar = shot_meta.status_bar(root)
        check("old dump: the status bar is found", bar is not None and bar["rect"][1] == 0 and bar["rect"][3] > 0, str(bar))
        for node in list(root.iter("node")):
            if node.get("resource-id", "").startswith("com.android.systemui:id/status_bar"):
                node.set("resource-id", "")
        check("old dump: no status bar -> None, not a number", shot_meta.status_bar(root) is None)
    else:
        print("note: no old windows dump found; the old-dump checks are skipped")
    low = ET.fromstring('<hierarchy><node package="com.android.systemui" resource-id="com.android.systemui:id/status_bar" bounds="[0,2200][1080,2281]"/></hierarchy>')
    check("old dump: a bar that is not at the top edge is not a status bar", shot_meta.status_bar(low) is None)

    # --- the answer of phonectl shot ---
    parsed = shot_meta.parse_shot(shot_answer())
    check("shot: times, size, density, rotation", parsed["screencap_done_ns"] == 1790974336600000000 and parsed["size"] == [1080, 2340]
          and parsed["density"] == 400 and parsed["rotation"] == 0, str(parsed))
    check("shot: the focus window", parsed["focus"].endswith("GroupActivity"), parsed["focus"])
    check("shot: the status bar from the window list", parsed["status_bar"] == {"rect": [0, 0, 1080, 81], "height_px": 81})
    gap = shot_meta.parse_shot({"ok": True})
    check("shot: a part the phone did not give is None", gap["screencap_done_ns"] is None and gap["status_bar"] is None and gap["focus"] == "?")

    # --- the structured sidecar ---
    static = {"device": {"model": "FP4"}, "environment": {"profile": "p"}, "code": {"git_head": "abc"}, "context": {"run": "r"}}

    def build(answer: dict, **extra) -> dict:
        return shot_meta.build(file="a.png", png_sha256="0" * 64, image_size=(1080, 2340), raw=shot_meta.parse_shot(answer),
                               host_before_ns=1790974336590000000, host_after_ns=1790974336610000000, static=extra.get("static", static), step={},
                               raw_file="a.png.raw.json", device_raw_path="/sdcard/kpshots/r/a.png.raw.json")

    facts = build(shot_answer())
    check("sidecar: schema 2", facts["schema"] == 2)
    check("sidecar: the status bar rectangle and its explicit height", facts["status_bar"]["rect"] == [0, 0, 1080, 81] and facts["status_bar"]["height_px"] == 81, str(facts["status_bar"]))
    check("sidecar: measured by phonectl at capture", facts["status_bar"]["measured"] == "phonectl-windows")
    check("sidecar: no navigation bar with gestures", facts["navigation_bar"] is None)
    check("sidecar: taken is the phone's clock", facts["taken_source"] == "device-clock" and facts["taken"].startswith("2026-"), facts["taken"])
    check("sidecar: capture duration from the phone's clock", facts["capture_ms"] == 600, str(facts["capture_ms"]))
    check("sidecar: without run pings the skew is the shot's rough span", facts["clock"]["skew_estimate_ms"] == 0 and facts["clock"]["skew_uncertainty_ms"] == 10
          and facts["clock"]["skew_basis"] == "this shot's call span", str(facts["clock"]))
    with_skew = build(shot_answer(), static={**static, "clock_skew": {"skew_estimate_ms": -37, "skew_uncertainty_ms": 12, "basis": "pings"}})
    check("sidecar: the skew measured by the run's pings wins", with_skew["clock"]["skew_estimate_ms"] == -37 and with_skew["clock"]["skew_basis"].startswith("run:"), str(with_skew["clock"]))
    check("sidecar: device, environment, code, context embedded", all(facts[k] == static[k] for k in static))
    check("sidecar: raw reference", facts["raw"] == {"file": "a.png.raw.json", "device_path": "/sdcard/kpshots/r/a.png.raw.json"})
    check("sidecar: top_rows is the height", shot_meta.top_rows(facts) == 81)
    wide = json.loads(json.dumps(facts))
    wide["image"]["width"] = 1000
    check("sidecar: a bar that does not span the picture gives no number", shot_meta.top_rows(wide) is None)
    with_nav = build(shot_answer(navigation_bar={"rect": [0, 2259, 1080, 2340], "height_px": 81}))
    check("sidecar: a navigation bar is recorded when the phone has one", with_nav["navigation_bar"]["height_px"] == 81, str(with_nav["navigation_bar"]))
    none = build(shot_answer(status_bar=None, windows_error="java.lang.SecurityException: no UiAutomation"))
    check("sidecar: no status bar -> null and the phone's reason", none["status_bar"] is None and "SecurityException" in none["status_bar_error"], str(none.get("status_bar_error")))
    check("sidecar: top_rows of an unmeasured bar is None", shot_meta.top_rows(none) is None)
    plain = build(shot_answer(status_bar=None))
    check("sidecar: no status bar and no reason -> a plain reason", plain["status_bar"] is None and "no status bar" in plain["status_bar_error"])

    # --- the answer of phonectl env ---
    env = shot_meta.parse_env(ENV_ANSWER)
    device = env["device"]
    check("env: the phone", device["model"] == "FP4" and device["manufacturer"] == "Fairphone" and device["android"] == "13" and device["sdk"] == "33", str(device))
    check("env: settings typed", device["font_scale"] == 1.3 and device["screen_off_timeout_ms"] == 600000 and device["navigation_mode"] == "gestures", str(device))
    check("env: locale", device["locale"] == "en-DE")
    check("env: the build id and fingerprint are under private", device["private"]["build_id"] == "TEST.ID" and "build_id" not in device)
    check("env: night mode", device["night_mode"] == "no")
    check("env: roles", env["roles"]["dialer"] == "org.fossify.phone" and env["roles"]["home"] == "rasel.lunar.launcher", str(env["roles"]))
    test_pkg = env["packages"]["com.kunzisoft.keepass.tests"]
    check("env: an instrumentation APK has no version name, but keeps its APK checksum", test_pkg["version_name"] is None and test_pkg["apk_sha256"] == "789abc", str(test_pkg))
    check("env: package with version and APK checksum", env["packages"]["com.kunzisoft.keepass.free"]["apk_sha256"] == "abc123"
          and env["packages"]["org.fossify.phone"]["version_code"] == 12)

    # --- the publication manifest never holds a private field ---
    sys.path.insert(0, str(HERE.parent.parent / "fork-tools"))
    import publish_png  # noqa: E402  (fork-tools is not a package)

    secret = {**facts, "device": {**device}, "environment": {"profile": "p", "target_app": {"package": "x", "apk_path": "/data/app/secret/base.apk", "apk_sha256": "s"},
                                                            "roles": {"dialer": {"package": "d", "version_name": "1", "apk_path": "/data/app/secret2"}},
                                                            "packages": {"all": "of them"}}}
    published = json.dumps(publish_png.public_facts(secret))
    check("publish: no private field in the manifest", "build_id" not in published and "build_fingerprint" not in published and "TEST.ID" not in published, published[:200])
    check("publish: no phone path and no package list in the manifest", "/data/app" not in published and "of them" not in published)
    check("publish: the model and the APK checksum are in it", '"model": "FP4"' in published and '"apk_sha256": "s"' in published)
    check("publish: phonectl's measurement is accepted for the crop", "phonectl-windows" in publish_png.MEASURED_OK)

    # --- every screenshot has its sidecar ---
    image = Image.new("RGB", (1080, 2340), (10, 20, 30))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    raw_text = json.dumps(shot_answer())
    shot = dv.Shot(image, buffer.getvalue(), raw_text, json.loads(json.dumps(facts)), "0001-b", "/sdcard/kpshots/r")
    with tempfile.TemporaryDirectory() as tmp:
        run = Path(tmp)
        png = run / "e" / "b.png"
        png.parent.mkdir()
        shot.write(png, entry="tel-url", scenario="UI-COPY", label="b", clipboard={"value": "x", "read_by": "test", "after": "Copy"})
        check("write: the picture, its raw file and its sidecar", png.exists() and shot_meta.raw_path(png).exists() and shot_meta.sidecar_path(png).exists())
        check("write: the picture is the captured data", png.read_bytes() == buffer.getvalue())
        check("write: the raw file is what the phone answered (JSON)", json.loads(shot_meta.raw_path(png).read_text(encoding="utf8")) == shot_answer())
        back = shot_meta.read(png)
        check("write: step and clipboard in the sidecar", back["step"] == {"entry": "tel-url", "scenario": "UI-COPY", "label": "b"} and back["clipboard"]["value"] == "x")
        check("write: the raw reference names the final file", back["raw"]["file"] == "b.png.raw.json" and back["file"] == "b.png", str(back["raw"]))
        check("write: the shot object is not changed by writing", "clipboard" not in shot.facts)
        dv.annotate(png, clipboard={"value": "y", "read_by": "test"})
        check("annotate: adds a field to the sidecar", shot_meta.read(png)["clipboard"]["value"] == "y")
        check("verify_run: a complete picture is fine", shot_meta.verify_run(run) == [])

        lone = run / "e" / "lone.png"
        lone.write_bytes(buffer.getvalue())
        check("verify_run: a picture without a sidecar is reported", shot_meta.verify_run(run) == ["e/lone.png.json"], str(shot_meta.verify_run(run)))
        shot_meta.sidecar_path(lone).write_text(json.dumps({"schema": 2}), encoding="utf8")
        check("verify_run: a sidecar without a raw file is reported", shot_meta.verify_run(run) == ["e/lone.png.raw.json"], str(shot_meta.verify_run(run)))
        shot_meta.sidecar_path(lone).write_text(json.dumps({"schema": 2, "backfilled": True}), encoding="utf8")
        check("verify_run: a backfilled picture needs no raw file", shot_meta.verify_run(run) == [])

        blocked = run / "e" / "blocked.png"
        shot_meta.sidecar_path(blocked).mkdir()  # a folder where the sidecar file must go
        try:
            shot.write(blocked, label="blocked")
            raised = False
        except ScreenshotFailed:
            raised = True
        check("write: a sidecar that cannot be written fails the shot", raised)
        check("write: and leaves no picture and no raw file", not blocked.exists() and not shot_meta.raw_path(blocked).exists())
        try:
            dv.annotate(run / "e" / "nothing.png", clipboard={})
            raised = False
        except ScreenshotFailed:
            raised = True
        check("annotate: a picture without a sidecar is a failed shot", raised)

    print()
    print("all checks passed" if not failures else f"{len(failures)} failed: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
