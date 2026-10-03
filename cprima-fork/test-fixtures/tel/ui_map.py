"""The UI structure of KeePassDX, extracted from its source (no phone needed).

Reads app/src/main: the manifest (activities), the Kotlin sources (which layout, menu and preference
screen each activity, fragment and dialog uses), res/menu (menu items) and res/xml/preferences_*
(settings keys). Writes repository/ui-map-keepassdx.json.

This is a static map: what the code refers to. How the screens lead to each other, what is built at
run time, and what a screen shows in a given state need a reading of the code or the device: the
harvest and the written analysis cover those.

    uv run python ui_map.py
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
MAIN = HERE.parent.parent / "app" / "src" / "main"
JAVA = MAIN / "java"
RES = MAIN / "res"
OUT = HERE / "repository" / "ui-map-keepassdx.json"
ANDROID = "{http://schemas.android.com/apk/res/android}"
IGNORE = ("Spike",)  # the fork-only spike is not part of the app's UI


def strings() -> dict[str, str]:
    root = ET.parse(RES / "values" / "strings.xml").getroot()
    return {s.get("name"): "".join(s.itertext()) for s in root.findall("string")}


def resolve(value: str | None, table: dict[str, str]) -> str:
    if not value:
        return ""
    m = re.fullmatch(r"@string/(\w+)", value)
    return table.get(m.group(1), value) if m else value


def snake(binding: str) -> str:
    """ActivityMainCredentialBinding -> activity_main_credential."""
    name = binding[: -len("Binding")] if binding.endswith("Binding") else binding
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def class_files() -> dict[str, Path]:
    found = {}
    for path in JAVA.rglob("*.kt"):
        if any(token in path.name for token in IGNORE):
            continue
        for m in re.finditer(r"^\s*(?:\w+\s+)*class\s+(\w+)", path.read_text(encoding="utf-8"), re.M):
            found.setdefault(m.group(1), path)
    return found


def uses(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    layouts = set(re.findall(r"R\.layout\.(\w+)", text))
    layouts |= {snake(b) for b in re.findall(r"\b(\w+Binding)\.inflate", text)}
    layouts |= {snake(b) for b in re.findall(r"\b(\w+Binding)\b\s*[:=]", text) if b != "ViewBinding"}
    fragments = re.findall(r"class\s+(\w+)\s*(?:\([^)]*\))?\s*:\s*[\w.<>, ()]*Fragment", text)
    dialogs = re.findall(r"class\s+(\w+)\s*(?:\([^)]*\))?\s*:\s*[\w.<>, ()]*Dialog\w*", text)
    return {
        "file": str(path.relative_to(MAIN.parent.parent.parent)).replace("\\", "/"),
        "layouts": sorted(l for l in layouts if (RES / "layout" / f"{l}.xml").exists()),
        "menus": sorted(set(re.findall(r"R\.menu\.(\w+)", text))),
        "preferences": sorted(set(re.findall(r"R\.xml\.(\w+)", text))),
        "fragments_defined_here": sorted(set(fragments)),
        "dialogs_defined_here": sorted(set(dialogs)),
        "activities_started": sorted(set(re.findall(r"(\w+Activity)::class\.java", text)) | set(re.findall(r"\b(\w+Activity)\.launch", text))),
    }


def menus(table: dict[str, str]) -> dict:
    result = {}
    for path in sorted((RES / "menu").glob("*.xml")):
        root = ET.parse(path).getroot()
        items = [{"id": (i.get(f"{ANDROID}id") or "").split("/")[-1], "title": resolve(i.get(f"{ANDROID}title"), table),
                  "show": i.get("{http://schemas.android.com/apk/res-auto}showAsAction") or i.get(f"{ANDROID}showAsAction") or ""}
                 for i in root.iter("item")]
        result[path.stem] = items
    return result


def preferences(table: dict[str, str]) -> dict:
    result = {}
    for path in sorted((RES / "xml").glob("preferences*.xml")):
        root = ET.parse(path).getroot()
        rows = []
        for element in root.iter():
            key = element.get(f"{ANDROID}key")
            if key is None and element.tag not in ("PreferenceCategory",):
                continue
            rows.append({"type": element.tag.split(".")[-1], "key": (key or "").split("/")[-1],
                         "title": resolve(element.get(f"{ANDROID}title"), table)})
        result[path.stem] = rows
    return result


def main() -> int:
    table = strings()
    manifest = ET.parse(MAIN / "AndroidManifest.xml").getroot()
    package = manifest.get("package", "com.kunzisoft.keepass")
    files = class_files()
    activities = {}
    for activity in manifest.iter("activity"):
        name = activity.get(f"{ANDROID}name", "").lstrip(".").split(".")[-1]
        filters = [f for f in activity.iter("intent-filter")]
        entry = {
            "exported": activity.get(f"{ANDROID}exported"),
            "launcher": any(c.get(f"{ANDROID}name") == "android.intent.category.LAUNCHER" for f in filters for c in f.iter("category")),
            "actions": sorted({a.get(f"{ANDROID}name", "").split(".")[-1] for f in filters for a in f.iter("action")}),
        }
        if name in files:
            entry.update(uses(files[name]))
        activities[name] = entry
    others = {}
    for name, path in sorted(files.items()):
        if name in activities or not (name.endswith("Fragment") or name.endswith("Dialog") or "Dialog" in name):
            continue
        others[name] = uses(path)
    data = {"source": "app/src/main (static; the fork-only Spike files are excluded)", "package": package,
            "activities": activities, "fragments_and_dialogs": others, "menus": menus(table), "preferences": preferences(table)}
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(activities)} activities, {len(others)} fragments and dialogs, {len(data['menus'])} menus, "
          f"{len(data['preferences'])} preference screens -> {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
