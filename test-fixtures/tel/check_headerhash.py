"""Compare Meta/HeaderHash stored in a KDBX 3.x file with the real header hash."""

import base64
import hashlib
import struct
import sys

from pykeepass import PyKeePass

PASSWORD = "test123"


def header_bytes(path: str) -> bytes:
    data = open(path, "rb").read()
    pos = 12  # signature 4+4, version 2+2
    while True:
        field_id = data[pos]
        length = struct.unpack("<H", data[pos + 1 : pos + 3])[0]
        pos += 3 + length
        if field_id == 0:  # EndOfHeader
            return data[:pos]


for path in sys.argv[1:]:
    actual = base64.b64encode(hashlib.sha256(header_bytes(path)).digest()).decode()
    element = PyKeePass(path, password=PASSWORD).tree.find("Meta/HeaderHash")
    stored = element.text if element is not None else None
    print(path)
    print(f"  stored: {stored}")
    print(f"  actual: {actual}")
    print(f"  match : {stored == actual}")
