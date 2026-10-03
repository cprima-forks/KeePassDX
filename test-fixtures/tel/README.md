# tel: test fixture

Throwaway KeePassDX database for testing how `tel:` and other URL schemes are handled. **Contains no real data.** Fork-only: committed on the feature branch, but left out of the upstream PR (see `FORK-WORKFLOW.md`).

- File: `kp-test-tel.kdbx` (KDBX 3.1, created with KeePassDX 4.5.4)
- Password: `test123` (non-secret, no keyfile)
- Open it **read-only** when testing, so that nothing is saved.

## What the entries are

`fixture-spec.json` is the source of truth. It lists the entries (version 2: 40), the UI scenarios (tap, long-press, Call, two numbers, wrapped number, edit mode, copy, reopen) and which entries use them.

- An entry is either a UI-only entry with its own `value` (long-press at the start, middle and end of a text, two numbers, a wrapped number, edit and copy, and the controls from version 1), or it takes its value from a case of the code-level case file `app/src/sharedTest/resources/tel-link-cases.json` (`valueFrom`: a case id). The unit and phone tests check that case; the fixture shows what a user sees for the same text.
- The **Notes** field of every entry holds the instructions: the numbered steps of its scenarios, what is expected (for a case, taken from the case file), and the entry id. For an entry that tests the Notes field, the tested value is the last line.
- Cases of the group `observed` record today's behaviour without a decision. The Notes of such an entry say so.
- Entries and cases are aligned by reference and by an automated check, not generated from each other: not every case needs a UI entry (`check_alignment.py` lists the ones without).

The database also contains the built-in `Templates` group that KeePassDX adds to a new database; the scripts leave it alone.

## Rebuilding / repairing

`populate.py` brings the database in line with the spec and the case file. It is idempotent: a second run changes nothing and does not rewrite the file. It removes entries of the root group that the spec does not list.

```
uv sync
uv run python populate.py kp-test-tel.kdbx --dry   # show the plan
uv run python populate.py kp-test-tel.kdbx
uv run python check_alignment.py kp-test-tel.kdbx  # spec, case file and database agree?
uv run python check_headerhash.py kp-test-tel.kdbx
```

From the repository root: `just fixture dry`, `populate`, `align`, `check`.

Why the script empties `Meta/HeaderHash`: pykeepass regenerates the file header on every save but keeps the old `HeaderHash`. KeePassDX compares it with the real header hash (`DatabaseInputKDBX.kt`) and refuses to load the file on a mismatch ("Could not load the database"). An empty value skips that check.

Related issues: #1 (baseline), #2 (epic), #3 (this fixture), #10 (test model).
