"""Writes the documentation table of the near-life database from two runs on the phone.

    uv run python make_near_life_doc.py runs/<ui run>/report.json runs/<lab run>/diagnostics.jsonl <page.md>

For every entry of near-life.json: the stored text; what KeePassDX links (LinkLab, the spans of the real
field view); what the dialer holds after a tap and what a long-press selects and offers (ui_test.py on the
database tel-link-examples.kdbx). The words come from the runs, not from an expectation.
"""

import glob
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESOURCES = HERE.parent.parent / "app" / "sharedTest" / "resources"
INVISIBLE = {0x00A0, 0x200E, 0x202A, 0x202E, 0x2066, 0x2067, 0x2069}


def cell(text: str) -> str:
    shown = "".join(f"<U+{ord(c):04X}>" if ord(c) < 32 or ord(c) in INVISIBLE else c for c in text)
    return "`" + shown.replace("|", "\\|") + "`"


def scenario(entry: dict, name: str) -> dict | None:
    return next((s for s in entry.get("scenarios", []) if s["scenario"] == name), None)


def linked(spans: list[dict]) -> str:
    tel = [s for s in spans if s["url"].lower().startswith("tel:")]
    return ", ".join(cell(s["text"]) for s in tel) if tel else "no link"


def usable(entry: dict | None, link: str) -> bool:
    """Whether the UI steps of an entry say something about the app. When LinkLab shows a link but the run
    could not find it on the screen, the later steps pressed somewhere else: they are not used."""
    if entry is None or link == "no link":
        return entry is not None
    step = scenario(entry, "UI-LINK")
    if step is None:
        return False
    return step["state"] == "pass" or (step["state"] == "fail" and "is not drawn as a link" not in step["detail"])


def intention(item: dict) -> str:
    """The meaning of an entry for the reader: what it shows, without the full stop."""
    return item["what"].rstrip(".")


def tapped(entry: dict | None) -> str:
    step = scenario(entry, "UI-TAP") if entry else None
    if step is None:
        return "not tested"
    held = re.search(r"holds '([^']*)'", step["detail"])
    if held:
        return cell(held.group(1))
    if "did not leave the app" in step["detail"]:
        return "nothing happens"
    return "not read"


def pressed(entry: dict | None) -> tuple[str, str]:
    step = scenario(entry, "UI-LONGPRESS") if entry else None
    if step is None:
        return "not tested", ""
    found = re.search(r"copied '([^']*)'(?:, expected '[^']*')?; toolbar: (.*)$", step["detail"])
    if not found:
        return "not read", ""
    return cell(found.group(1)), ("yes" if "Call" in found.group(2).split(", ") else "no")


def dialed_by_entry(path: str | None) -> dict[str, str]:
    """What the emulator's telephony dialled for the links of each entry (dial_out_test.py), by entry title."""
    found: dict[str, list[str]] = {}
    if path:
        for line in Path(path).read_text(encoding="utf-8").splitlines()[1:]:
            row = json.loads(line)
            if row.get("url") is None:
                continue
            word = cell(row["dialed"]) if row.get("dialed") else ("never dialled" if "emergency" in row["state"] else "no call")
            found.setdefault(row["entry"], []).append(word)
    return {title: ", ".join(words) for title, words in found.items()}


def main(report_path: str, lab_path: str, out_path: str, dial_path: str | None = None) -> int:
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    source = json.loads((RESOURCES / "near-life.json").read_text(encoding="utf-8"))
    spec = json.loads((HERE / "near-life-spec.json").read_text(encoding="utf-8"))
    by_title = {e["id"]: e for e in spec["entries"]}
    meta = report["meta"]
    dials = dialed_by_entry(dial_path)

    cases = []
    for path in sorted(glob.glob(str(RESOURCES / "tel-cases" / "*.json"))):
        cases += json.loads(Path(path).read_text(encoding="utf-8"))
    case_of: dict[str, str] = {}
    for case in cases:
        if case["level"] == "code" and case.get("field", "url") == "url":
            case_of.setdefault(case["value"], case["id"])
    spans: dict[str, list[dict]] = {}
    for line in Path(lab_path).read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("probe") == "link.field":
            spans[record["case"]] = record["spans"]

    lines = [
        "> **Status:** draft  ",
        f"> **Run:** {meta['started'][:10]}, {meta['device']} with Android {meta['android']}, KeePassDX `{meta['app_version']}`  ",
        "",
        "# Telephone links as people write them",
        "",
        "What KeePassDX does with a telephone number in the URL field, for the ways people really write one. "
        "Every row is a fictional address-book entry in the database `tel-link-examples.kdbx`; the second column is "
        "exactly the stored text. The other columns are what the phone showed in an automatic run:",
        "",
        "- **Linked**: the text that KeePassDX underlines as a `tel:` link.",
        "- **Tap**: the number the dialer holds after a tap on the link. \"nothing happens\": the tap stayed in KeePassDX.",
        "- **Long-press**: the text that a long-press selects and copies, and whether Android offers *Call* in the toolbar.",
        "- **Dialled (Android 9 emulator)**: the number that the telephony of an emulator passes to its simulated modem when the link is dialled. This shows what the dialer does with hyphens, dots and brackets; it is another dialer than the one of the phone, and no call leaves the computer.",
        "",
        "| What it shows | Stored text | Linked | Tap: the dialer holds | Dialled (emulator) | Long-press: selected | *Call* offered |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in source["entries"]:
        value = by_title[item["title"]]["value"]
        entry = report["entries"].get(item["title"])
        link = linked(spans.get(case_of[item["value"]], []))
        trusted = entry if usable(entry, link) else None
        tap = tapped(trusted) if link != "no link" else "-"
        selected, call = pressed(trusted) if link != "no link" else ("-", "")
        lines.append(f"| {intention(item)} | {cell(value)} | {link} | {tap} | {dials.get(item['title'], '-')} | {selected} | {call} |")

    lines += ["", "\"not read\": the run could not read the value on the screen. \"not tested\": the step was not run for "
              "that entry, or the run could not find the link on the screen and so did not press it. \"-\": there is no link, so there is nothing to tap or select."]
    Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"{out_path}: {len(source['entries'])} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
