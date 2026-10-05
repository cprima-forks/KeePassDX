"""Builds notes-markdown-example.kdbx: a KeePass database with one entry whose Notes field shows what the
Markdown spike (upstream issue #2702) turns into formatting, and what it deliberately leaves as typed.

The entry is fictional: no real data, the password of the database is `test123`.

    uv run python make_markdown_example.py

The database is rebuilt from scratch every time, so the script is the single source of the entry.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

from pykeepass import create_database

HERE = Path(__file__).resolve().parent
DATABASE = HERE / "notes-markdown-example.kdbx"
PASSWORD = "test123"

TITLE = "Home network (example)"

# KeePassDX shows an entry that does not expire with this expiry time. pykeepass writes the creation time instead, and
# the edit screen then counts the entry as changed and asks "Discard changes?" on a back press with no change made.
NEVER_EXPIRES = datetime(2999, 11, 28, 23, 59, 59, tzinfo=timezone.utc)

# What the renderer shows as formatting comes first, then what it leaves as typed. The line that ends in \x20\x20
# (two spaces) is on purpose: that is a line break in Markdown. It is written as an escape, because editors and
# tools strip trailing spaces from a source file.
NOTES = """# Home network

Router login: **admin**, the password is in the password field of this entry.\x20\x20
Second line of the same paragraph, after a line break.

Support hotline: [Provider support](tel:+4930123456)
Write to [help desk](mailto:help@example.com) or open [the portal](https://example.com/help).

## If the line is down

1. Restart the router
2. Wait *two minutes*
3. Call support and say the contract number `A-12345`

- Do not reboot twice
- Note the time of the call

> Never give the password on the phone.

---

## Left as typed

| Port | Use |
|------|-----|
| 22   | SSH |

```
ssh admin@192.168.0.1
```

![network diagram](http://example.com/net.png)

A single line break
in the middle of a paragraph is a space.
"""


def main() -> int:
    if DATABASE.exists():
        DATABASE.unlink()
    database = create_database(str(DATABASE), password=PASSWORD)
    entry = database.add_entry(
        database.root_group,
        title=TITLE,
        username="admin",
        password="example-not-a-secret",
        url="https://example.com/router",
        notes=NOTES,
        expiry_time=NEVER_EXPIRES,
        icon="0",
    )
    entry.expires = False
    database.save()
    print(f"{DATABASE.name}: 1 entry, password {PASSWORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
