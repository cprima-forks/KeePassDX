"""Take one screenshot of each default app on the phone, with its sidecar, and pull it.

For each target of repository/predicted-needs.json (dialer, browser, mailer, sms): close the app,
launch it with an intent that cannot do harm (DIAL shows the dialpad without calling, VIEW https opens
the browser, SENDTO mailto: and sms: open a composer without sending), wait, take the screenshot
(device.capture: on the phone, with its raw and structured sidecar), close the app. It NEVER taps
anything and never presses Send. The pictures go to runs/_apps-<time>/<role>/<screen>.png (local,
not published).

A composer can show the account it would send from, and a messaging app its suggestions: the pictures
are for the person who owns the phone to look at, nothing here reads their content.

    uv run python shoot_apps.py                  # all four
    uv run python shoot_apps.py browser mailer   # some
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import device as dv
import fixture_spec
import run_facts

HERE = Path(__file__).parent
NEEDS = HERE / "repository" / "predicted-needs.json"
RUNS = HERE / "runs"
ROLE_KEYS = {"dialer": ("dial", "dialer-role"), "browser": ("web", "browser-role"), "mailer": ("mail",), "sms": ("sms-role",)}


def main() -> int:
    wanted = set(sys.argv[1:])
    predicted = json.loads(NEEDS.read_text(encoding="utf-8"))
    spec = fixture_spec.load_spec()
    env = fixture_spec.load_environment("cprima-dev")
    dv.configure(spec["dialogs"], env)
    detected = dv.detect_handlers()
    out = RUNS / f"_apps-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    out.mkdir(parents=True)
    dv.SHOT_STATIC.clear()
    dv.SHOT_STATIC.update(context={"run": out.name, "environment": env["name"]})
    fixture_sha = run_facts.sha256_of(HERE / "kp-test-tel.kdbx") or ""
    run_facts.collect(out, out.name, env, detected, fixture_sha, HERE / "fixture-spec.json", (HERE / spec["casesFile"]).resolve())

    taken = []
    try:
        for role, target in predicted["targets"].items():
            if wanted and role not in wanted:
                continue
            package = next((detected[k] for k in ROLE_KEYS[role] if k in detected), None)
            if package is None:
                print(f"{role}: no app detected for this role", flush=True)
                continue
            print(f"{role}: {package} ...", flush=True)
            try:
                dv.adb("shell", "am", "force-stop", package)
                time.sleep(1.0)
                dv.adb("shell", "am", "start", *[f"'{a}'" if ("?" in a or ":" in a) and not a.startswith("-") else a for a in target["launch"]])
                dv.soft_wait(lambda: package in dv.focus(), timeout=15)
                time.sleep(3.0)  # a first start may need a moment
                front = dv.focus()
                folder = out / role
                folder.mkdir()
                shot = dv.capture(target["screen"])
                path = shot.write(folder / f"{target['screen']}.png", role=role, package=package, launched_with=target["launch"], in_front=front)
                print(f"   in front: {front}; picture: {path.relative_to(HERE)}", flush=True)
                taken.append(path)
            except Exception as problem:
                print(f"   NOT TAKEN: {type(problem).__name__}: {problem}", flush=True)
            finally:
                dv.adb("shell", "am", "force-stop", package)  # leave nothing open
    finally:
        dv.remove_phone_shots()
    print(f"{len(taken)} picture(s) pulled to {out.relative_to(HERE)}, each with its .png.raw.json and .png.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
