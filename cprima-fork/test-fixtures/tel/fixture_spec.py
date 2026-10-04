"""Reads fixture-spec.json and the case file and works out what each fixture entry must hold.

Shared by populate.py (writes the database) and check_alignment.py (checks it).
"""

import json
import os
from pathlib import Path

HERE = Path(__file__).parent
SPEC_FILE = HERE / os.environ.get("TEL_SPEC", "fixture-spec.json")  # TEL_SPEC: another fixture, see near-life.json

READ_ONLY_LINE = "Open the database read-only, so that nothing here is saved."
CALL_LINE = "Never press the call button of the dialer. Go back after each step."


CODE_ENTRIES_FILE = HERE / "fixture-spec.code-entries.json"


def load_spec() -> dict:
    """fixture-spec.json, with the entries of fixture-spec.code-entries.json (make_code_entries.py)
    appended: one for every value of the code cases that no entry of the spec shows."""
    spec = json.loads(SPEC_FILE.read_text(encoding="utf-8"))
    if CODE_ENTRIES_FILE.exists() and SPEC_FILE.name == "fixture-spec.json":
        ids = {e["id"] for e in spec["entries"]}
        added = json.loads(CODE_ENTRIES_FILE.read_text(encoding="utf-8"))["entries"]
        spec["entries"] = spec["entries"] + [e for e in added if e["id"] not in ids]
    return spec


def load_environment(name: str) -> dict:
    """The profile of one phone and its apps (environments/<name>.json): the app under test, the apps
    to close, the dialer and the id of its number field. None of it belongs to the fixture."""
    path = HERE / "environments" / f"{name}.json"
    if not path.exists():
        known = sorted(p.stem for p in (HERE / "environments").glob("*.json"))
        raise FileNotFoundError(f"no environment {name!r}; known: {known}")
    return {**json.loads(path.read_text(encoding="utf-8")), "key": name}


def load_cases(spec: dict) -> dict:
    """Case id -> case, over the groups works, fails and observed."""
    path = (HERE / spec["casesFile"]).resolve()
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases = {}
    for group in ("works", "fails", "observed"):
        for case in raw.get(group, []):
            cases[case["id"]] = {**case, "group": group}
    return cases


def links_of(entry: dict, case: dict | None) -> list[dict]:
    """The complete list of links the value must show, in text order: the entry's own 'links' (a
    UI-only entry), else the links of the case it takes its value from. Each is {text, target}."""
    if "links" in entry:
        return entry["links"]
    return (case or {}).get("links", [])


def is_tel(link: dict) -> bool:
    return link["target"].lower().startswith("tel:")


def scenarios_of(entry: dict, case: dict | None) -> list[str]:
    """Scenarios of an entry: its own list, else derived from the links the value must show."""
    if "scenarios" in entry:
        return entry["scenarios"]
    links = links_of(entry, case)
    tel = [link for link in links if is_tel(link)]
    scenarios = []
    if tel:
        scenarios += ["UI-LINK", "UI-LONGPRESS", "UI-CALL"]
    scenarios += ["UI-WEB"] if any(link["target"].lower().startswith("http") for link in links) else []
    scenarios += ["UI-MAIL"] if any(link["target"].lower().startswith("mailto:") for link in links) else []
    if links and not tel:
        scenarios.append("UI-NOTEL")
    if not links:
        scenarios.append("UI-NOLINK")
    return scenarios


def value_of(entry: dict, cases: dict) -> str:
    """The tested value: the entry's own, or the input of the case named by valueFrom."""
    if "value" in entry:
        return entry["value"]
    case = cases[entry["valueFrom"]]
    if "input" not in case:
        raise ValueError(f"case {case['id']} has no plain input (generated?), give the entry a value")
    return case["input"]


def expected_of(entry: dict, case: dict | None) -> str:
    if "expected" in entry:
        return entry["expected"]
    if case is None:
        return ""
    links = case.get("links") or []
    if links:
        shown = ", ".join(repr(link["text"]) for link in links)
        text = f"Underlined: {shown}. The rest is plain."
    else:
        text = "Nothing is underlined."
    group = case["group"]
    if group == "observed":
        text += " Observed case: the current behaviour is recorded, no decision yet."
    note = case.get("note")
    return f"{text} {note}" if note else text


def instructions_of(entry: dict, spec: dict, cases: dict) -> str:
    """The text of the Notes field: instruction lines, then 'Expected', then the entry id."""
    if "notes" in entry:  # an entry with its own text (the near-life database)
        return "\n".join([entry["notes"], f"Expected: {expected_of(entry, None)}", f"Entry: {entry['id']}"])
    case = cases.get(entry.get("valueFrom", ""))
    lines = [READ_ONLY_LINE, CALL_LINE]
    number = 1
    for name in scenarios_of(entry, case):
        for step in spec["scenarios"][name]["steps"]:
            lines.append(f"{number}. [{name}] {step}")
            number += 1
    lines.append(f"Expected: {expected_of(entry, case)}")
    lines.append(f"Entry: {entry['id']}")
    return "\n".join(lines)


def wanted(spec: dict, cases: dict) -> dict:
    """Entry id -> {'url', 'notes', 'custom'}; the shape populate.py applies."""
    result = {}
    for entry in spec["entries"]:
        value = value_of(entry, cases)
        notes = instructions_of(entry, spec, cases)
        want = {"url": "", "notes": notes, "custom": {}}
        field = entry["field"]
        if field == "url":
            want["url"] = value
        elif field == "notes":
            # the tested value is the last line
            want["notes"] = f"{notes}\n{value}"
        elif field == "custom":
            want["custom"] = {spec["customFieldName"]: value}
        else:
            raise ValueError(f"entry {entry['id']}: field {field!r} not supported by the fixture")
        result[entry["id"]] = want
    return result
