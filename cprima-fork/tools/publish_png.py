"""Prepare screenshots for publication: cut off the status bar, remove the metadata, verify.

For each image: crop the top rows (crop_png.py), remove eXIf, tEXt, zTXt, iTXt and tIME
(strip_png_metadata.py), then read the written file again and check that none of those chunks is
left and that the pixel data is the one that was cropped. The source is never changed.

The number of rows to cut comes from the sidecar `<name>.png.json` that the run wrote when it took the
screenshot: the status bar was measured on the phone, per shot. Without a sidecar the number must be
given with --top, and the manifest then says "given": a person looked at it. There is no guessing
here. `preview` shows where the cut would fall.

The capture time is the sidecar's `taken`. Without a sidecar it is the modification time of the file
on this machine, and the manifest says "mtime".

    one image:
    uv run --with pillow python cprima-fork/tools/publish_png.py one SOURCE.png TARGET.png

    a folder, with a provenance file (one JSON object per line):
    uv run --with pillow python cprima-fork/tools/publish_png.py dir SOURCE_DIR TARGET_DIR --manifest provenance.jsonl

    look before cutting (draws the cut line on the top of the picture):
    uv run --with pillow python cprima-fork/tools/publish_png.py preview SOURCE.png PREVIEW.png [--top 96]

Sidecar format: see cprima-fork/test-fixtures/tel/shot_meta.py.
"""

import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import strip_png_metadata as strip
from crop_png import crop_top
from PIL import Image, ImageDraw

MEASURED_OK = ("phonectl-windows", "windows-dump", "inferred-from-dump", "inferred-from-sidecar", "given")


