"""What a run is made of, collected once at its start and embedded in every sidecar.

The phone and the apps are asked by `phonectl env`, which runs on the phone and answers with JSON; the
code and the files come from the host (git, SHA-256 of the fixture, the spec and the cases). The result
is written to the run folder as env.raw.json (the phone's own answer) and env.json (the structured
facts), and set as device.SHOT_STATIC, which every screenshot's sidecar embeds.

Nothing here identifies a person: no serial number, no IMEI, no account, no phone number. The firmware
build id and fingerprint are kept under device.private and are never published (publish_png.py writes
only a whitelist).
"""

import hashlib
import json
import subprocess
import time
from pathlib import Path

import device as dv
import shot_meta

HERE = Path(__file__).parent
REPO = HERE.parent.parent
TEST_APP = "com.kunzisoft.keepass.tests"  # the instrumented tests' package, if installed

# Settings of the app under test that change what a screenshot shows. Only these are recorded.
PICTURE_PREFERENCES = (
    "enable_screenshot_mode_key", "enable_education_screens_key", "user_verification_mode_key",
    "user_verification_device_credential_key", "clip_timeout_key", "allow_copy_password_key",
    "setting_style_key", "setting_style_brightness_key", "list_size_key",
    "monospace_font_extra_fields_enable_key", "colorize_password_key", "show_entry_colors_key",
)


def sha256_of(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def git(*args: str) -> str | None:
    result = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def code_facts(fixture_sha: str, spec_file: Path, cases_file: Path) -> dict:
    """The code state of the host: git HEAD, how many files differ from it, and the data files."""
    status = git("status", "--porcelain")
    return {
        "git_head": git("rev-parse", "HEAD"),
        "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_dirty_files": len(status.splitlines()) if status is not None else None,
        "fixture_sha256": fixture_sha,
        "spec_sha256": sha256_of(spec_file),
        "cases_sha256": sha256_of(cases_file),
    }


def packages_of(env: dict, detected: dict) -> list[str]:
    """The packages whose versions and APK checksums are recorded: the app under test, the apps that
    Android says are the defaults or handle what a tap opens, and the test app."""
    wanted = [env["target"], TEST_APP, *detected.values()]
    return [p for i, p in enumerate(wanted) if p and p not in wanted[:i]]


def measure_clock_skew(pings: int = 7) -> dict:
    """How far the phone's clock is from this machine's: the phone's `date` against the host's time
    around a quick call. The call with the shortest round trip wins; its half is the uncertainty. Asked
    once per run: the span of a screenshot call (seconds, mostly the windows dump) is far too wide for it."""
    best = None
    for _ in range(pings):
        before = time.time_ns()
        answer = dv.adb("shell", "date", "+%s%N").strip()
        after = time.time_ns()
        if answer.isdigit():
            round_trip = after - before
            if best is None or round_trip < best[0]:
                best = (round_trip, int(answer) - (before + after) // 2)
    if best is None:
        return {"skew_estimate_ms": None, "skew_uncertainty_ms": None, "pings": pings, "basis": "the phone did not answer"}
    return {"skew_estimate_ms": round(best[1] / 1e6), "skew_uncertainty_ms": round(best[0] / 2e6), "pings": pings,
            "basis": f"shortest round trip of {pings} calls of `date +%s%N`"}


def collect(run_dir: Path, run_name: str, env: dict, detected: dict, fixture_sha: str, spec_file: Path, cases_file: Path) -> dict:
    """Ask the phone (`phonectl env`), read the host, write env.raw.json and env.json, set device.SHOT_STATIC.
    Returns the static facts. A failure to ask the phone is a DeviceError: a run without its facts
    would have pictures that cannot be published."""
    answer = dv.phonectl("env", *packages_of(env, detected))
    parsed = shot_meta.parse_env(answer)
    packages = parsed["packages"]
    target = packages.get(env["target"], {})

    def role(name: str) -> dict:
        package = parsed["roles"].get(name, "")
        return {"package": package, **packages.get(package, {})} if package else {"package": None}

    handlers = {kind: {"package": detected.get(kind), **packages.get(detected.get(kind), {})}
                for kind in ("dial", "web", "mail") if detected.get(kind)}
    static = {
        "device": parsed["device"],
        "environment": {
            "profile": env["name"],
            "roles": {name: role(name) for name in ("dialer", "browser", "sms", "home")},
            "handlers": handlers,
            "detected": detected,
            "target_app": {"package": env["target"], **target},
            "test_app": {"package": TEST_APP, **packages[TEST_APP]} if packages.get(TEST_APP, {}).get("apk_path") else None,
            "packages": packages,
        },
        "code": code_facts(fixture_sha, spec_file, cases_file),
        "context": {"run": run_name, "environment": env["name"]},
        "clock_skew": measure_clock_skew(),
    }
    (run_dir / "env.raw.json").write_text(json.dumps(answer, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    write_env(run_dir, static)
    dv.SHOT_STATIC.clear()
    dv.SHOT_STATIC.update(static)
    return static


def add_preflight(run_dir: Path, fingerprint: dict) -> None:
    """After the preflight: the settings that change what a picture shows, and the preconditions, join
    the environment. The pictures taken before this point have the facts without them."""
    prefs = (fingerprint or {}).get("app_preferences") or {}
    environment = dv.SHOT_STATIC.setdefault("environment", {})
    environment["app_preferences"] = {key: prefs.get(key) for key in PICTURE_PREFERENCES}
    environment["preconditions"] = [{"id": p["id"], "ok": p["ok"], "actual": p["actual"]} for p in (fingerprint or {}).get("preconditions", [])]
    write_env(run_dir, dv.SHOT_STATIC)


def write_env(run_dir: Path, static: dict) -> None:
    (run_dir / "env.json").write_text(json.dumps(static, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
