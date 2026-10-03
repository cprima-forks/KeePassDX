"""Harvest the screens of KeePassDX itself, to grow the object repository.

Navigation only. The taps come from repository/predicted-needs-keepassdx.json, a short list written
before looking. The harvest never taps a switch, a row inside a settings category, a Save or Validate
button, Add node, or anything that changes data. A tap target that is not found stops that screen:
nothing is guessed.

Initialize and End are the test run's (fixture_setup): the apps are closed, the fixture is opened and
unlocked, and at the end the apps are closed again and the settings that were changed are restored.

    uv run python harvest_keepassdx.py
"""

import json
import re
import sys
import time
from pathlib import Path

import device as dv
import fixture_setup as fs
import fixture_spec
from errors import ElementMissing

HERE = Path(__file__).parent
NEEDS = HERE / "repository" / "predicted-needs-keepassdx.json"
OUT = HERE / "repository" / "harvest"
DATABASE = HERE / "kp-test-tel.kdbx"
APP = "com.kunzisoft.keepass"


def tap_target(target: dict) -> None:
    """Tap the first node that has all the given attributes (id suffix, desc, text, all exact)."""
    root = dv.dump(windows=True)
    for node in root.iter("node"):
        if "id" in target and not node.get("resource-id", "").endswith(target["id"]):
            continue
        if "desc" in target and node.get("content-desc") != target["desc"]:
            continue
        if "text" in target and node.get("text") != target["text"]:
            continue
        if dv.bounds(node) == (0, 0, 0, 0):
            continue
        dv.tap(*dv.centre(dv.bounds(node)))
        return
    raise ElementMissing(f"harvest: no tap target {target} on the screen")


def matches(node: dict, hint: dict) -> bool:
    fields = {"id": node.get("id") or "", "text": node.get("text") or "", "desc": node.get("desc") or "", "class": node.get("class") or ""}
    return any(re.search(pattern, fields[key]) for key, pattern in hint.items())


def read_screen(screen: dict) -> dict:
    """The elements of the screen in front (the app's windows, popups included), and the predicted
    needs matched against them."""
    nodes = [n for n in dv.snapshot().get("nodes", []) if (n.get("package") or "").startswith(APP)]
    result = {"screen": screen["id"], "from": screen.get("from"), "focus": dv.focus(),
              "date": time.strftime("%Y-%m-%d"), "candidates": nodes, "matches": {}}
    for need in screen.get("needs", []):
        found = [n for n in nodes if matches(n, need["hint"])]
        result["matches"][need["name"]] = {"why": need["why"], "count": len(found), "found": found[:4]}
    shown = {id(n) for m in result["matches"].values() for n in m["found"]}
    result["unpredicted"] = [n for n in nodes if (n.get("id") or n.get("desc")) and id(n) not in shown][:60]
    return result


def harvest_screen(screen: dict) -> dict:
    dv.recover_to_list()  # every screen starts from the entry list
    if screen.get("open_entry"):
        dv.open_entry(screen["open_entry"])
    for target in screen.get("taps", []):
        tap_target(target)
        time.sleep(1.5)
    return read_screen(screen)


def harvest_settings_categories(main: dict, names: list[str]) -> list[dict]:
    """Open each named category row of the settings, read its list, go back. Nothing inside is tapped."""
    results = []
    for name in names:
        root = dv.dump(windows=True)
        row = next((n for n in root.iter("node") if re.match(f"(?i)^{name}", n.get("text", "") or "") and dv.bounds(n) != (0, 0, 0, 0)), None)
        if row is None:
            results.append({"screen": f"settings.{name.lower()}", "error": f"no row named {name!r} on the settings screen"})
            continue
        dv.tap(*dv.centre(dv.bounds(row)))
        time.sleep(1.5)
        results.append(read_screen({"id": f"settings.{name.lower().replace(' ', '_')}", "from": "the settings, the category row", "needs": []}))
        dv.press_back()
        time.sleep(1.0)
    return results


def report(results: list[dict]) -> str:
    lines = ["# Harvest of KeePassDX's own screens", "",
             "Written by `harvest_keepassdx.py`. Navigation only: nothing was changed. Predicted needs come from `predicted-needs-keepassdx.json`, written before looking.", ""]
    for r in results:
        lines += [f"## {r['screen']}", ""]
        if "error" in r:
            lines += [f"**Not harvested:** {r['error']}", ""]
            continue
        lines += [f"From: {r.get('from')}. {len(r['candidates'])} nodes of the app on the screen; in front: `{r['focus']}`.", ""]
        if r["matches"]:
            lines += ["| Predicted need | Found | Best candidate |", "|---|---|---|"]
            for name, m in r["matches"].items():
                best = m["found"][0] if m["found"] else None
                shown = f"`{(best['id'] or best['desc'] or best['text'] or '')[:60]}` ({best['class']})" if best else "-"
                lines.append(f"| {name}: {m['why']} | {'**yes**' if m['count'] else 'NO'} ({m['count']}) | {shown} |")
            lines.append("")
        lines += [f"With an id or description, not predicted: {len(r['unpredicted'])}.", ""]
        for n in r["unpredicted"][:25]:
            lines.append(f"- `{(n.get('id') or '').split('/')[-1]}` {n.get('desc') or ''} {n.get('text') or ''} ({n['class']})".rstrip())
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    predicted = json.loads(NEEDS.read_text(encoding="utf-8"))
    spec = fixture_spec.load_spec()
    env = fixture_spec.load_environment("cprima-dev")
    dv.configure(spec["dialogs"], env)
    detected = dv.detect_handlers()
    log = lambda **f: print("  ", f, flush=True)
    original = fs.read_app_preferences(env["target"])
    OUT.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    try:
        fs.initialize(spec, env, detected, DATABASE, log)
        wanted = set(sys.argv[1:])  # screen ids to harvest; none means all
        for screen in predicted["screens"]:
            if wanted and screen["id"] not in wanted:
                continue
            print(f"harvesting {screen['id']} ...", flush=True)
            try:
                with dv.dump_on_error(OUT / "_dumps", f"keepassdx-{screen['id']}-error"):
                    result = harvest_screen(screen)
                results.append(result)
                if screen.get("sub_screens"):
                    results += harvest_settings_categories(result, screen["sub_screens"])
            except Exception as problem:
                results.append({"screen": screen["id"], "error": f"{type(problem).__name__}: {problem}"})
                print(f"   not harvested: {problem}", flush=True)
        for r in results:
            (OUT / f"keepassdx-{r['screen']}.json").write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")
        (OUT / "REPORT-keepassdx.md").write_text(report(results), encoding="utf-8")
        found = sum(1 for r in results for m in r.get("matches", {}).values() if m["count"])
        total = sum(len(r.get("matches", {})) for r in results)
        print(f"{len(results)} screens harvested; {found} of {total} predicted needs found. report: {OUT / 'REPORT-keepassdx.md'}")
    finally:
        fs.finish(env, detected, log, original)
    return 0


if __name__ == "__main__":
    sys.exit(main())
