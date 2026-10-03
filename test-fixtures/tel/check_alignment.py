"""Check that fixture-spec.json, the case file and the fixture database agree.

Errors (exit 1): a valueFrom that names no case, an entry missing from the
database or with other content than the spec says, an entry in the database
that the spec does not know, a Notes field without the instructions.
Information: cases that no entry uses.

    uv run python check_alignment.py kp-test-tel.kdbx
"""

import argparse
import sys

from pykeepass import PyKeePass

import fixture_spec

PASSWORD = "test123"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("database")
    ap.add_argument("--password", default=PASSWORD)
    args = ap.parse_args()

    spec = fixture_spec.load_spec()
    cases = fixture_spec.load_cases(spec)
    errors = []

    ids = [e["id"] for e in spec["entries"]]
    for dup in {i for i in ids if ids.count(i) > 1}:
        errors.append(f"spec: duplicate entry id {dup}")
    for entry in spec["entries"]:
        ref = entry.get("valueFrom")
        if ref is not None and ref not in cases:
            errors.append(f"spec: {entry['id']} takes its value from unknown case {ref}")
        for name in entry.get("scenarios", []):
            if name not in spec["scenarios"]:
                errors.append(f"spec: {entry['id']} uses unknown scenario {name}")
    if errors:
        print("\n".join(errors))
        return 1

    want = fixture_spec.wanted(spec, cases)
    kp = PyKeePass(args.database, password=args.password)
    # the KeePassDX templates live in their own group and are not part of the fixture
    have = {e.title: e for e in kp.root_group.entries}

    for title, w in want.items():
        entry = have.get(title)
        if entry is None:
            errors.append(f"database: entry {title} missing")
            continue
        if (entry.url or "") != w["url"]:
            errors.append(f"database: {title} url {entry.url!r}, spec {w['url']!r}")
        if (entry.notes or "") != w["notes"]:
            errors.append(f"database: {title} notes differ from the spec")
        if dict(entry.custom_properties) != w["custom"]:
            errors.append(f"database: {title} custom fields differ from the spec")
        if "Expected:" not in (entry.notes or ""):
            errors.append(f"database: {title} has no instructions in Notes")
    for title in have.keys() - want.keys():
        errors.append(f"database: entry {title} is not in the spec")

    used = {e["valueFrom"] for e in spec["entries"] if "valueFrom" in e}
    unused = sorted(c for c, v in cases.items() if c not in used and "input" in v)
    print(f"{len(want)} spec entries, {len(have)} database entries, {len(cases)} cases")
    print(f"cases without a fixture entry: {len(unused)} (information)")
    for case_id in unused:
        print(f"  {case_id}")

    if errors:
        print("\n".join(errors))
        return 1
    print("aligned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
