"""Where the words of a screenshot are: OCR word boxes, and the position of a link in them.

The accessibility dump gives one box per line of text, not the position of a link inside it, so the
position comes from the picture. Uses the Windows OCR engine through `ocr_words.ps1`
(Windows PowerShell 5.1).
"""

import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

SCRIPT = Path(__file__).parent / "ocr_words.ps1"


def ocr_words(png: Path, scale: int = 1) -> list[dict]:
    """Words with boxes {text, x, y, w, h}. With scale > 1 the picture is enlarged first (small text
    is read better) and the boxes are scaled back."""
    source = png
    scratch = None
    if scale > 1:
        # the enlarged copy is a work file, not a screenshot: it lives in a temp folder, never next to
        # the run's pictures (every picture there has a sidecar, see shot_meta.verify_run)
        scratch = tempfile.TemporaryDirectory()
        image = Image.open(png)
        source = Path(scratch.name) / f"{png.stem}-x{scale}.png"
        image.resize((image.width * scale, image.height * scale), Image.LANCZOS).save(source)
    try:
        raw = subprocess.run(
            ["powershell.exe", "-NoProfile", "-File", str(SCRIPT), "-File", str(source)],
            capture_output=True,
        ).stdout
    finally:
        if scratch is not None:
            scratch.cleanup()
    words = json.loads(raw.decode("utf8") or "[]")
    for word in words:
        for key in ("x", "y", "w", "h"):
            word[key] //= scale
    return words


def inside(word: dict, region: tuple[int, int, int, int]) -> bool:
    cx, cy = word["x"] + word["w"] // 2, word["y"] + word["h"] // 2
    return region[0] <= cx <= region[2] and region[1] <= cy <= region[3]


def anchors_of(words: list[dict]) -> list[dict]:
    """The words that end in `tel:`, in reading order."""
    found = [w for w in words if w["text"].lower().endswith("tel:")]
    return sorted(found, key=lambda w: (w["y"], w["x"]))


def right_of(anchor: dict, words: list[dict]) -> dict | None:
    """The word directly to the right of `anchor` on the same line."""
    best = None
    for w in words:
        gap = w["x"] - (anchor["x"] + anchor["w"])
        if w is not anchor and abs(w["y"] - anchor["y"]) < 20 and -5 <= gap <= 45:
            if best is None or w["x"] < best["x"]:
                best = w
    return best


def wrapped_after(anchor: dict, word: dict, words: list[dict]) -> bool:
    """Whether `word` starts the next line and `anchor` ends its line: the number wrapped away from `tel:`."""
    if right_of(anchor, words) is not None:
        return False
    below = word["y"] - anchor["y"]
    return 0 < below <= 2.2 * anchor["h"] and word["x"] <= anchor["x"]


def locate_numbers(words: list[dict], numbers: list[str]) -> list[tuple[dict | None, str]]:
    """Box of each number, in order, and how it was found.

    1. a word that starts the number and has a `tel:` word directly to its left ("ocr");
    2. else the position just right of the i-th `tel:` word ("tel-anchor"), when there are as many
       `tel:` words as numbers;
    3. else None.
    """
    anchors = anchors_of(words)
    found: list[tuple[dict | None, str]] = []
    used: set[int] = set()
    for number in numbers:
        best = None
        for anchor in anchors:
            for i, w in enumerate(words):
                if i in used or not (number.startswith(w["text"]) or w["text"].startswith(number[:3])):
                    continue
                gap = w["x"] - (anchor["x"] + anchor["w"])
                if abs(w["y"] - anchor["y"]) < 20 and -5 <= gap <= 45:
                    if best is None or (w["y"], w["x"]) < (best[1]["y"], best[1]["x"]):
                        best = (i, w)
                elif wrapped_after(anchor, w, words):
                    if best is None or (w["y"], w["x"]) < (best[1]["y"], best[1]["x"]):
                        best = (i, w)
        if best:
            used.add(best[0])
            found.append((best[1], "ocr"))
        else:
            found.append((None, ""))
    if any(box is None for box, _ in found) and len(anchors) == len(numbers):
        for i, (box, _) in enumerate(found):
            if box is None:
                a = anchors[i]
                width = int(len(numbers[i]) * a["h"] * 0.8)  # a glyph of this font is about 0.8 of the box height wide
                found[i] = ({"text": "", "x": a["x"] + a["w"], "y": a["y"], "w": width, "h": a["h"]}, "tel-anchor")
    return found


def box_of(word: dict) -> tuple[int, int, int, int]:
    return word["x"], word["y"], word["x"] + word["w"], word["y"] + word["h"]


def box_after(words: list[dict], prefix: str) -> dict | None:
    """The box of what follows a prefix word on its line (for "mailto:" the address). Used when OCR
    misreads the text itself (it read "a@example.com" as "aaexample . com"), but reads the prefix:
    the position comes from the prefix and the known text, not from the characters."""
    wanted = prefix.rstrip(":").lower()
    for anchor in sorted(words, key=lambda w: (w["y"], w["x"])):
        if anchor["text"].rstrip(":").lower() != wanted:
            continue
        rest = [w for w in words if w is not anchor and abs(w["y"] - anchor["y"]) <= 25
                and w["x"] >= anchor["x"] + anchor["w"] - 5 and w["text"] != ":"]
        if rest:
            x1 = min(w["x"] for w in rest)
            y1 = min(w["y"] for w in rest)
            x2 = max(w["x"] + w["w"] for w in rest)
            y2 = max(w["y"] + w["h"] for w in rest)
            return {"text": "", "x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1}
    return None


def word_for_text(words: list[dict], text: str) -> dict | None:
    """The box of `text` (a web or e-mail address). OCR splits an address at punctuation, so
    neighbouring words on one line are joined until they spell the text; a word that ends with
    the text (the address after a prefix) is taken as it is."""
    for first in sorted(words, key=lambda w: (w["y"], w["x"])):
        if not text.startswith(first["text"]):
            continue
        joined, last, box = first["text"], first, dict(first)
        while joined != text:
            # the next piece: the word to the right on the same line that continues the text
            following = [
                w for w in words
                if w is not last and abs(w["y"] - last["y"]) <= 25
                and -5 <= w["x"] - (last["x"] + last["w"]) <= 45
                and text.startswith(joined + w["text"])
            ]
            if not following:
                break
            piece = min(following, key=lambda w: w["x"])
            joined += piece["text"]
            last = piece
            box["w"] = piece["x"] + piece["w"] - box["x"]
            box["h"] = max(box["h"], piece["h"])
        if joined == text or (len(joined) >= 6 and len(joined) >= len(text) // 2):
            box["text"] = joined
            return box
    for w in words:
        if w["text"].endswith(text):
            return w
    return None
