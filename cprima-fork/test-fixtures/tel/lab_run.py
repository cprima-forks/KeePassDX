"""Screenshots of LinkLab cases on the phone, each with its raw and structured sidecar.

Usage (from cprima-fork/test-fixtures/tel):
    uv run python lab_run.py --cases C-NG-001,C-PC-001      the listed cases
    uv run python lab_run.py --all                          every case of the code level
    options: --environment cprima-dev   --lab-env E-004   --no-scroll

Per case the lab is started with the case ID, the script waits for the state the lab writes to logcat
(`LINKLAB_STATE` with ready=true), and takes a picture of the top of the screen and one after a scroll.
Every picture comes from `device.capture` (taken on the phone, with its facts on the phone's clock) and is
written with `Shot.write`, so it has `<name>.png`, `<name>.png.raw.json` and `<name>.png.json`. A picture
whose sidecar cannot be written fails the case. At the end `shot_meta.verify_run` lists any picture that
lacks a file.

The lab observes and gives no verdict, so this script does not either: its result per case is `shot`
or `error`, and an error says what failed. Files go to runs/<stamp>-lab/<case>/.
"""

import argparse
import datetime
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import device as dv
import fixture_spec
import run_facts
import shot_meta

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
PACKAGE = "com.kunzisoft.keepass.cprima_fork"
LAB = PACKAGE + "/com.kunzisoft.keepass.linklab.LabActivity"
ABOUT = PACKAGE + "/com.kunzisoft.keepass.linklab.LabAboutActivity"
CASES_DIR = HERE.parent.parent / "app" / "sharedTest" / "resources"
HOST_DATA_SHA = hashlib.sha256((CASES_DIR / "tel-values.json").read_bytes()).hexdigest()
STATE = re.compile(r"LINKLAB_STATE (\{.*\})")


requirements: dict[str, list[str]] = {}  # case id -> requirement ids, from the case files


def case_ids(all_code: bool, listed: str | None) -> list[str]:
    """The cases to shoot: the listed ones, or every case of the code level (the order of the files).
    Fills `requirements` for every case of the files."""
    ids = []
    for path in sorted((CASES_DIR / "tel-cases").glob("*.json")):
        for case in json.loads(path.read_text(encoding="utf-8")):
            requirements[case["id"]] = case.get("requirements", [])
            if case.get("level", "code") == "code":
                ids.append(case["id"])
    if listed:
        wanted = [c.strip() for c in listed.split(",") if c.strip()]
        unknown = [c for c in wanted if c not in requirements]
        if unknown:
            raise SystemExit(f"unknown case(s): {unknown}")
        return wanted
    return ids


def near_life_cases(code_ids: list[str]) -> list[str]:
    """The first code case in the URL field of every value of near-life.json, in the order of that file."""
    cases = {}
    for path in sorted((CASES_DIR / "tel-cases").glob("*.json")):
        for case in json.loads(path.read_text(encoding="utf-8")):
            if case["id"] in code_ids and case.get("field", "url") == "url":
                cases.setdefault(case["value"], case["id"])
    entries = json.loads((CASES_DIR / "near-life.json").read_text(encoding="utf-8"))["entries"]
    return [cases[entry["value"]] for entry in entries]


def lab_state(case: str) -> dict | None:
    """The newest LINKLAB_STATE of this case in logcat, or None."""
    found = None
    for line in dv.adb("logcat", "-d", "-s", "LinkLab").splitlines():
        match = STATE.search(line)
        if match:
            state = json.loads(match.group(1))
            if state.get("case") == case:
                found = state
    return found


def show(case: str, lab_env: str) -> dict:
    """Start the lab on the case and wait until it says it is ready. The lab's own words, not a pause."""
    dv.adb("logcat", "-c")
    dv.adb("shell", "am", "start", "-n", LAB, "--es", "case-id", case, "--es", "env-id", lab_env)
    state = dv.wait_until(lambda: (s := lab_state(case)) and s.get("ready") and s, timeout=20, poll=0.3,
                          what=f"LinkLab to be ready for {case}")
    time.sleep(0.3)  # the last layout pass after the state line
    return state


