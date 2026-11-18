# Independent review pack

The owner has authorized source publication. Independent reviews below remain outstanding deployment assurance tasks; publication does not represent their completion. Implementation, automated validation, independent review and publication are separate states. The maintainer who implemented the changes cannot supply independent approval for their own work.

Start with [the product explanation](product.md), [user guide](user-guide.md), [acceptance matrix](product-acceptance.md) and [known release limitations](release-readiness.md). Review the exact candidate commit and artifacts, not a moving branch. Copy [the review record](review-record.md) into a private evidence location. Assign a reviewer and evidence reference to each decision; an unassigned review is pending.

## Prepare the evidence

Use a clean authorized checkout of the candidate commit. Python 3.15.2, uv, actionlint and the documented development prerequisites are required. Set a private destination outside the checkout; use a new directory for each revision.

```sh
set -e
export DATAVOUCH_REVIEW_DIR="$(mktemp -d "${TMPDIR:-/tmp}/datavouch-review.XXXXXX")"
chmod 700 "$DATAVOUCH_REVIEW_DIR"
git rev-parse HEAD > "$DATAVOUCH_REVIEW_DIR/revision.txt"
git status --porcelain > "$DATAVOUCH_REVIEW_DIR/worktree.txt"
uv sync --locked --all-extras
uv run --no-sync python scripts/validate.py > "$DATAVOUCH_REVIEW_DIR/validation.log" 2>&1
```

Stop if any command fails or the worktree is dirty. The validator performs formatting, lint, types, security/dependency checks, tests/coverage, builds, clean installation and source/wheel parity. Then collect inventory and measurements:

```sh
uv run --no-sync python scripts/check_release.py > "$DATAVOUCH_REVIEW_DIR/release-inventory.json"
uv export --locked --all-extras --no-dev --format cyclonedx1.5 --output-file "$DATAVOUCH_REVIEW_DIR/runtime-sbom.json"
uv export --locked --all-extras --format cyclonedx1.5 --output-file "$DATAVOUCH_REVIEW_DIR/development-sbom.json"
uv run --no-sync python scripts/benchmark.py > "$DATAVOUCH_REVIEW_DIR/benchmark.json"
cp dist/*.whl dist/*.tar.gz "$DATAVOUCH_REVIEW_DIR/"
```

The lockfile SBOM describes Python dependencies, including applicable platform alternatives; it is not a scan of an installed container. Inventory the Python base image, OS packages and build tooling separately when reviewing a distributed image. License metadata and vulnerability scans are evidence inputs, not legal or security approval. Keep private reports out of Git; share through the agreed reviewer channel.

## Security review

Use a reviewer who did not implement the change and has experience with web authentication, cloud IAM and software supply chains. Supply code, architecture, source history, artifact hashes, dependency inventories, test results and the deployment trust diagram. No production credentials are needed for source review.

Review these boundaries explicitly:

- Untrusted JSON, duplicate keys, numeric limits, resource limits, file paths and safe template rendering.
- Basic local access versus verified gateway identities, actual peer checks, host/origin checks, subject-bound form tokens, role/connection isolation and revocation.
- Cloud credential scope, selected job filtering, parameterized metadata reads, cost/time limits and sensitive metadata in reports or logs.
- Run-store ownership, symlinks/permissions, concurrent deletion, stale confirmation, recovery, audit integrity/retention and denial-of-service limits.
- Trusted Python adapters and their ability to execute arbitrary code; evidence attestations are not cryptographic proof.
- Container/chart defaults, image provenance, dependency findings and the real gateway/network results from [client validation](client-validation.md).
- All reachable Git history and release archives for credentials, private context, customer data and ownership-sensitive material. Use a maintained secret scanner with redacted output; inspect findings privately. A clean scan is not exhaustive proof.
- CI permissions, pinned dependencies/actions, contributor trust, branch protections and release authority.

Record severity, affected revision, reproduction, proposed fix and retest evidence. Resolve critical/high findings before publication. Other findings need explicit owner disposition; do not silently relabel failures as accepted. Validate the security mailbox is monitored and name the response owner and backup. Existing application tests are a starting point, not an independent penetration test.

