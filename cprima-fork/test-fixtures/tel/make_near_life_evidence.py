"""Writes the evidence page of the near-life database: for every entry a cropped picture of the entry view,
of the long-press, and of the dialer after a tap.

    uv run python make_near_life_evidence.py runs/<ui run> runs/<lab run>/diagnostics.jsonl <wiki folder>

The pictures are the ones ui_test.py published (status bar already cut, metadata stripped). They are cut
further to the part that carries the evidence and scaled to 720 px width, and written to
<wiki folder>/tel-link-examples/. The page is <wiki folder>/Tel-Link-Examples-Evidence.md.
"""

import glob
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import make_near_life_doc as doc

HERE = Path(__file__).resolve().parent
RESOURCES = doc.RESOURCES
WIDTH = 720
# pixel rows of the published pictures (1080 wide): the Password row, the URL row with the toolbar above it
# and the handles under it, and the Notes label. The dialer's number field is a fixed place too.
ENTRY_BOX = (0, 490, 1080, 1010)
DIALER_BOX = (0, 1090, 1080, 1340)


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def placeholder(label: str, box: tuple[int, int, int, int], target: Path) -> None:
    """A picture of the size of a cropped one with a short word on it, so that a column keeps its width."""
    width, height = WIDTH, round((box[3] - box[1]) * WIDTH / (box[2] - box[0]))
    image = Image.new("RGB", (width, height), (34, 40, 36))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except OSError:
        font = ImageFont.load_default()
    left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
    draw.text(((width - (right - left)) / 2 - left, (height - (bottom - top)) / 2 - top), label,
              fill=(150, 160, 152), font=font)
    image.save(target, optimize=True)


def crop(source: Path, box: tuple[int, int, int, int], target: Path) -> bool:
    if not source.exists():
        return False
    with Image.open(source) as image:
        part = image.crop(box)
        part = part.resize((WIDTH, round(part.height * WIDTH / part.width)))
        part.save(target, optimize=True)
    return True


def main(run_dir: str, lab_path: str, wiki: str, dial_path: str | None = None) -> int:
    run = Path(run_dir)
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    source = json.loads((RESOURCES / "near-life.json").read_text(encoding="utf-8"))
    spec = json.loads((HERE / "near-life-spec.json").read_text(encoding="utf-8"))
    by_title = {e["id"]: e for e in spec["entries"]}
    meta = report["meta"]
    dials = doc.dialed_by_entry(dial_path)

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

    folder = Path(wiki) / "tel-link-examples"
    folder.mkdir(parents=True, exist_ok=True)
    lines = [
        "> **Status:** draft  ",
        f"> **Run:** {meta['started'][:10]}, {meta['device']} with Android {meta['android']}, KeePassDX `{meta['app_version']}`  ",
        "",
        "# Telephone links as people write them: pictures",
        "",
        "## A valid number (RFC 3966)",
        "",
        "- **Global:** `+`, then digits, with `-` `.` `(` `)` allowed between them. At least one digit. No spaces, no letters.",
        "- **Local** (no `+`): valid only with a `;phone-context=` that says where it applies.",
        "- Anything else is not a valid number. [Details](Research-RFC-3966).",
        "",
        "The pictures behind [Tel-Link-Examples](Tel-Link-Examples). Per entry: the entry view, the dialer after a tap on the "
        "link, and a long-press on the link (the toolbar above it). A grey picture with \"-\" means that there is no link to press. \"not tested\" means that the run did not "
        "press it: the step was not run, or the run could not find the link on the screen.",
        "",
    ]
    shown = 0
    for item in source["entries"]:
        title = item["title"]
        name = item["value"].lower()  # the value id: a neutral file name
        value = by_title[title]["value"]
        entry = report["entries"].get(title)
        link = doc.linked(spans.get(case_of[item["value"]], []))
        trusted = doc.usable(entry, link)
        published = run / "published" / title
        tap_picture = "tap-dialer.png" if (published / "tap-dialer.png").exists() else "tap.png"
        why = "-" if link == "no link" else "not tested"
        made = {"view": crop(published / "01-view.png", ENTRY_BOX, folder / f"{name}-view.png")}
        if not made["view"]:
            placeholder("not tested", ENTRY_BOX, folder / f"{name}-view.png")
        for key, source_name, box in (("tap", tap_picture, DIALER_BOX if tap_picture == "tap-dialer.png" else ENTRY_BOX),
                                      ("longpress", "longpress.png", ENTRY_BOX)):
            if trusted and link != "no link" and crop(published / source_name, box, folder / f"{name}-{key}.png"):
                continue
            placeholder(why, box, folder / f"{name}-{key}.png")
        made = {"view": True, "tap": True, "long-press": True}
        shown_entry = entry if trusted else None
        tap = doc.tapped(shown_entry) if link != "no link" else "-"
        selected, call = doc.pressed(shown_entry) if link != "no link" else ("-", "")
        lines += [
            f"## {doc.intention(item)}",
            "",
            f"- Stored: {doc.cell(value)}",
            f"- Linked: {link}",
            f"- Tap, the dialer holds: {tap}",
            f"- Dialled on the Android 9 emulator: {dials.get(title, '-')}",
            f"- Long-press selects: {selected}" + (f" (*Call* offered: {call})" if call else ""),
            "",
            "| Entry view | Tap | Long-press |",
            "|---|---|---|",
            "| " + " | ".join(
                f"![{label}: {doc.intention(item)}](tel-link-examples/{name}-{key}.png)" if made[label] else ""
                for label, key in (("view", "view"), ("tap", "tap"), ("long-press", "longpress"))) + " |",
            "",
        ]
        shown += sum(made.values())

    out = Path(wiki) / "Tel-Link-Examples-Evidence.md"
    out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"{out}: {len(source['entries'])} entries, {shown} pictures")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
