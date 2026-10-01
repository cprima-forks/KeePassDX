# tel: test fixture

Throwaway KeePassDX database for testing how `tel:` and other URL schemes are handled. **Contains no real data.** Fork-only: lives on `fork-main`, never in a feature branch or PR.

- File: `kp-test-tel.kdbx` (KDBX 3.1, created with KeePassDX 4.5.4)
- Password: `test123` (non-secret, no keyfile)

## Entries

| Title | Where | Value |
|---|---|---|
| tel-url | URL | `tel:+1234567890` |
| tel-custom | custom field `phone` | `tel:+1234567890` |
| tel-notes | notes | `tel:+1234567890` |
| ctl-https | URL | `https://example.com` |
| ctl-mailto | URL | `mailto:a@example.com` |
| ctl-bare | notes | `0301234567` |

The database also contains the built-in `Templates` group that KeePassDX adds to a new database.

## Rebuilding / repairing

`populate.py` brings the database in line with its spec and is idempotent: a second run changes nothing and does not rewrite the file.

```
uv sync
uv run python populate.py kp-test-tel.kdbx --dry   # show the plan
uv run python populate.py kp-test-tel.kdbx
uv run python check_headerhash.py kp-test-tel.kdbx
```

Why the script empties `Meta/HeaderHash`: pykeepass regenerates the file header on every save but keeps the old `HeaderHash`. KeePassDX compares it with the real header hash (`DatabaseInputKDBX.kt`) and refuses to load the file on a mismatch ("Could not load the database"). An empty value skips that check.

Related issues: #1 (baseline), #2 (epic), #3 (this fixture).
