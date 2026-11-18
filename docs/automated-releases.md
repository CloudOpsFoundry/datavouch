# Automated protected releases

The public workflow uses Google’s Release Please action, pinned to v5.0.0 by commit SHA. It runs only after successful CI for a push to main. It never runs on a pull request or a manual validation dispatch and does not check out contributor code in the write-enabled job.

## Version rules

| Conventional commit | Next version from 1.0.0 |
| --- | --- |
| `fix:` or `perf:` | 1.0.1 |
| `feat:` | 1.1.0 |
| `feat!:` or a `BREAKING CHANGE:` footer | 2.0.0 |
| `docs:`, `chore:`, `ci:`, tests without a breaking change | No feature release |

Use these prefixes in squash-merge PR titles. The highest applicable change since the last release determines the increment; issue priority alone does not determine compatibility.

## Protected sequence

1. Product changes pass `Public CI passed` and the owner merges the PR.
2. Successful main CI opens or updates a release PR containing generated release notes and synchronized versions in pyproject.toml, uv.lock, the Python version constant, Helm metadata and the release manifest.
3. The workflow explicitly dispatches read-only public CI for the bot-created release branch. GitHub's built-in token does not automatically trigger push or pull-request workflows for its own changes. No personal token is stored.
4. The owner reviews and merges the passing release PR. The bot cannot merge or bypass owner-only protected main.
5. Successful main CI recognizes the merged release PR and creates the version tag and GitHub release notes. No wheel, container, package-registry publication or CI artifact upload occurs. GitHub automatically supplies source archives for tags.

Version calculation, changelog maintenance, tags and notes are automated. Owner review/merge deliberately remains required. Existing releases are not rewritten. The automation baseline is v1.0.0, so deletion of earlier alpha tags does not affect future increments. Do not edit dependency versions to force a release.

## Permissions and recovery

Only the main release job receives contents, pull-request, issue-label and Actions-dispatch write permissions. The repository must allow Actions to create pull requests; GitHub combines this setting with review permission, but this workflow never approves reviews. Main restrictions still exclude the bot from pushing or merging. All validation uses read-only tokens on disposable hosted runners. The retired private workflows remain disabled.

A failed release job can be rerun after its error is fixed. Release Please reconciles existing release PRs, tags and releases. If main has already advanced when the job starts, it skips the stale run. A failed validation never starts release automation. Inspect the exact SHA and required check before merging a release PR.

Release automation is not client-deployment acceptance or independent security approval. See [client validation](client-validation.md) and [the review pack](review-pack.md).

References: [Release Please action](https://github.com/googleapis/release-please-action), [version file customization](https://github.com/googleapis/release-please/blob/main/docs/customizing.md).
