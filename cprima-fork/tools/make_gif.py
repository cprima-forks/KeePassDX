"""Animated GIF of the pictures of one run or of one folder of screenshots.

Usage:
    uv run --with pillow python cprima-fork/tools/make_gif.py RUN_OR_FOLDER OUT.gif [WIDTH=360] [MS_PER_FRAME=700]

RUN_OR_FOLDER is either
  - a run folder of the device run (cprima-fork/test-fixtures/tel/runs/<run>/): the pictures in its
    `published/` folder, in the order they were taken (by the time of the uncropped original), or
  - any folder of PNG files without a `published/` folder (the screenshots of LinkLab, for example): all
    PNG files in it, sorted by file name.

Every frame is scaled to WIDTH pixels, put on a white canvas of the height of the tallest frame and reduced
to 128 colours, which keeps a run of about 140 pictures at a few megabytes. The GIF loops.
"""

import sys
from pathlib import Path

from PIL import Image


def pictures(source: Path) -> list[Path]:
    """The pictures to show, in the order to show them."""
    published = source / "published"
    if not published.is_dir():
        return sorted(source.glob("*.png"))
    found = []
    for path in published.rglob("*.png"):
        original = source / path.relative_to(published)  # the uncropped original holds the time it was taken
        found.append(((original if original.exists() else path).stat().st_mtime, path))
    return [path for _, path in sorted(found)]


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    source = Path(sys.argv[1])
    out = Path(sys.argv[2])
    width = int(sys.argv[3]) if len(sys.argv) > 3 else 360
    ms = int(sys.argv[4]) if len(sys.argv) > 4 else 700

    paths = pictures(source)
    if not paths:
        print(f"no PNG files found for {source}", file=sys.stderr)
        return 1

    frames = []
    for path in paths:
        image = Image.open(path).convert("RGB")
        height = round(image.height * width / image.width)
        frames.append(image.resize((width, height), Image.LANCZOS))
    height = max(frame.height for frame in frames)

    canvas = []
    for frame in frames:
        page = Image.new("RGB", (width, height), (255, 255, 255))
        page.paste(frame, (0, 0))
        canvas.append(page.quantize(colors=128, method=Image.MEDIANCUT, dither=Image.NONE))
    canvas[0].save(out, save_all=True, append_images=canvas[1:], duration=ms, loop=0, optimize=True)
    print(len(canvas), "frames,", width, "x", height, ",", round(out.stat().st_size / 1e6, 1), "MB ->", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