def sidecar_of(source: Path) -> dict | None:
    path = source.with_name(source.name + ".json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def sidecar_top(facts: dict) -> int | None:
    """The rows to cut as the sidecar says: the bottom of the measured status bar, which must sit at
    the top edge and span the picture. None when it was not measured."""
    bar = facts.get("status_bar")
    if not bar or bar.get("measured") not in MEASURED_OK:
        return None
    left, top, right, bottom = bar["rect"]
    if top != 0 or left != 0 or right != facts["image"]["width"]:
        return None
    return bottom


def decide_top(source: Path, facts: dict | None, given: int | None) -> tuple[int, str]:
    """(rows, where the number comes from). The sidecar wins; a given number that disagrees with a
    measured one is refused, so that a wrong guess cannot hide a measurement."""
    measured = sidecar_top(facts) if facts else None
    if measured is not None:
        if given is not None and given != measured:
            raise ValueError(f"{source}: --top {given} disagrees with the measured status bar ({measured} px)")
        return measured, f"sidecar:{facts['status_bar']['measured']}"
    if given is not None:
        why = "the sidecar has no measured status bar" if facts else "no sidecar"
        return given, f"given ({why})"
    reason = facts.get("status_bar_error", "no status bar") if facts else "no sidecar"
    raise ValueError(f"{source}: the status bar height is not known ({reason}); give --top N after `preview`, or backfill the sidecar")


def publish(source: Path, target: Path, given_top: int | None = None, force: bool = False) -> dict:
    """Crop, strip and verify one image. Returns the facts for the provenance table."""
    source_data = source.read_bytes()
    if not source_data.startswith(strip.SIGNATURE):
        raise ValueError(f"{source}: not a PNG")
    facts = sidecar_of(source)
    top, top_source = decide_top(source, facts, given_top)
    had = sorted({kind.decode() for kind, _ in strip.chunks(source_data) if kind in strip.STRIP})

    with tempfile.TemporaryDirectory() as tmp:
        cropped_file = Path(tmp) / "cropped.png"
        before, after = crop_top(source, cropped_file, top, force)
        cropped = cropped_file.read_bytes()

    stripped = strip.SIGNATURE + b"".join(raw for kind, raw in strip.chunks(cropped) if kind not in strip.STRIP)
    cropped_hash = strip.pixel_hash(cropped)
    if strip.pixel_hash(stripped) != cropped_hash:
        raise ValueError(f"{source}: the pixel data changed while stripping, nothing written")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(stripped)

    # verify what was written, not what was meant to be written
    written = target.read_bytes()
    left = [kind.decode() for kind, _ in strip.chunks(written) if kind in strip.STRIP]
    if left:
        target.unlink()
        raise ValueError(f"{target}: metadata chunks left after stripping: {left}; file removed")
    if strip.pixel_hash(written) != cropped_hash:
        target.unlink()
        raise ValueError(f"{target}: the written pixel data differs from the cropped one; file removed")

    if facts and facts.get("taken"):
        taken, taken_source = facts["taken"], facts.get("taken_source", "capture")
    else:
        taken, taken_source = datetime.fromtimestamp(source.stat().st_mtime).isoformat(timespec="seconds"), "mtime"
    record = {
        "source": str(source),
        "published": target.name,
        "taken": taken,
        "taken_source": taken_source,
        "pixel_hash16": cropped_hash[:16],
        "size_before": list(before),
        "size_after": list(after),
        "top": top,
        "top_source": top_source,
        "source_had_chunks": had,
    }
    if facts:
        record.update(public_facts(facts))
    return record


# What may go into a publication manifest. The sidecar holds more (the firmware build id and
# fingerprint, paths on the phone, the whole package list); those stay local.
PUBLIC_DEVICE = ("manufacturer", "brand", "model", "android", "sdk", "security_patch", "abi", "locale",
                 "font_scale", "navigation_mode", "night_mode")
PUBLIC_APP = ("package", "version_name", "version_code", "apk_sha256")


def public_facts(facts: dict) -> dict:
    """The part of a sidecar that is published: a whitelist, never the private fields."""
    device = facts.get("device") or {}
    environment = facts.get("environment") or {}
    code = facts.get("code") or {}
    public: dict = {
        "step": facts.get("step", {}),
        "device": {key: device[key] for key in PUBLIC_DEVICE if key in device},
        "environment": {
            "profile": environment.get("profile"),
            "roles": {role: {key: app.get(key) for key in PUBLIC_APP} for role, app in (environment.get("roles") or {}).items()},
            "target_app": {key: (environment.get("target_app") or {}).get(key) for key in PUBLIC_APP},
            "test_app": {key: environment["test_app"].get(key) for key in PUBLIC_APP} if environment.get("test_app") else None,
            "app_preferences": environment.get("app_preferences"),
        },
        "code": {key: code.get(key) for key in ("git_head", "git_branch", "git_dirty_files", "fixture_sha256", "spec_sha256", "cases_sha256")},
        "run": (facts.get("context") or {}).get("run"),
    }
    for key in ("clipboard", "selection"):
        if key in facts:
            public[key] = facts[key]
    return public


def publish_run(run: Path, exclude_names: tuple[str, ...] = ("error-*",), exclude_dirs: tuple[str, ...] = ("published",)) -> dict:
    """Crop, strip and verify every screenshot of a finished run into `<run>/published/`, same folder
    layout, and write `published/provenance.jsonl` (one JSON object per picture). Folders whose name
    starts with `_` (calibration, start and abort evidence) and error evidence are not published. A
    picture that cannot be published (no measured status bar, no --top) is listed in `errors`, and the
    others are still done: the caller decides what an error means. Returns {count, errors, manifest}."""
    target_root = run / "published"
    records, errors = [], []
    for source in sorted(run.rglob("*.png")):
        relative = source.relative_to(run)
        first = relative.parts[0]
        if first in exclude_dirs or first.startswith("_") or any(source.match(p) for p in exclude_names):
            continue
        try:
            records.append(publish(source, target_root / relative))
        except (ValueError, OSError) as problem:
            errors.append({"file": relative.as_posix(), "error": str(problem)})
    target_root.mkdir(parents=True, exist_ok=True)
    manifest = target_root / "provenance.jsonl"
    manifest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    return {"count": len(records), "errors": errors, "manifest": str(manifest)}


def preview(source: Path, out: Path, given_top: int | None) -> int:
    """The top of the picture, three times the cut height, with a red line where the cut would fall."""
    facts = sidecar_of(source)
    top, top_source = decide_top(source, facts, given_top)
    with Image.open(source) as image:
        part = image.convert("RGB").crop((0, 0, image.width, min(image.height, top * 3)))
    draw = ImageDraw.Draw(part)
    draw.line([(0, top), (part.width, top)], fill=(255, 0, 0), width=2)
    out.parent.mkdir(parents=True, exist_ok=True)
    part.save(out, format="PNG")
    print(f"{out}: the red line is at row {top} ({top_source}); everything above it is cut")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    for name in ("one", "dir", "preview"):
        p = sub.add_parser(name)
        p.add_argument("source", type=Path)
        p.add_argument("target", type=Path)
        p.add_argument("--top", type=int, help="rows to cut off the top; needed only without a measured sidecar")
        if name != "preview":
            p.add_argument("--force", action="store_true", help="allow more than a quarter of the height")
        if name == "dir":
            p.add_argument("--manifest", type=Path, help="write one JSON object per image here")
            p.add_argument("--exclude", action="append", default=[], help="glob of file names to skip, e.g. 'error-*'")
    args = parser.parse_args()

    try:
        if args.mode == "preview":
            return preview(args.source, args.target, args.top)
        if args.mode == "one":
            jobs = [(args.source, args.target)]
        else:
            jobs = [
                (path, args.target / path.relative_to(args.source))
                for path in sorted(args.source.rglob("*.png"))
                if not any(path.match(pattern) for pattern in args.exclude)
            ]
        records = []
        for source, target in jobs:
            record = publish(source, target, args.top, args.force)
            records.append(record)
            print(f"{record['source']} -> {target}")
            print(f"  {record['size_before'][0]}x{record['size_before'][1]} -> {record['size_after'][0]}x{record['size_after'][1]}"
                  f" (top {record['top']} rows cut, {record['top_source']}); taken {record['taken']} ({record['taken_source']});"
                  f" pixel hash {record['pixel_hash16']}; source had: {record['source_had_chunks'] or 'no metadata chunks'}")
        if args.mode == "dir" and args.manifest:
            args.manifest.parent.mkdir(parents=True, exist_ok=True)
            args.manifest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
            print(f"{len(records)} images; provenance written to {args.manifest}")
    except (ValueError, OSError) as problem:
        print(f"error: {problem}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
