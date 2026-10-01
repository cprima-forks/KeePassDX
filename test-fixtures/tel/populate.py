"""Idempotently populate the tel: test fixture database.

Re-running makes no change (and does not rewrite the file) once the
database matches SPEC. Entries are matched by title.

    uv run python populate.py kp-test-tel.kdbx --dry
    uv run python populate.py kp-test-tel.kdbx
"""

import argparse
import sys

from pykeepass import PyKeePass

PASSWORD = "test123"  # documented, non-secret test password

# title -> desired url / notes / custom (advanced) fields
SPEC = {
    "tel-url": {"url": "tel:+1234567890", "notes": "", "custom": {}},
    "tel-custom": {"url": "", "notes": "", "custom": {"phone": "tel:+1234567890"}},
    "tel-notes": {"url": "", "notes": "tel:+1234567890", "custom": {}},
    "ctl-https": {"url": "https://example.com", "notes": "", "custom": {}},
    "ctl-mailto": {"url": "mailto:a@example.com", "notes": "", "custom": {}},
    "ctl-bare": {"url": "", "notes": "0301234567", "custom": {}},
}


def reconcile(kp: PyKeePass, title: str, want: dict, dry: bool) -> bool:
    """Bring one entry in line with `want`. Return True if anything changed."""
    entry = kp.find_entries(title=title, first=True)
    changes = []

    if entry is None:
        changes.append("create")
        if not dry:
            entry = kp.add_entry(
                kp.root_group, title, "", PASSWORD, url=want["url"] or None
            )
    else:
        if (entry.url or "") != want["url"]:
            changes.append(f"url {entry.url!r} -> {want['url']!r}")
            if not dry:
                entry.url = want["url"]

    if entry is not None:
        if (entry.notes or "") != want["notes"]:
            changes.append(f"notes {entry.notes!r} -> {want['notes']!r}")
            if not dry:
                entry.notes = want["notes"]

        have = dict(entry.custom_properties)
        for key, value in want["custom"].items():
            if have.get(key) != value:
                changes.append(f"custom[{key}] {have.get(key)!r} -> {value!r}")
                if not dry:
                    entry.set_custom_property(key, value)
        for key in set(have) - set(want["custom"]):
            changes.append(f"custom[{key}] remove")
            if not dry:
                entry.delete_custom_property(key)
    else:
        # dry run for a new entry: report what it would carry
        for key, value in want["custom"].items():
            changes.append(f"custom[{key}] = {value!r}")
        if want["notes"]:
            changes.append(f"notes = {want['notes']!r}")

    print(f"{title:12} {'; '.join(changes) if changes else 'ok (no change)'}")
    return bool(changes)


def clear_header_hash(kp: PyKeePass, dry: bool) -> bool:
    """Empty Meta/HeaderHash so KeePassDX does not reject the file.

    pykeepass regenerates the header (seed, IV) on every save but keeps the
    old HeaderHash. KeePassDX compares it with the real header hash
    (DatabaseInputKDBX.kt) and refuses to load on a mismatch. An empty
    value skips that check.
    """
    element = kp.tree.find("Meta/HeaderHash")
    if element is None or not (element.text or ""):
        print(f"{'HeaderHash':12} ok (already empty)")
        return False
    print(f"{'HeaderHash':12} clear (stale after save)")
    if not dry:
        element.text = ""
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("database")
    ap.add_argument("--password", default=PASSWORD)
    ap.add_argument("--dry", action="store_true", help="print plan, write nothing")
    args = ap.parse_args()

    kp = PyKeePass(args.database, password=args.password)
    print(f"opened {args.database} (KDBX {kp.version[0]}.{kp.version[1]}), "
          f"{len(kp.entries)} entries")

    changed = [reconcile(kp, t, w, args.dry) for t, w in SPEC.items()]
    changed.append(clear_header_hash(kp, args.dry))

    if not any(changed):
        print("up to date, file not rewritten")
    elif args.dry:
        print("dry run: nothing written")
    else:
        kp.save()
        print("saved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
