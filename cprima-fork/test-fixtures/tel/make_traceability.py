"""Builds the results file of a code-level run and the traceability table from it.

Inputs: the requirements and the case files, and the raw results of one run:
  - the JUnit XML folders of the desktop run (environment E-003): the normal task and the known
    defects task,
  - the `am instrument -r` outputs of the phone run (environment E-004): the normal run and the
    known defects run.

Outputs, both in the wiki folder test-management:
  - runs/<run>.results.csv: case, environment, result (pass or fail) for every code case,
  - traceability.csv: one row per requirement, case and environment, with the latest applicable
    state. Device and manual cases are not executed yet and appear as `not covered` in E-001.

The environments are defined in test-management/environments.md. Run with uv:
  uv run python make_traceability.py --run 2026-10-03-03 --jvm-normal DIR --jvm-defects DIR \
      --phone-normal FILE --phone-defects FILE
"""

import argparse
import csv
import glob
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
FORK = HERE.parent.parent  # cprima-fork/
REPO = FORK.parent
CASES_DIR = FORK / "app" / "sharedTest" / "resources" / "tel-cases"
WIKI = REPO.parent / "KeePassDX.wiki" / "test-management"

ENV_JVM, ENV_PHONE, ENV_DEVICE = "E-003", "E-004", "E-001"
ENV_JVM28 = "E-007"  # the same desktop JVM run with Robolectric at sdk 28 (Android 9)
CODE_ENVIRONMENTS = (ENV_JVM, ENV_JVM28, ENV_PHONE)
CASE_NAME = re.compile(r"case\[(C-[A-Z]{2}-\d+)\]")


def jvm_results(folder: Path, class_suffix: str) -> dict[str, str]:
    """Case id -> pass or fail, from the JUnit XML of one task."""
    found: dict[str, str] = {}
    for path in glob.glob(str(folder / f"TEST-*{class_suffix}.xml")):
        for testcase in ET.parse(path).getroot().findall("testcase"):
            match = CASE_NAME.fullmatch(testcase.get("name", ""))
            if match:
                failed = testcase.find("failure") is not None or testcase.find("error") is not None
                found[match.group(1)] = "fail" if failed else "pass"
    return found


def phone_results(output: Path, class_suffix: str) -> dict[str, str]:
    """Case id -> pass or fail, from the output of `am instrument -r`."""
    found: dict[str, str] = {}
    block: dict[str, str] = {}
    for line in output.read_text(encoding="utf8", errors="replace").splitlines():
        status = re.match(r"INSTRUMENTATION_STATUS: (\w+)=(.*)", line)
        if status:
            block[status.group(1)] = status.group(2).strip()
            continue
        code = re.match(r"INSTRUMENTATION_STATUS_CODE: (-?\d+)", line)
        if code:
            klass, test = block.get("class", ""), block.get("test", "")
            match = CASE_NAME.fullmatch(test)
            # 1 = started, 0 = ok, anything else = failure or error
            if match and klass.endswith(class_suffix) and code.group(1) != "1":
                found[match.group(1)] = "pass" if code.group(1) == "0" else "fail"
            block = {}
    return found


DEFECT_TYPES = {"product", "testware", "environment", "documentation"}
DEFECT_STATUSES = {"open", "accepted", "fixed", "withdrawn"}
DEFECT_ROW = re.compile(r"^\| (D-\d{3,}) \| (\w+) \| (R-\d{3,}) \| (\w+) \|")


def load_defects(requirements: list[str]) -> tuple[dict[str, str], list[str]]:
    """Requirement id -> id of its defect, from the table of defects.md, and the problems found."""
    by_requirement: dict[str, str] = {}
    problems: list[str] = []
    seen: set[str] = set()
    path = WIKI / "defects.md"
    if not path.exists():
        return by_requirement, ["defects.md does not exist"]
    for number, line in enumerate(path.read_text(encoding="utf8").splitlines(), 1):
        match = DEFECT_ROW.match(line)
        if not match:
            continue
        defect, kind, requirement, status = match.groups()
        where = f"defects.md:{number} {defect}"
        if defect in seen:
            problems.append(f"{where}: the ID is used twice")
        seen.add(defect)
        if kind not in DEFECT_TYPES:
            problems.append(f"{where}: unknown type '{kind}'")
        if status not in DEFECT_STATUSES:
            problems.append(f"{where}: unknown status '{status}'")
        if requirement not in requirements:
            problems.append(f"{where}: unknown requirement {requirement}")
        if kind == "product" and status in {"open", "accepted"}:
            if requirement in by_requirement:
                problems.append(f"{where}: {requirement} already has {by_requirement[requirement]}")
            by_requirement[requirement] = defect
    return by_requirement, problems


