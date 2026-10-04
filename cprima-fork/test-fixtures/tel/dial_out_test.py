"""Dials out on an emulator and records the number that Android's telephony passes on.

For each entry of near-life.json: the `tel:` links that KeePassDX makes of the value (the spans of the
LinkLab run) are handed to Android as a call (ACTION_CALL) on an emulator. The emulator's modem is
simulated: nothing leaves the computer and nothing costs. The emulator console lists the call with the
number that the dialer and telecom service gave the modem (`gsm list`). The call is ended at once.

This tests the other half of the tap: what the phone dials from the string it is handed, which the dialer's
input field does not show. It does not drive KeePassDX and it has no verdict.

    uv run python dial_out_test.py [--serial emulator-5554] [--only TITLE...]
        [--diagnostics runs/lab-near-life/diagnostics.jsonl]

An emergency number (112, 911, 110, 999, 000) is never dialled, also not on an emulator. Files go to
runs/<stamp>-dial/dialed.jsonl.
"""

import argparse
import datetime
import glob
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
RESOURCES = HERE.parent.parent / "app" / "sharedTest" / "resources"
EMERGENCY = {"112", "911", "110", "999", "000"}
OUTBOUND = re.compile(r"outbound to\s+(\S*)\s*:\s*(\w+)")


def adb(serial: str, *args: str) -> str:
    done = subprocess.run(["adb", "-s", serial, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (done.stdout + done.stderr).strip()


def calls(serial: str) -> list[tuple[str, str]]:
    """The calls of the simulated modem: (number, state)."""
    return OUTBOUND.findall(adb(serial, "emu", "gsm", "list"))


def end_all(serial: str) -> None:
    for number, _ in calls(serial):
        adb(serial, "emu", "gsm", "cancel", number)
    if calls(serial):
        adb(serial, "shell", "input", "keyevent", "KEYCODE_ENDCALL")
        time.sleep(1.0)


def is_emergency(url: str) -> bool:
    number = url[4:].split(";")[0]
    return re.sub(r"[^0-9]", "", number) in EMERGENCY


def dial(serial: str, url: str) -> dict:
    end_all(serial)
    # one string for the phone's shell: brackets and semicolons in the URL would be read as shell syntax
    quoted = "'" + url.replace("'", "'\''") + "'"
    started = adb(serial, "shell", f"am start -a android.intent.action.CALL -d {quoted}")
    seen: list[tuple[str, str]] = []
    deadline = time.time() + 8
    while time.time() < deadline and not seen:
        time.sleep(0.5)
        seen = calls(serial)
    focus = adb(serial, "shell", "dumpsys", "window", "displays") if not seen else ""
    end_all(serial)
    adb(serial, "shell", "input", "keyevent", "KEYCODE_HOME")
    if seen:
        return {"state": "dialed", "dialed": seen[0][0], "modem_state": seen[0][1]}
    return {"state": "no call", "dialed": None, "start": started[-160:], "screen": "".join(focus.split())[:0]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--diagnostics", default=str(RUNS / "lab-near-life" / "diagnostics.jsonl"))
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args()
    if not args.serial.startswith("emulator-"):
        raise SystemExit("this script dials: it runs on an emulator only (--serial emulator-NNNN)")

    source = json.loads((RESOURCES / "near-life.json").read_text(encoding="utf-8"))
    cases = []
    for path in sorted(glob.glob(str(RESOURCES / "tel-cases" / "*.json"))):
        cases += json.loads(Path(path).read_text(encoding="utf-8"))
    case_of: dict[str, str] = {}
    for case in cases:
        if case["level"] == "code" and case.get("field", "url") == "url":
            case_of.setdefault(case["value"], case["id"])
    spans: dict[str, list[dict]] = {}
    for line in Path(args.diagnostics).read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("probe") == "link.field":
            spans[record["case"]] = record["spans"]

    run_dir = RUNS / (datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-dial")
    run_dir.mkdir(parents=True)
    facts = {"serial": args.serial, "sdk": adb(args.serial, "shell", "getprop", "ro.build.version.sdk"),
             "release": adb(args.serial, "shell", "getprop", "ro.build.version.release"),
             "model": adb(args.serial, "shell", "getprop", "ro.product.model")}
    rows = []
    for item in source["entries"]:
        if args.only and item["title"] not in args.only:
            continue
        urls = [s["url"] for s in spans.get(case_of[item["value"]], []) if s["url"].lower().startswith("tel:")]
        if not urls:
            rows.append({"entry": item["title"], "url": None, "state": "no link"})
            continue
        for url in urls:
            if is_emergency(url):
                rows.append({"entry": item["title"], "url": url, "state": "not dialled: emergency number"})
                print(f"{item['title']:34} {url:42} not dialled (emergency number)")
                continue
            result = dial(args.serial, url)
            rows.append({"entry": item["title"], "url": url, **result})
            print(f"{item['title']:34} {url:42} {result['state']}: {result['dialed']}", flush=True)
    end_all(args.serial)
    with open(run_dir / "dialed.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"facts": facts, "diagnostics": args.diagnostics}) + "\n")
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{len(rows)} rows -> {run_dir / 'dialed.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
