# Fork workflow

This is a personal fork of [Kunzisoft/KeePassDX](https://github.com/Kunzisoft/KeePassDX).
It is used for upstream contributions.

## Branches

| Branch | Purpose | Rules |
|---|---|---|
| `master` | Mirror of upstream `master` | Fast-forward from upstream only. Never commit directly. |
| `develop` | Mirror of upstream `develop` | Fast-forward from upstream only. Never commit directly. Base for the feature branch. |
| `feature/<upstream-issue#>-<slug>` | The one working branch for an upstream issue | Branch off `develop`. All work for that issue lives here: code, tests, research, fixtures. |
| `spike/<slug>` | Exploration of an idea, for example `spike/notes-markdown` (upstream #2702) | Branch off `develop`. Short-lived. It carries the fork test infrastructure so that the idea can be tested. It is not a pull request branch. |

There is one feature branch at a time, and spike branches for exploration. No other long-lived or side branches.

`fork-main` is not part of this workflow.

## Rules

- Every change is tracked as an issue in this fork. The branch name uses the **upstream** issue number. Fork issue numbers overlap with upstream numbers, so they are for tracking only and never appear in branch names.
- Never commit directly to `master` or `develop`.
- Work follows the phases: requirements, design, implement, test, PR. Each phase ends with an approval.
- Commit and push only when asked.
- Upstream PRs follow upstream `CONTRIBUTING.md`: discuss in an upstream issue first, keep commits small and logical, include tests, and state how the code was reviewed and which tools helped.
- Fork-only material (this document, `justfile`, `cprima-fork/tools/`, `cprima-fork/test-fixtures/`) is committed on the feature branch, but must not appear in the upstream PR. Research, notes and checklists live in the [wiki](https://github.com/cprima-forks/KeePassDX/wiki), not in the repository. When the PR is prepared, put only the code and test commits on a clean branch off `develop` (cherry-pick), and leave the fork-only commits behind.
- Test databases contain no real data and use a documented, non-secret password. Never copy a real database into the repository.

## Syncing with upstream

```
gh repo sync cprima-forks/KeePassDX --branch master  --source Kunzisoft/KeePassDX
gh repo sync cprima-forks/KeePassDX --branch develop --source Kunzisoft/KeePassDX
git fetch origin
git rebase origin/develop      # while the feature branch is unpushed; merge once it is pushed
```

`gh repo sync` fast-forwards only and fails if the branch has diverged. Do not force it.

## Testing on a device

The F-Droid install `com.kunzisoft.keepass.libre` must not be replaced: the debug build has the same id and a different signature. Build `freeDebug` (id `com.kunzisoft.keepass.free`) to run side by side.

Test data lives in `cprima-fork/test-fixtures/`; see the README there.