def load_cases() -> list[dict]:
    cases = []
    for path in sorted(glob.glob(str(CASES_DIR / "*.json"))):
        cases += json.load(open(path, encoding="utf8"))
    return cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--jvm-normal", type=Path, required=True)
    parser.add_argument("--jvm-defects", type=Path, required=True)
    parser.add_argument("--phone-normal", type=Path, required=True)
    parser.add_argument("--phone-defects", type=Path, required=True)
    args = parser.parse_args()

    cases = load_cases()
    code_ids = {c["id"] for c in cases if c["level"] == "code"}

    results = {
        ENV_JVM: {**jvm_results(args.jvm_normal, "RequirementCasesTest"),
                  **jvm_results(args.jvm_defects, "RequirementCasesKnownDefectsTest")},
        ENV_JVM28: {**jvm_results(args.jvm_normal, "RequirementCasesApi28Test"),
                    **jvm_results(args.jvm_defects, "RequirementCasesKnownDefectsApi28Test")},
        ENV_PHONE: {**phone_results(args.phone_normal, "RequirementCasesInstrumentedTest"),
                    **phone_results(args.phone_defects, "RequirementCasesKnownDefectsInstrumentedTest")},
    }
    errors = []
    for environment, found in results.items():
        if set(found) != code_ids:
            errors.append(f"{environment}: missing {sorted(code_ids - set(found))[:5]} extra {sorted(set(found) - code_ids)[:5]}")
    for other in (ENV_PHONE, ENV_JVM28):
        if results[ENV_JVM] != results[other]:
            different = sorted(c for c in code_ids if results[ENV_JVM].get(c) != results[other].get(c))
            print(f"note: {ENV_JVM} and {other} differ in {different}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    # The verdict never reads `current`, but a case that fails while it says `matches` (or the other way
    # round) is a stale case file: report it.
    stale = [c["id"] for c in cases if c["level"] == "code"
             and (results[ENV_JVM][c["id"]] == "fail") != (c["current"] == "differs")]
    if stale:
        print(f"note: `current` disagrees with the result in {stale}")

    results_path = WIKI / "runs" / f"{args.run}.results.csv"
    with open(results_path, "w", encoding="utf8", newline="") as out:
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["case", "environment", "result"])
        for environment in CODE_ENVIRONMENTS:
            for case_id in sorted(results[environment]):
                writer.writerow([case_id, environment, results[environment][case_id]])

    requirement_rows = list(csv.DictReader(open(WIKI / "requirements.csv", encoding="utf8", newline="")))
    requirements = [r["id"] for r in requirement_rows]
    scope = {r["id"]: r["scope"] for r in requirement_rows}

    rows = []
    covered_requirements = set()

    def row(requirement, case="", level="", environment="", run="", coverage="not covered", result=""):
        return {"requirement": requirement, "scope": scope[requirement], "case": case, "level": level,
                "environment": environment, "run": run, "coverage": coverage, "result": result, "defect": ""}

    for case in cases:
        for requirement in case["requirements"]:
            covered_requirements.add(requirement)
            if case["level"] == "code":
                for environment in CODE_ENVIRONMENTS:
                    rows.append(row(requirement, case["id"], "code", environment, args.run,
                                    "covered", results[environment][case["id"]]))
            else:
                rows.append(row(requirement, case["id"], case["level"], ENV_DEVICE))
    for requirement in requirements:
        if requirement not in covered_requirements:
            rows.append(row(requirement))
    rows.sort(key=lambda r: (r["requirement"], r["case"], r["environment"]))

    # A failing case of an in-scope requirement names the defect of that requirement. A failing case of an
    # out-of-scope requirement is evidence of the boundary: it stays a visible failure and names no defect.
    defects, problems = load_defects(requirements)
    for r in rows:
        if r["result"] == "fail" and r["scope"] == "in":
            if r["requirement"] in defects:
                r["defect"] = defects[r["requirement"]]
            else:
                problems.append(f"{r['case']} in {r['environment']}: fails, and {r['requirement']} has no defect in defects.md")
    failing_in_scope = {r["requirement"] for r in rows if r["result"] == "fail" and r["scope"] == "in"}
    for requirement, defect in defects.items():
        if scope[requirement] == "out":
            problems.append(f"{defect}: {requirement} is out of scope and cannot have a defect")
        elif requirement not in failing_in_scope:
            problems.append(f"{defect}: {requirement} has no failing case in this run (fixed?)")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1

    trace_path = WIKI / "traceability.csv"
    fields = ["requirement", "scope", "case", "level", "environment", "run", "coverage", "result", "defect"]
    with open(trace_path, "w", encoding="utf8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print(f"{results_path.name}: {sum(len(v) for v in results.values())} results")
    print(f"{trace_path.name}: {len(rows)} rows for {len(requirements)} requirements")
    return 0


if __name__ == "__main__":
    sys.exit(main())
