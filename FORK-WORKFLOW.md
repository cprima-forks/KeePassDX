# Fork workflow

This is a personal fork of [Kunzisoft/KeePassDX](https://github.com/Kunzisoft/KeePassDX).
It is used for upstream contributions and for fork-only extras.

## Branches

| Branch | Purpose | Rules |
|---|---|---|
| `master` | Mirror of upstream `master` | Fast-forward from upstream only. Never commit directly. |
| `develop` | Mirror of upstream `develop` | Fast-forward from upstream only. Never commit directly. Base for all PRs. |
| `feature/<upstream-issue#>-<slug>` | Work for one upstream issue | Branch off `develop`. Source of upstream PRs. |
| `fork-main` | Fork-only extras: this document, test fixtures, personal patches | Merge `master` into it to keep current. Never commit directly: change it by pull request. Never an upstream PR source. |
| `extras/<upstream-issue#>-<slug>` or `extras/<slug>` | Fork-only work: fixtures, tooling, docs | Branch off `fork-main`, merge back by pull request. Never an upstream PR source. |

## Rules

- Every change is tracked as an issue in this fork. Branch names use the **upstream** issue number the work relates to. Fork issue numbers overlap with upstream numbers, so they are for tracking only and never appear in branch names. Work with no upstream issue uses `extras/<slug>`.
- Never commit directly to `master`, `develop` or `fork-main`.
- Work follows the phases: requirements, design, implement, test, PR. Each phase ends with an approval.
- Upstream PRs follow upstream `CONTRIBUTING.md`: discuss in an upstream issue first, keep commits small and logical, include tests, and state how the code was reviewed and which tools helped.
- Test data (for example `.kdbx` fixtures) lives only on `fork-main` and `extras/*` branches. It must never appear in a `feature/*` branch or PR diff.
- Test databases contain no real data and use a documented, non-secret password.

## Syncing with upstream

```
gh repo sync cprima-forks/KeePassDX --branch master  --source Kunzisoft/KeePassDX
gh repo sync cprima-forks/KeePassDX --branch develop --source Kunzisoft/KeePassDX
git checkout fork-main && git merge master
```

`gh repo sync` fast-forwards only and fails if the branch has diverged. Do not force it.

## Testing on a device

The F-Droid install `com.kunzisoft.keepass.libre` must not be replaced: the debug build has the same id and a different signature. Build `freeDebug` (id `com.kunzisoft.keepass.free`) to run side by side.
