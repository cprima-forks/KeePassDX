"""Idempotently populate the tel: test fixture database from fixture-spec.json.

Re-running makes no change (and does not rewrite the file) once the
database matches the spec. Entries are matched by title; entries that are
not in the spec are removed.

    uv run python populate.py kp-test-tel.kdbx --dry
    uv run python populate.py kp-test-tel.kdbx
"""

import argparse
import sys

from pykeepass import PyKeePass

import fixture_spec

PASSWORD = "test123"  # documented, non-secret test password


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
    elif (entry.url or "") != want["url"]:
        changes.append("url")
        if not dry:
            entry.url = want["url"]

    if entry is not None:
        if (entry.notes or "") != want["notes"]:
            changes.append("notes")
            if not dry:
                entry.notes = want["notes"]

        have = dict(entry.custom_properties)
        for key, value in want["custom"].items():
            if have.get(key) != value:
                changes.append(f"custom[{key}]")
                if not dry:
                    entry.set_custom_property(key, value)
        for key in set(have) - set(want["custom"]):
            changes.append(f"custom[{key}] remove")
            if not dry:
                entry.delete_custom_property(key)
    else:
        changes.append("with url, notes and custom fields")

    print(f"{title:42} {'; '.join(changes) if changes else 'ok (no change)'}")
    return bool(changes)


def remove_stale(kp: PyKeePass, titles: set[str], dry: bool) -> bool:
    changed = False
    # only the entries of the root group: the KeePassDX templates live in their own group
    for entry in list(kp.root_group.entries):
        if entry.title not in titles:
            print(f"{entry.title:42} remove (not in the spec)")
            if not dry:
                kp.delete_entry(entry)
            changed = True
    return changed


def clear_header_hash(kp: PyKeePass, dry: bool) -> bool:
    """Empty Meta/HeaderHash so KeePassDX does not reject the file.

    pykeepass regenerates the header (seed, IV) on every save but keeps the
    old HeaderHash. KeePassDX compares it with the real header hash
    (DatabaseInputKDBX.kt) and refuses to load on a mismatch. An empty
    value skips that check.
    """
    element = kp.tree.find("Meta/HeaderHash")
    if element is None or not (element.text or ""):
        print(f"{'HeaderHash':42} ok (already empty)")
        return False
    print(f"{'HeaderHash':42} clear (stale after save)")
    if not dry:
        element.text = ""
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("database")
    ap.add_argument("--password", default=PASSWORD)
    ap.add_argument("--dry", action="store_true", help="print plan, write nothing")
    args = ap.parse_args()

    spec = fixture_spec.load_spec()
    cases = fixture_spec.load_cases(spec)
    want = fixture_spec.wanted(spec, cases)

    kp = PyKeePass(args.database, password=args.password)
    print(f"opened {args.database} (KDBX {kp.version[0]}.{kp.version[1]}), "
          f"{len(kp.entries)} entries, spec has {len(want)}")

    changed = [reconcile(kp, t, w, args.dry) for t, w in want.items()]
    changed.append(remove_stale(kp, set(want), args.dry))
    # a save regenerates the header, so the hash is cleared after any change
    changed.append(clear_header_hash(kp, args.dry))

    if not any(changed):
        print("up to date, file not rewritten")
    elif args.dry:
        print("dry run: nothing written")
    else:
        # entries changed above leave Meta/HeaderHash stale again on save
        kp.save()
        element = kp.tree.find("Meta/HeaderHash")
        if element is not None and (element.text or ""):
            element.text = ""
            kp.save()
        print("saved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
