"""Inventory of the UI elements of KeePassDX, read from the app's own source (no phone needed).

Scans app/src/main/res/layout/*.xml and res/menu/*.xml for every view with an id, with its type, its
text and its content description (strings are resolved from values/strings.xml), and the file it is
defined in. The result is repository/inventory-keepassdx.json: the interaction surface of the app, and the
reference that the object repository (repository/keepassdx.json) is checked against.

    uv run python inventory_ui.py              # write the inventory
    uv run python inventory_ui.py --check      # check the repository's ids against the inventory
"""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
REPO_ROOT = HERE.parent.parent
RES = REPO_ROOT / "app" / "src" / "main" / "res"
INVENTORY = HERE / "repository" / "inventory-keepassdx.json"
REPOSITORY = HERE / "repository" / "keepassdx.json"
ANDROID = "{http://schemas.android.com/apk/res/android}"


def strings() -> dict[str, str]:
    root = ET.parse(RES / "values" / "strings.xml").getroot()
    return {s.get("name"): "".join(s.itertext()) for s in root.findall("string")}


def resolve(value: str | None, table: dict[str, str]) -> str:
    if not value:
        return ""
    match = re.fullmatch(r"@string/(\w+)", value)
    return table.get(match.group(1), value) if match else value


def scan(folder: str, table: dict[str, str]) -> list[dict]:
    found = []
    for path in sorted((RES / folder).glob("*.xml")):
        try:
            tree = ET.parse(path)
        except ET.ParseError:
            continue
        for element in tree.getroot().iter():
            raw = element.get(f"{ANDROID}id")
            if not raw:
                continue
            found.append({
                "id": raw.split("/")[-1],
                "view": element.tag.split(".")[-1],
                "file": f"{folder}/{path.name}",
                "text": resolve(element.get(f"{ANDROID}text") or element.get(f"{ANDROID}title"), table),
                "desc": resolve(element.get(f"{ANDROID}contentDescription"), table),
            })
    return found


def build() -> dict:
    table = strings()
    elements = scan("layout", table) + scan("menu", table)
    by_id: dict[str, list[dict]] = {}
    for e in elements:
        by_id.setdefault(e["id"], []).append(e)
    return {"source": "app/src/main/res", "count": len(elements), "ids": by_id}


def walk(elements: dict, prefix: str):
    """Every element with its full name, children included."""
    for name, locator in elements.items():
        yield f"{prefix}.{name}", locator
        yield from walk(locator.get("children", {}), f"{prefix}.{name}")


def repository_ids() -> list[tuple[str, str, str]]:
    """(system, name, id) for every locator with an id in a system of kind `app`."""
    rows = []
    for path in sorted(REPOSITORY.parent.glob("*.json")):
        if path.name.startswith("inventory-"):
            continue
        system = json.loads(path.read_text(encoding="utf-8"))
        if system.get("kind") != "app":
            continue  # the platform and the phone's apps are not in the app source
        for screen, content in system["screens"].items():
            for name, locator in walk(content["elements"], f"{system['system']}.{screen}"):
                if "id" in locator and locator.get("from") != "library":
                    rows.append((system["system"], name, locator["id"]))
    return rows


def check(inventory: dict) -> int:
    problems, rows = 0, repository_ids()
    for system, name, ident in rows:
        if not inventory["ids"].get(ident):
            print(f"MISSING  {name}: id {ident!r} is not defined in the app source")
            problems += 1
    print(f"{len(rows)} ids of the app systems checked against {inventory['count']} views in the source: "
          f"{problems} missing")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    inventory = build()
    INVENTORY.parent.mkdir(exist_ok=True)
    INVENTORY.write_text(json.dumps(inventory, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"inventory: {inventory['count']} views with an id, {len(inventory['ids'])} distinct ids -> {INVENTORY.name}")
    return check(inventory) if args.check else 0


if __name__ == "__main__":
    sys.exit(main())