def shoot_about(folder: Path, number: list[int]) -> list[Path]:
    """The start screen of the lab (its legend) is the first picture of every run: top, then the end of the text.
    It is what a reader of the pictures needs to read the rest."""
    dv.adb("shell", "am", "start", "-n", ABOUT)
    dv.wait_until(lambda: "LabAboutActivity" in dv.focus(), timeout=15, what="the About screen of LinkLab")
    time.sleep(0.5)
    written = []
    for view, swipes in (("top", 0), ("middle", 1), ("end", 3)):
        for _ in range(swipes):
            dv.swipe(540, 1900, 540, 600)
            time.sleep(0.4)
        number[0] += 1
        shot = dv.capture(f"about-{view}")
        path = folder / f"about_{number[0]:03d}-{view}.png"
        shot.write(path, screen="about", view=view)
        written.append(path)
    return written


def shoot(case: str, state: dict, folder: Path, scroll: bool, number: list[int]) -> list[Path]:
    written = []
    views = [("top", None)] + ([("scrolled", (540, 1900, 540, 700))] if scroll else [])
    for view, swipe in views:
        if swipe:
            dv.swipe(*swipe)
            time.sleep(0.5)
        number[0] += 1
        shot = dv.capture(f"{case}-{view}")
        path = folder / f"{case}_{number[0]:03d}-{view}.png"
        shot.write(path, case=case, value=state.get("value"), requirements=requirements.get(case), view=view,
                   lab_run=state.get("run"), lab_index=state.get("index"), lab_total=state.get("total"),
                   lab_seq=state.get("seq"), lab_schema=state.get("schema"), lab_data_sha256=state.get("data"),
                   lab_data_source=state.get("data_source"),
                   lab_data_matches_host=state.get("data") == HOST_DATA_SHA)
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cases")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--near-life", action="store_true", help="the code case of each value of near-life.json")
    parser.add_argument("--environment", default="cprima-dev")
    parser.add_argument("--lab-env", default="E-004")
    parser.add_argument("--no-scroll", action="store_true")
    args = parser.parse_args()
    if not args.cases and not args.all and not args.near_life:
        parser.error("give --cases, --all or --near-life")

    ids = case_ids(args.all or args.near_life, args.cases)
    if args.near_life:
        ids = near_life_cases(ids)
    env = fixture_spec.load_environment(args.environment)
    dv.configure([], env)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS / f"{stamp}-lab"
    run_dir.mkdir(parents=True)

    dv.SHOT_STATIC.clear()
    dv.SHOT_STATIC.update(context={"run": run_dir.name, "environment": env["name"]})
    detected = dv.detect_handlers()
    run_facts.collect(run_dir, run_dir.name, env, detected, None, HERE / "fixture-spec.generated.json",
                      CASES_DIR / "tel-values.json")
    dv.SHOT_STATIC["context"]["lab_environment"] = args.lab_env
    dv.SHOT_STATIC["context"]["tool"] = "lab_run.py"
    run_facts.write_env(run_dir, dv.SHOT_STATIC)

    dv.adb("shell", "am", "force-stop", env["target"])
    results, number = [], [0]
    try:
        folder = run_dir / "about"
        folder.mkdir()
        files = shoot_about(folder, number)
        results.append({"screen": "about", "result": "shot", "files": [f.name for f in files]})
        print(f"about: {len(files)} picture(s)")
    except Exception as problem:
        results.append({"screen": "about", "result": "error", "reason": f"{type(problem).__name__}: {problem}"})
        print(f"about: ERROR {problem}", file=sys.stderr)
    for case in ids:
        folder = run_dir / case
        folder.mkdir()
        try:
            state = show(case, args.lab_env)
            files = shoot(case, state, folder, not args.no_scroll, number)
            results.append({"case": case, "result": "shot", "files": [f.name for f in files]})
            print(f"{case}: {len(files)} picture(s)")
        except Exception as problem:  # the result is `error` with the reason; the run goes on
            results.append({"case": case, "result": "error", "reason": f"{type(problem).__name__}: {problem}"})
            print(f"{case}: ERROR {problem}", file=sys.stderr)
    dv.adb("shell", "am", "force-stop", env["target"])

    missing = shot_meta.verify_run(run_dir)
    report = {"run": run_dir.name, "lab_environment": args.lab_env, "cases": len(ids),
              "shot": sum(r["result"] == "shot" and "case" in r for r in results), "errors": sum(r["result"] == "error" for r in results),
              "sidecars_missing": missing, "results": results}
    (run_dir / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{report['shot']} of {len(ids)} cases shot, {report['errors']} errors, {len(missing)} files without sidecar -> {run_dir}")
    return 1 if report["errors"] or missing else 0


if __name__ == "__main__":
    sys.exit(main())
