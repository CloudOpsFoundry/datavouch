# Automatic private alpha releases

After a push to `main` passes every CI stage and the **CI passed** gate, the release job calculates the next version, updates the changelog, validates release packages, pushes a version commit and annotated tag atomically, and creates a GitHub prerelease with generated notes. Feature branches never release. Repository visibility is unchanged; no PyPI or container-registry publication is configured.

## Declare the change once

Use Conventional Commits for commits and the PR title used by squash merge. The owner still reviews and merges product changes. Automation handles version files, tags and notes afterward; it cannot infer compatibility from issue priority or lines changed.

| Merged change | Increment | Example from 0.1.0a2 |
| --- | --- | --- |
| `fix: correct a result` | Patch | `v0.1.1a0` |
| `perf: reduce collection overhead` | Patch | `v0.1.1a0` |
| `feat: add an adapter` | Minor | `v0.2.0a0` |
| `feat!: change the report contract` | Major | `v1.0.0a0` |
| A `BREAKING CHANGE:` footer | Major | `v1.0.0a0` |
| `docs:`, `test:`, `ci:`, `chore:` without breaking changes | No release | No tag |

The highest increment since the last release wins. Issue references such as `Closes #123` can appear in the commit body. Commitizen 4.19.3 supplies the conventional-commit classifier, exact increment behavior, Python version/uv lockfile updates and changelog generation. Python versions use PEP 440 (`0.2.0a0`); Helm uses the corresponding SemVer form (`0.2.0-alpha.0`).

Automatic releases remain **alpha**, even for a major compatibility change. A major number is not production certification. Moving to stable releases requires a reviewed policy change after the independent acceptance gates are closed.

## Sequence and safeguards

1. Main passes static analysis, tests/coverage, dependency audit, package validation and the aggregate gate.
2. A serialized release job checks out that exact SHA with full tag history. A superseded revision skips release; the newer main pipeline considers accumulated changes.
3. Commitizen updates only release metadata. The package version, Python version constant, uv project entry and Helm metadata stay aligned. Dependency versions are not upgraded.
4. The job rebuilds and validates the stamped wheel/source archives, exclusions, clean installation, source/wheel parity and release metadata. Functional tests have already run on main; unchanged functional code is not tested redundantly here.
5. A `chore(release): VERSION` commit and annotated tag are pushed together without force. A concurrent main update or branch protection rejection prevents the entire push.
6. GitHub release notes come from the new changelog section. The release is marked prerelease, and an existing release is not overwritten. Rerunning the original successful workflow recovers a missing GitHub release after a completed push, even if main has moved on.

GitHub's standard workflow token does not trigger another push workflow when it creates the version commit, preventing a release loop. The release job itself validates the stamped artifacts. See [GitHub's token behavior](https://docs.github.com/en/actions/concepts/security/github_token).

## One-time prerequisites

- Merge this workflow through the normal reviewed PR process.
- Restore a trusted self-hosted runner with the `datavouch_local` label. The private repository must retain its trusted-runner and actor variables.
- Permit this release job's standard `GITHUB_TOKEN` to write repository contents. No personal token is required for an unprotected private branch.
- If enforced branch protection blocks automation writes, configure an approved automation identity and matching branch policy before enabling releases. This workflow does not bypass or weaken protection, and owner-only branch rules may require that one-time setup. Until then, release pushes fail safely.

Only the release job receives `contents: write`; normal jobs retain read access. Public visibility remains blocked pending independent reviews and a separate public-runner trust model. This workflow deliberately requires a private repository.

Remote CI requires an online, registered trusted runner. If none is available, checks remain queued and the PR must wait. Local tests exercise version selection, metadata consistency, changelog sections, no-release changes, atomic rejection and retry behavior without publishing anything.