For a repeatable history scan, install a reviewed release of [Gitleaks](https://github.com/gitleaks/gitleaks/releases) from its official distribution and verify the published checksum. With the private review directory defined above:

```sh
gitleaks version
gitleaks git . --log-opts=--all --redact --report-format json --report-path "$DATAVOUCH_REVIEW_DIR/history-secrets.json"
```

Exit code 1 means findings need triage; it is not a passed check. Inspect each flagged line and its context privately, including synthetic fixtures. Record false-positive decisions explicitly and keep the original redacted report. Do not globally ignore test directories or rewrite history to hide a finding. Scan the final committed candidate and released files; this Git command does not inspect uncommitted or ignored files.

## Independent onboarding

Ask a person unfamiliar with the implementation to follow [getting started](getting-started.md) and [the measured demo](local-demo.md) on a clean machine. Do not coach around unclear instructions without recording the problem.

Record OS/architecture, Python version, exact commands, installation time, time to first understandable report, failed steps and the participant's own explanation of workloads/experiments/runs. Ask them to:

1. Explain why successful SQL execution is insufficient evidence of correctness.
2. Find the equivalent, incorrect and missing-evidence demo results and explain each check.
3. Reproduce a saved report with the CLI and compare it with the UI.
4. Create and validate a plan without cloud access; explain why validation is not verification.
5. In an approved execution deployment, inspect a completed run, an error and a missing-evidence case. Use disposable records to test individual and bulk deletion and verify unrelated history remains.
6. Follow either Compose or Helm installation and recovery documentation in an authorized test environment.

Measure misunderstandings and setup effort; do not invent a satisfaction score or speed improvement. Triage findings, amend the instructions and have the participant retry the affected steps. A developer replay is useful but not independent onboarding.

## License and ownership review

The selected source license is MIT. Provide LICENSE, contribution history, dependency inventories, copied or generated assets, container base-image information and distribution contents to a qualified reviewer or the organization's responsible owner.

Confirm rights to publish each contribution, including any employment or third-party restrictions. Review actual license files and required notices for runtime dependencies, optional SDK/web dependencies, distributed images and bundled tools. Treat missing or ambiguous metadata as unresolved. Confirm that source and wheel carry the intended license, and that the intended distribution method satisfies applicable obligations. Record the reviewer, scope, conclusions and exceptions. The presence of an MIT file does not establish ownership or dependency compatibility.

No legal conclusion is implied by the generated inventory. If the reviewer requires an additional notice file or source-offer materials, prepare and verify them before releasing the affected artifact.

## Financial-method review

A reviewer familiar with cloud pricing and workload attribution should examine usage estimates, supplied spending, allocation, counterfactual assumptions, overlapping claims and exact arithmetic. Use synthetic rates and inputs. Verify that absent evidence stays UNKNOWN and no runtime/slot reduction is automatically presented as realized monetary savings. Record which claims the evidence supports and which it does not.

## Publication handoff

For any publication, record unresolved reviews as unverified and obtain explicit owner authorization. Then:

1. Resolve findings and bind the approvals to the final commit and artifact hashes. Rerun affected tests and CI after changes.
2. Prepare public contribution CI on disposable standard GitHub-hosted runners with no cloud credentials and a read-only token. Keep `pull_request_target` away from untrusted code. Remove this repository's access to persistent self-hosted runners before publication; a workflow condition alone is not a security boundary against workflow edits.
3. Require CI and reviewed changes on main, disallow force pushes/deletion, restrict merging to the owner, and verify enforcement on the selected GitHub plan. A sole author cannot independently approve their own PR; appoint an independent reviewer or document the governance limitation. Do not silently bypass it.
4. Confirm the security contact, maintainer responsibilities, release notes, known limits and tested platforms. Retain the experimental version unless evidence supports a broader stability promise.
5. Have the owner authorize the concrete publication candidate. Change visibility, verify public repository protections and run public CI against that exact revision before releasing artifacts. No package-registry publication is implied by source publication.

GitHub recommends avoiding persistent self-hosted runners for public repositories. Standard hosted runners are free for public repositories; no paid upgrade is required for that runner choice. See [GitHub's security guidance](https://docs.github.com/en/actions/reference/security/secure-use) and [runner selection](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job). Validate current settings at the time of publication.
