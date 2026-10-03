"""Generates a fixture spec from the case files, so that the cases are the source of the device run.

Reads tel-values.json and tel-cases/*.json (cprima-fork/app/sharedTest/resources) and the hand-kept parts of the
current fixture-spec.json (database, dialogs, scenario texts, custom field name). Writes
fixture-spec.generated.json next to it. The current spec is not touched; ui_test.py, populate.py and
check_alignment.py read the same format.

Two kinds of entry, told apart by `purpose`:
  case    one entry per fixture of a device or manual case; `cases` lists the case ids that use it.
          Only these entries may produce results of cases.
  visual  an entry that only shows a value in the real field (the old display-only entries). It gives
          evidence, never a result of a case.

Run:  uv run python make_fixture_spec.py
"""

import glob
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESOURCES = HERE.parent.parent / "app" / "sharedTest" / "resources"
CURRENT_SPEC = HERE / "fixture-spec.json"
GENERATED_SPEC = HERE / "fixture-spec.generated.json"

# The order in which scenarios are listed for an entry, as in the current spec
SCENARIO_ORDER = ["UI-LINK", "UI-WEB", "UI-MAIL", "UI-NOLINK", "UI-NOTEL", "UI-TAP", "UI-LONGPRESS",
                  "UI-LONGPRESS-TWO", "UI-WRAP", "UI-CALL", "UI-REOPEN", "UI-EDIT", "UI-COPY"]


def load_values() -> dict[str, str]:
    values = {}
    for value in json.load(open(RESOURCES / "tel-values.json", encoding="utf8")):
        if "generated" in value:
            continue
        values[value["id"]] = value["value"]
    return values


def load_cases() -> list[dict]:
    cases = []
    for path in sorted(glob.glob(str(RESOURCES / "tel-cases" / "*.json"))):
        cases += json.load(open(path, encoding="utf8"))
    return cases


def kind_of(text: str) -> str:
    if text.lower().startswith("http"):
        return "web"
    if "@" in text:
        return "mail"
    return "tel"


def link_of(text: str) -> dict:
    kind = kind_of(text)
    target = text if kind == "web" else ("mailto:" + text if kind == "mail" else "tel:" + text)
    return {"text": text, "target": target}


def links_for(case: dict, code_cases: list[dict]) -> list[dict]:
    """The complete list of links the value must show: the expected links of a code case with the same
    value, else built from the underlined texts of the device case."""
    if case.get("field", "url") != "url":
        return []
    for code in code_cases:
        if code["value"] == case["value"] and code.get("field", "url") == "url":
            return code["expected"]["links"]
    return [link_of(text) for text in case["expected"].get("underline", [])]


def scenarios_for(case: dict, links: list[dict]) -> list[str]:
    """The old scenario names that cover what the steps of the case do."""
    steps = case["steps"]
    verbs = [s["do"] for s in steps]
    targets = [s.get("target", "") for s in steps]
    web = any(l["target"].lower().startswith("http") for l in links)
    mail = any(l["target"].lower().startswith("mailto:") for l in links)
    tel = any(l["target"].lower().startswith("tel:") for l in links)
    found = []
    if "look" in verbs or "tap" in verbs or "longpress" in verbs:
        if tel:
            found.append("UI-LINK")
        elif web:
            found.append("UI-WEB")
            if "tel:" in "".join(case.get("_text", "")).lower():
                found.append("UI-NOTEL")
        elif mail:
            found.append("UI-MAIL")
        elif "look" in verbs:
            found.append("UI-NOLINK")
    # UI-LONGPRESS-TWO and UI-WRAP already contain their own taps, long-presses and Call steps
    special = "link:2" in targets or "link:second-line" in targets
    if "tap" in verbs and tel and not special:
        found.append("UI-TAP")
    if "longpress" in verbs:
        if "link:2" in targets:
            found.append("UI-LONGPRESS-TWO")
        elif "link:second-line" in targets:
            found.append("UI-WRAP")
        else:
            found.append("UI-LONGPRESS")
    elif "link:second-line" in targets:
        found.append("UI-WRAP")
    if "call" in verbs and not special:
        found.append("UI-CALL")
    if "reopen" in verbs:
        found.append("UI-REOPEN")
    if "edit" in verbs:
        found.append("UI-EDIT")
    if "copy" in verbs:
        found.append("UI-COPY")
    return found


