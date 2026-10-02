"""Remove metadata chunks from a PNG and keep the pixels unchanged.

Removes eXIf, tEXt, zTXt, iTXt and tIME. Every other chunk is copied byte for byte.
The pixel data (all IDAT chunks) is hashed before and after; the script refuses to write
if the hashes differ. Running it again on its own output changes nothing.

    uv run python fork-tools/strip_png_metadata.py SOURCE.png TARGET.png
"""

import hashlib
import struct
import sys

SIGNATURE = b"\x89PNG\r\n\x1a\n"
STRIP = {b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"}


def chunks(data: bytes):
    """Yield (type, raw bytes of the whole chunk including length and CRC)."""
    pos = len(SIGNATURE)
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        end = pos + 12 + length
        yield data[pos + 4 : pos + 8], data[pos:end]
        pos = end


def pixel_hash(data: bytes) -> str:
    digest = hashlib.sha256()
    for kind, raw in chunks(data):
        if kind == b"IDAT":
            digest.update(raw[8:-4])
    return digest.hexdigest()


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    source, target = sys.argv[1], sys.argv[2]
    data = open(source, "rb").read()
    if not data.startswith(SIGNATURE):
        print(f"{source}: not a PNG")
        return 1

    removed = [(kind.decode(), len(raw)) for kind, raw in chunks(data) if kind in STRIP]
    stripped = SIGNATURE + b"".join(raw for kind, raw in chunks(data) if kind not in STRIP)

    before, after = pixel_hash(data), pixel_hash(stripped)
    if before != after:
        print("pixel data changed, nothing written")
        return 1

    open(target, "wb").write(stripped)
    print(f"{source} -> {target}")
    print(f"  removed: {removed if removed else 'nothing'}")
    print(f"  size: {len(data)} -> {len(stripped)} bytes")
    print(f"  pixel hash (IDAT): {before[:16]} (unchanged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
