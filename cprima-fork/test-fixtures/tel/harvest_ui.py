"""Harvest the elements of the apps on the phone, to grow the object repository.

For each target in repository/predicted-needs.json: close the app, launch it with an intent that
cannot do harm (DIAL shows the dialpad without calling, SENDTO mailto: and sms: open a composer without
sending, VIEW https opens the browser), read the screen, close the app. It NEVER taps anything.

The screen is read with the snapshot of device.py (privacy filtered: an e-mail address or a phone
number in a text becomes a placeholder; no picture of another app is kept). The predicted needs are
then matched against what was found. Results go to repository/harvest/<system>-<screen>.json and a
report in repository/harvest/REPORT.md: what was found, what was not, and what was not predicted.

    uv run python harvest_ui.py                 # all targets
    uv run python harvest_ui.py dialer mailer   # some
"""

import json
import re
import sys
import time
from pathlib import Path

import device as dv
import fixture_spec

HERE = Path(__file__).parent
NEEDS = HERE / "repository" / "predicted-needs.json"
OUT = HERE / "repository" / "harvest"
ROLE_KEYS = {"dialer": ("dial", "dialer-role"), "browser": ("web", "browser-role"), "mailer": ("mail",), "sms": ("sms-role",)}


def matches(node: dict, hint: dict) -> bool:
    """Any one hint that matches counts: a regular expression over the id, text, description or class."""
    fields = {"id": node.get("id") or "", "text": node.get("text") or "", "desc": node.get("desc") or "", "class": node.get("class") or ""}
    return any(re.search(pattern, fields[key]) for key, pattern in hint.items())


def harvest_target(role: str, target: dict, detected: dict, env: dict) -> dict:
    package = next((detected[k] for k in ROLE_KEYS[role] if k in detected), None)
    if package is None:
        return {"role": role, "error": "no app detected for this role on the phone"}
    result = {"role": role, "screen": target["screen"], "package": package, "launched_with": target["launch"],
              "device": env["device"]["description"], "date": time.strftime("%Y-%m-%d")}
    scratch = OUT / "_dumps"
    try:
        with dv.dump_on_error(scratch, f"{role}-error"):
            dv.adb("shell", "am", "force-stop", package)
            time.sleep(1.0)
            dv.adb("shell", "am", "start", *[f"'{a}'" if ("?" in a or ":" in a) and not a.startswith("-") else a for a in target["launch"]])
            dv.soft_wait(lambda: package in dv.focus(), timeout=15)
            time.sleep(3.0)  # a first start may need a moment
            result["focus"] = dv.focus()
            modal = dv.detect_modal()
            if modal is not None:
                result["modal"] = {"kind": modal.kind, "window": modal.window, "title": modal.title,
                                   "message": modal.message, "buttons": list(modal.buttons), "texts": modal.texts[:8]}
            nodes = [n for n in dv.snapshot().get("nodes", []) if n.get("package") == package]
            result["candidates"] = nodes
            result["matches"] = {}
            for need in target["needs"]:
                found = [n for n in nodes if matches(n, need["hint"])]
                result["matches"][need["name"]] = {"why": need["why"], "found": found[:4], "count": len(found)}
            predicted = {id(n) for m in result["matches"].values() for n in m["found"]}
            result["unpredicted"] = [n for n in nodes if (n.get("id") or n.get("desc")) and id(n) not in predicted][:40]
    except Exception as problem:
        result["error"] = f"{type(problem).__name__}: {problem}"
        result["evidence"] = getattr(problem, "ui_evidence", [])
    finally:
        dv.adb("shell", "am", "force-stop", package)  # leave nothing open
    return result


def report(results: list[dict]) -> str:
    lines = ["# Harvest of the phone's apps", "",
             "Written by `harvest_ui.py`: each app was launched by an intent that cannot do harm, read, and closed. Nothing was tapped.",
             "Predicted needs come from `predicted-needs.json`, written before the apps were opened.", ""]
    for r in results:
        lines += [f"## {r['role']} ({r.get('package', '?')})", ""]
        if "error" in r:
            lines += [f"**Not harvested:** {r['error']}", ""]
            if r.get("evidence"):
                lines += [f"The UI was dumped: {r['evidence']}", ""]
            continue
        lines += [f"Launched with `{' '.join(r['launched_with'])}`; in front: `{r.get('focus')}`; {len(r['candidates'])} nodes of the app on the screen.", ""]
        if "modal" in r:
            lines += [f"**A modal was showing:** {r['modal']}", ""]
        lines += ["| Predicted need | Found | Best candidate |", "|---|---|---|"]
        for name, m in r["matches"].items():
            best = m["found"][0] if m["found"] else None
            shown = f"`{best['id'] or best['desc'] or best['text']}` ({best['class']})" if best else "-"
            lines.append(f"| {name}: {m['why']} | {'**yes**' if m['count'] else 'NO'} ({m['count']}) | {shown} |")
        lines += ["", f"Not predicted, but present with an id or description: {len(r['unpredicted'])}.", ""]
        for n in r["unpredicted"][:12]:
            lines.append(f"- `{n.get('id') or ''}` {n.get('desc') or ''} {n.get('text') or ''} ({n['class']})".rstrip())
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    wanted = set(sys.argv[1:])
    predicted = json.loads(NEEDS.read_text(encoding="utf-8"))
    env = fixture_spec.load_environment("cprima-dev")
    dv.configure(fixture_spec.load_spec()["dialogs"], env)
    detected = dv.detect_handlers()
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for role, target in predicted["targets"].items():
        if wanted and role not in wanted:
            continue
        print(f"harvesting {role} ...", flush=True)
        result = harvest_target(role, target, detected, env)
        (OUT / f"{role}-{target['screen']}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
        found = sum(1 for m in result.get("matches", {}).values() if m["count"])
        print(f"   {result.get('package', '?')}: " + (result["error"] if "error" in result else
              f"{len(result['candidates'])} nodes, {found} of {len(result['matches'])} predicted needs found"), flush=True)
        results.append(result)
    (OUT / "REPORT.md").write_text(report(results), encoding="utf-8")
    print(f"report: {OUT / 'REPORT.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