def prose(case: dict) -> str:
    """The expected text of the Notes field, from the keys of `expected`."""
    expected = case["expected"]
    parts = []
    if "underline" in expected:
        shown = ", ".join(repr(t) for t in expected["underline"])
        parts.append(f"Underlined: {shown}. The rest is plain." if expected["underline"] else "Nothing is underlined.")
    if expected.get("underlineContinuousOverBothLines"):
        parts.append("The underline is continuous over both lines.")
    for step in ("tap", "call"):
        part = expected.get(step, {})
        if "uri" in part:
            parts.append(f"The {step} hands over {part['uri']}.")
        if "opens" in part:
            parts.append(f"The tap opens the {part['opens']}.")
    if "longPress" in expected:
        part = expected["longPress"]
        if "selection" in part:
            parts.append(f"A long-press highlights {part['selection']!r}.")
        if "toolbar" in part:
            parts.append("The toolbar contains: " + ", ".join(part["toolbar"]) + ".")
    for key, text in (("clipboard", "The copy button copies"), ("editFieldText", "Edit mode shows")):
        if key in expected:
            parts.append(f"{text} {expected[key]!r}.")
    return " ".join(parts)


def main() -> int:
    values = load_values()
    cases = load_cases()
    code_cases = [c for c in cases if c["level"] == "code"]
    device_cases = [c for c in cases if c["level"] in ("device", "manual")]
    current = json.load(open(CURRENT_SPEC, encoding="utf8"))
    old_cases = json.load(open(HERE / current["casesFile"], encoding="utf8"))
    old_input = {c["id"]: c.get("input") for g in ("works", "fails", "observed") for c in old_cases[g]}

    entries: dict[str, dict] = {}
    unsupported = []
    for case in device_cases:
        text = values[case["value"]]
        field = case.get("field", "url")
        entry_id = case["fixture"] or f"case-{case['id']}"
        if field == "url" and "protected" in case["preconditions"]:
            unsupported.append({"case": case["id"], "why": case.get("note", "the fixture cannot hold this yet")})
            continue
        links = links_for(case, code_cases)
        scenarios = scenarios_for({**case, "_text": text}, links)
        if entry_id in entries:
            entry = entries[entry_id]
            if entry["value"] != text or entry["field"] != field:
                print(f"conflict: {entry_id} is used with two values", file=sys.stderr)
                return 1
            entry["cases"].append(case["id"])
            entry["scenarios"] = [s for s in SCENARIO_ORDER if s in set(entry["scenarios"]) | set(scenarios)]
            if links != entry["links"]:
                print(f"note: {entry_id}: the cases expect different links; the first is kept", file=sys.stderr)
            entry["expected"] += " " + prose(case)
        else:
            entries[entry_id] = {"id": entry_id, "purpose": "case", "cases": [case["id"]], "field": field,
                                 "value": text, "links": links,
                                 "scenarios": [s for s in SCENARIO_ORDER if s in scenarios],
                                 "expected": prose(case)}

    # The old display-only entries that no case entry covers become visual entries, from the value of the
    # code case that took over the old case
    by_legacy = {legacy: c for c in code_cases for legacy in c["legacy"]}
    taken_values = {(e["field"], e["value"]) for e in entries.values()}
    visual = 0
    for old in current["entries"]:
        if "valueFrom" not in old or "scenarios" in old:
            continue
        case = by_legacy.get(old["valueFrom"])
        if case is None:
            print(f"warning: no case took over {old['valueFrom']}", file=sys.stderr)
            continue
        text = values.get(case["value"], old_input.get(old["valueFrom"]))
        if (old["field"], text) in taken_values:
            continue
        taken_values.add((old["field"], text))
        entry_id = f"visual-{case['value']}"
        entries[entry_id] = {"id": entry_id, "purpose": "visual", "field": old["field"], "value": text,
                             "links": case["expected"]["links"] if old["field"] == "url" else []}
        visual += 1

    # An entry that the current spec has keeps the scenarios it has there, so that the device run covers
    # at least what it covered before; the scenarios of the cases are added to them
    import fixture_spec
    old_cases_by_id = fixture_spec.load_cases(current)
    for old in current["entries"]:
        if old["id"] in entries:
            old_scenarios = fixture_spec.scenarios_of(old, old_cases_by_id.get(old.get("valueFrom", "")))
            entry = entries[old["id"]]
            entry["scenarios"] = [s for s in SCENARIO_ORDER if s in set(entry["scenarios"]) | set(old_scenarios)]

    generated = {k: v for k, v in current.items() if k not in ("entries", "description")}
    generated["description"] = ("Generated by make_fixture_spec.py from tel-values.json and tel-cases/*.json; "
                                "do not edit. Entries with purpose 'case' belong to device cases (field "
                                "'cases'); entries with purpose 'visual' only show a value and give evidence, "
                                "never a result of a case.")
    generated["entries"] = list(entries.values())
    generated["unsupported"] = unsupported
    GENERATED_SPEC.write_text(json.dumps(generated, indent=2, ensure_ascii=True) + "\n", encoding="utf8")
    print(f"{GENERATED_SPEC.name}: {len(entries) - visual} case entries, {visual} visual entries, "
          f"{len(unsupported)} unsupported")
    return 0


if __name__ == "__main__":
    sys.exit(main())
