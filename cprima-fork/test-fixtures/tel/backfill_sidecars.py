"""Write sidecars (`<name>.png.json`) for the screenshots of a finished run that have none.

New runs write a sidecar for every screenshot at capture time (device.Shot.write). The runs before
that have pictures only. This script reconstructs what it can and says how it knows, field by field:

  status bar   1. "inferred-from-dump": a windows dump saved in the same run shows a status bar that
                  spans the picture's full width. (The display height is not used: a dump has no
                  nodes for the navigation bar, so it cannot tell it.)
               2. "inferred-from-sidecar": another run measured the status bar on a picture of the
                  same size from the same phone model (--reference lets you name the runs to read).
               3. otherwise null with the reason. Nothing is guessed: publish_png.py then asks for
                  --top N, which a person gives after `preview`.
  taken        the modification time of the file, marked taken_source "mtime" (it is not a capture time)
  step, device, context   from the folder name, the file name and the run's report.json

A sidecar that exists is never overwritten. The sidecars say `backfilled: true`.

    uv run python backfill_sidecars.py runs/<run>            # writes
    uv run python backfill_sidecars.py runs/<run> --dry      # only says what it would write
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

import shot_meta

HERE = Path(__file__).parent
RUNS = HERE / "runs"


def load_report(run: Path) -> dict:
    path = run / "report.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"meta": {}, "entries": {}}


def scenario_of(report: dict, relative: str) -> str:
    """The scenario whose result lists this picture, or "" (the view screenshot belongs to none)."""
    for result in report.get("entries", {}).values():
        for scenario in result.get("scenarios", []):
            if relative in scenario.get("shots", []) or relative in scenario.get("evidence", []):
                return scenario["scenario"]
    return ""


def dump_measurements(run: Path) -> list[dict]:
    """Status bars found in the windows dumps of the run: {rect, extent, source}."""
    found = []
    for path in sorted(run.rglob("*-windows.xml")):
        try:
            root = shot_meta.parse_dump(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        bar = shot_meta.status_bar(root)
        if bar:
            found.append({"rect": bar["rect"], "node": bar["node"], "source": path.relative_to(run).as_posix()})
    return found


def sidecar_measurements(runs: list[Path], model: str) -> list[dict]:
    """Status bars measured at capture time by other runs, for the same phone model."""
    found = []
    for run in runs:
        report_model = load_report(run)["meta"].get("device")
        if report_model and report_model != model:
            continue
        for path in run.rglob("*.png.json"):
            facts = json.loads(path.read_text(encoding="utf-8"))
            bar = facts.get("status_bar")
            if bar and bar.get("measured") in ("phonectl-windows", "windows-dump"):
                found.append({"rect": bar["rect"], "node": bar["node"], "size": (facts["image"]["width"], facts["image"]["height"]),
                              "source": f"{run.name}/{path.relative_to(run).as_posix()}"})
                break  # one per run is enough to name the source
    return found


def infer_bar(size: tuple[int, int], dumps: list[dict], others: list[dict]) -> tuple[dict | None, str]:
    # A dump does not tell the display's height (the navigation bar has no nodes in it), so the match
    # is the width: a status bar that spans the picture's full width, from the same run.
    for found in dumps:
        if found["rect"][0] == 0 and found["rect"][2] == size[0]:
            return {"rect": found["rect"], "node": found["node"], "measured": "inferred-from-dump", "inferred_from": found["source"]}, ""
    for found in others:
        if tuple(found["size"]) == size:
            return {"rect": found["rect"], "node": found["node"], "measured": "inferred-from-sidecar", "inferred_from": found["source"]}, ""
    return None, f"not measured: no windows dump of the run and no sidecar of another run for a {size[0]}x{size[1]} picture"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("run", type=Path)
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--reference", type=Path, nargs="*", default=None, help="runs whose sidecars may be used (default: all runs)")
    args = parser.parse_args()

    run = args.run.resolve()
    report = load_report(run)
    meta = report["meta"]
    model = meta.get("device", "")
    references = [r for r in (args.reference or sorted(p for p in RUNS.iterdir() if p.is_dir())) if r.resolve() != run]
    dumps = dump_measurements(run)
    others = sidecar_measurements(references, model)
    print(f"{run.name}: {len(dumps)} usable windows dump(s) in the run, {len(others)} measured sidecar(s) in other runs")

    written = skipped = unmeasured = 0
    for png in sorted(run.rglob("*.png")):
        if shot_meta.sidecar_path(png).exists():
            skipped += 1
            continue
        data = png.read_bytes()
        with Image.open(png) as image:
            size = image.size
        bar, error = infer_bar(size, dumps, others)
        relative = png.relative_to(run).as_posix()
        # A schema 2 sidecar with what history still tells; there is no raw file for these pictures
        # (the phone was not asked at the time), and `backfilled` says so.
        facts = {
            "schema": shot_meta.SCHEMA,
            "file": png.name,
            "taken": datetime.fromtimestamp(png.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
            "taken_source": "mtime",
            "clock": None,
            "capture_ms": None,
            "png_sha256": hashlib.sha256(data).hexdigest(),
            "image": {"width": size[0], "height": size[1]},
            "display": {"size": None, "density": None, "rotation": None},
            "status_bar": None,
            "focus": "?",
            "device": {"model": model, "android": meta.get("android", "")},
            "environment": {"profile": meta.get("environment", ""), "target_app": {"version_name": meta.get("app_version", "")},
                            "detected": meta.get("detected_apps", {})},
            "code": {"fixture_sha256": meta.get("fixture_sha256", "")},
            "context": {"run": run.name, "environment": meta.get("environment", "")},
            "step": {"entry": png.parent.name if png.parent != run else "", "scenario": scenario_of(report, relative), "label": png.stem},
            "raw": None,
            "backfilled": True,
            "backfilled_at": shot_meta.now_iso(),
        }
        if bar:
            facts["status_bar"] = {**bar, "height_px": bar["rect"][3] - bar["rect"][1], "dumped_at": None}
        else:
            facts["status_bar_error"] = error
            unmeasured += 1
        print(f"  {relative}: {'status bar ' + str(facts['status_bar']['rect']) + ' ' + facts['status_bar']['measured'] if bar else error}")
        if not args.dry:
            shot_meta.write(png, facts)
        written += 1
    print(f"{'would write' if args.dry else 'wrote'} {written} sidecar(s), {unmeasured} without a measured status bar; {skipped} already had one")
    return 0


if __name__ == "__main__":
    sys.exit(main())
