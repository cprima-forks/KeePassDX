"""Cut rows off the top of a PNG (the status bar of a screenshot) and write the result as a new file.

The source is never changed or overwritten. The rows are given in pixels; a value above a quarter of
the image height is refused unless --force is given, to catch a wrong number. The result carries no
metadata of its own (Pillow writes none unless asked), but this script does not promise that: run
strip_png_metadata.py on the result, or use publish_png.py, which does both and checks.

    uv run --with pillow python cprima-fork/tools/crop_png.py SOURCE.png TARGET.png --top 96
"""

import argparse
import sys
from pathlib import Path

from PIL import Image


def crop_top(source: Path, target: Path, top: int, force: bool = False) -> tuple[tuple[int, int], tuple[int, int]]:
    """Write `source` without its top `top` rows to `target`. Returns (size before, size after)."""
    if source.resolve() == target.resolve():
        raise ValueError("source and target are the same file: the source is never overwritten")
    if top <= 0:
        raise ValueError(f"--top must be positive, got {top}")
    with Image.open(source) as image:
        if image.format != "PNG":
            raise ValueError(f"{source}: not a PNG ({image.format})")
        width, height = image.size
        if top >= height:
            raise ValueError(f"{source}: --top {top} leaves nothing of an image {height} px high")
        if top > height // 4 and not force:
            raise ValueError(f"{source}: --top {top} is more than a quarter of the height ({height} px); use --force if that is meant")
        cropped = image.crop((0, top, width, height))
        target.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(target, format="PNG")
        return (width, height), cropped.size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--top", type=int, required=True, help="rows to cut off the top, in pixels")
    parser.add_argument("--force", action="store_true", help="allow more than a quarter of the height")
    args = parser.parse_args()
    try:
        before, after = crop_top(args.source, args.target, args.top, args.force)
    except (ValueError, OSError) as problem:
        print(f"error: {problem}")
        return 1
    print(f"{args.source} -> {args.target}")
    print(f"  cut {args.top} rows from the top: {before[0]}x{before[1]} -> {after[0]}x{after[1]}")
    print("  metadata is not stripped here: use strip_png_metadata.py or publish_png.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
