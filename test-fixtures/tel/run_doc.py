"""Write the complete documentation of a UI test run: every entry, every scenario, what was expected,
what was found (as-is) and every screenshot.

Reads runs/<run>/report.json and run.log.jsonl (written by ui_test.py) and the fixture spec with its
case file, and writes runs/<run>/RUN.md. Image links are relative, so the file reads in any Markdown
viewer next to its screenshots. Nothing is measured here: the file only puts together what the run
recorded and what the spec expects.

    uv run python run_doc.py                 # the newest run
    uv run python run_doc.py <run folder>
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

import fixture_spec

HERE = Path(__file__).parent
RUNS = HERE / "runs"

# What each scenario expects, in words. The checks are the runner's (ui_test.py); this is their plain
# reading, with the entry's own values filled in.
SCENARIO_TITLES = {
    "UI-LINK": "The link in view mode",
    "UI-TAP": "Tap on the link",
    "UI-LONGPRESS": "Long-press on the link",
    "UI-CALL": "Call in the selection toolbar",
    "UI-LONGPRESS-TWO": "Long-press with two numbers",
    "UI-WRAP": "A number that wraps over two lines",
    "UI-NOLINK": "No phone link",
    "UI-NOTEL": "Only another link, no phone link",
    "UI-WEB": "Tap on the web address",
    "UI-MAIL": "Tap on the e-mail address",
    "UI-REOPEN": "Reopen the entry",
    "UI-EDIT": "Edit mode shows the plain value",
    "UI-COPY": "Copy button",
}


def shown(text: str) -> str:
    """A value with its invisible characters written out, so that it can be read."""
    out = []
    for ch in text:
        if ch == "\n":
            out.append("\\n")
        elif ch.isprintable() and ch != "\u00a0":
            out.append(ch)
        else:
            out.append(f"\\u{ord(ch):04x}")
    return "".join(out)


def md(text: str) -> str:
    """Text safe inside a table cell or a paragraph."""
    return text.replace("|", "\\|").replace("\n", " ")


def code(text: str) -> str:
    return "`" + shown(text).replace("`", "'") + "`"


def expectation(scenario: str, links: list[dict], value: str) -> str:
    tel = [link for link in links if link["target"].lower().startswith("tel:")]
    texts = ", ".join(code(link["text"]) for link in tel)
    other = [link for link in links if link not in tel]
    if scenario == "UI-LINK":
        base = f"Underlined: {', '.join(code(link['text']) for link in links)}. The rest of the value is plain" if links else "Nothing is underlined"
        return base + ". The prefix before a tel link is not underlined."
    if scenario == "UI-TAP":
        return "The tap leaves the app: the system asks which app opens the number, or the default dialer opens. Back returns."
    if scenario == "UI-LONGPRESS":
        pressed = (tel or links)[0] if (tel or links) else None
        if pressed is None:
            return "The selection is exactly the link text."
        return f"The selection is exactly {code(pressed['text'])}" + (" (the first tel link; the toolbar offers Call)." if tel else " (the first link).")
    if scenario == "UI-CALL":
        if not tel:
            return "After Call the dialer holds the target without `tel:`. Call is never pressed."
        return f"After Call the dialer holds {code(tel[0]['target'][4:])} (the target without `tel:`). Call is never pressed."
    if scenario == "UI-LONGPRESS-TWO":
        return "A long-press on the second number selects only that number, and Call gives only that number."
    if scenario == "UI-WRAP":
        return "The underline is continuous over both lines; a tap and a long-press on the second line select the whole number."
    if scenario == "UI-NOLINK":
        return "No part of the value is drawn in the link colour."
    if scenario == "UI-NOTEL":
        return "A tap on the text opens the web address in the browser, not the dialer."
    if scenario == "UI-WEB":
        return "A tap on the web address opens the browser with its host."
    if scenario == "UI-MAIL":
        return "A tap on the e-mail address opens the composer addressed to it."
    if scenario == "UI-REOPEN":
        return "After closing and opening the entry again the value looks pixel-identical."
    if scenario == "UI-EDIT":
        return f"Edit mode shows the plain value {code(value)}. Nothing is saved."
    if scenario == "UI-COPY":
        return "The copy button copies the value (not implemented: the clipboard cannot be read over adb)."
    return ""


def category(detail: str, state: str) -> str:
    """A short label for what a non-pass looked like, to group them."""
    if state == "pass":
        return ""
    low = detail.lower()
    if "toolbar has no call" in low:
        return "no Call in the selection toolbar"
    if "selected '" in low and "expected '" in low:
        return "the selection differs from the link text"
    if "holds '" in low and "expected '" in low:
        return "the dialer holds something else"
    if "not drawn as a link" in low:
        return "the link is not drawn"
    if "no word of the value could be located" in low or "no position found" in low:
        return "the OCR could not locate the text"
    if "notimplemented" in low:
        return "not implemented"
    if low.startswith("not run"):
        return "not run (an earlier scenario failed)"
    return "other"


def main() -> int:
    run = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted(p for p in RUNS.iterdir() if (p / "report.json").exists())[-1]
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    meta, entries = report["meta"], report["entries"]
    spec = fixture_spec.load_spec()
    cases = fixture_spec.load_cases(spec)
    by_id = {entry["id"]: entry for entry in spec["entries"]}
    events = [json.loads(line) for line in (run / "run.log.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    selections = {}
    for event in events:
        if event.get("event") == "selection":
            selections.setdefault(event["entry"], []).append(event)

    def path_of(entry_id: str, name: str) -> str:
        """A recorded file name as a path from the run folder: some are recorded relative to the entry's folder."""
        return name if (run / name).exists() else f"{entry_id}/{name}"

    for entry_id, result in entries.items():
        for scenario in result["scenarios"]:
            scenario["shots"] = [path_of(entry_id, name) for name in scenario["shots"]]
            scenario["evidence"] = [path_of(entry_id, name) for name in scenario.get("evidence", [])]

    states = Counter(result["state"] for result in entries.values())
    scenario_states = Counter(s["state"] for result in entries.values() for s in result["scenarios"])
    groups = Counter(category(s["detail"], s["state"]) for result in entries.values() for s in result["scenarios"] if s["state"] != "pass")
    shots = sorted(p.relative_to(run).as_posix() for p in run.rglob("*") if p.is_file() and p.suffix in (".png", ".xml", ".json") and p.name != "report.json")

    out: list[str] = []
    w = out.append
    w(f"# UI test run {run.name}")
    w("")
    w("Complete documentation of one run: every entry, every scenario, what was expected, what was found, and the screenshots. Generated by `run_doc.py` from `report.json` and `run.log.jsonl`; nothing is re-measured.")
    w("")
    w("**Not for publication as it is.** The screenshots show the status bar (clock, notifications) and the phone's own apps. Crop the status bar and strip the metadata first (`just fork strip-png`). No screenshot of the share sheet is kept: it lists contacts.")
    w("")
    w("## Run")
    w("")
    w("| | |")
    w("|---|---|")
    w(f"| Started | {meta['started']} |")
    w(f"| Fixture | `{meta['phone_file']}`, SHA-256 `{meta['fixture_sha256']}` |")
    w(f"| Device | {meta['device']}, Android {meta['android']} |")
    w(f"| App | KeePassDX {meta['app_version']} |")
    w(f"| Environment | {meta['environment']} |")
    w("| Detected apps | " + ", ".join(f"{k}: `{v}`" for k, v in meta["detected_apps"].items()) + " |")
    pre = (meta.get("fingerprint") or {}).get("preconditions", [])
    if pre:
        w("| Preconditions | " + "; ".join(f"{p['id']} ({'ok' if p['ok'] else 'NOT ok'}: {md(str(p['actual']))})" for p in pre) + " |")
    w("")
    w("## Result")
    w("")
    w(f"**{len(entries)} entries: {states['pass']} pass, {states['fail']} fail, {states['error']} error.** In scenarios: {scenario_states['pass']} pass, {scenario_states['fail']} fail, {scenario_states['error']} error ({sum(scenario_states.values())} in all). {len(shots)} screenshots and evidence files are linked below.")
    w("")
    w("- **pass:** what was found equals what was expected.")
    w("- **fail:** the expectation was not met. The expectation comes from the case file and is never adapted to the observation.")
    w("- **error:** the scenario could not be carried out. The cause column says why: `system` (the phone or app was in the wrong state; recovered and repeated once), `script` (a limit or a bug of the script), `data` (the phone does not hold what the spec says).")
    w("")
    w("### What the non-passes look like (as recorded; no explanation is claimed)")
    w("")
    w("| What was seen | Scenarios |")
    w("|---|---|")
    for label, count in groups.most_common():
        w(f"| {label} | {count} |")
    w("")
    w("### All entries")
    w("")
    w("| # | Entry | Group | Field | Value | Verdict |")
    w("|---|---|---|---|---|---|")
    order = [entry["id"] for entry in spec["entries"]]
    for number, entry_id in enumerate(order, 1):
        if entry_id not in entries:
            continue
        entry = by_id[entry_id]
        case = cases.get(entry.get("valueFrom", ""))
        value = fixture_spec.value_of(entry, cases)
        group = case["group"] if case else "UI-only"
        verdict = entries[entry_id]["state"].upper()
        w(f"| {number} | [{entry_id}](#{entry_id}) | {group} | {entry['field']} | {md(code(value))} | {verdict} |")
    w("")
    if (run / "_calibration").exists():
        w("### Calibration")
        w("")
        w("The colour of a link is measured once on a known link before the entries, and every UI-LINK and UI-NOLINK verdict compares against it.")
        for p in sorted((run / "_calibration").glob("*.png")):
            w("")
            w(f"![calibration]({p.relative_to(run).as_posix()})")
        w("")
    w("## Entries")
    for number, entry_id in enumerate(order, 1):
        if entry_id not in entries:
            continue
        entry = by_id[entry_id]
        case = cases.get(entry.get("valueFrom", ""))
        value = fixture_spec.value_of(entry, cases)
        links = fixture_spec.links_of(entry, case)
        result = entries[entry_id]
        w("")
        w(f'<a id="{entry_id}"></a>')
        w(f"### {number}. {entry_id}: {result['state'].upper()}")
        w("")
        w(f"- **Field:** {entry['field']}")
        w(f"- **Value:** {code(value)}")
        if case:
            w(f"- **Case:** `{case['id']}` ({case['group']})" + (f", decision {case['decision']}" if case.get("decision") else ""))
            if case.get("note"):
                w(f"- **Note of the case:** {md(case['note'])}")
        if entry.get("why"):
            w(f"- **Why the entry exists:** {md(entry['why'])}")
        w("- **Links expected in the value:** " + (", ".join(f"{code(l['text'])} -> `{l['target']}`" for l in links) if links else "none"))
        for selection in selections.get(entry_id, []):
            w(f"- **Selection read by the run:** {code(selection['selected'])}, expected {code(selection['expected'])}, toolbar: {', '.join(selection.get('toolbar') or selection.get('names') or [])}" if "toolbar" in selection or "names" in selection else f"- **Selection read by the run:** {code(selection['selected'])}, expected {code(selection['expected'])}")
        for scenario in result["scenarios"]:
            name = scenario["scenario"]
            w("")
            w(f"#### {entry_id} / {name}: {scenario['state'].upper()}")
            w("")
            w(f"- **Scenario:** {SCENARIO_TITLES.get(name, name)}")
            w(f"- **Expected:** {md(expectation(name, links, value))}")
            w(f"- **As-is:** {md(scenario['detail'])}")
            tries = f", tries {scenario['attempts']}" if scenario.get("attempts", 1) != 1 else ""
            cause = f", cause: {scenario['cause']}" if scenario.get("cause") else ""
            w(f"- **Verdict:** {scenario['state']}{cause}{tries}")
            files = scenario["shots"] + scenario.get("evidence", [])
            for shot in files:
                if shot.endswith(".png"):
                    w("")
                    w(f"![{entry_id} {name}: {Path(shot).name}]({shot})")
                    w(f"*{shot}*")
                else:
                    w(f"- Evidence file: [{shot}]({shot})")
        # files of the entry that no scenario names: the view screenshot of a no-link scenario, error evidence
        named = {f for s in result["scenarios"] for f in s["shots"] + s["evidence"]}
        rest = sorted(p.relative_to(run).as_posix() for p in (run / entry_id).glob("*") if p.relative_to(run).as_posix() not in named)
        if rest:
            w("")
            w(f"#### {entry_id}: other files of the entry")
            for shot in rest:
                if shot.endswith(".png"):
                    w("")
                    w(f"![{entry_id}: {Path(shot).name}]({shot})")
                    w(f"*{shot}*")
                else:
                    w(f"- [{shot}]({shot})")
    w("")
    w("## Files")
    w("")
    w("- `report.json`: the results as data. `report.md`: the short table. `run.log.jsonl`: every step of the run, with times.")
    w(f"- {len(shots)} screenshots and evidence files, linked above. Error evidence (`error-N.png`, `error-N-dump.xml`, `error-N-ui.json`) shows what was on the phone when a scenario failed to run.")
    (run / "RUN.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"{run / 'RUN.md'}: {len(entries)} entries, {sum(scenario_states.values())} scenarios, {len(shots)} files linked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
