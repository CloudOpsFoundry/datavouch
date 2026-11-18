# Engineering workflow integration

`datavouch gate` applies an explicit policy to an offline verification input. It uses the existing verification engine and never collects cloud evidence, approves changes or merges code. Its default behavior writes JSON only to stdout.

## Repeat locally

From this checkout, using the installed development environment:

```sh
.venv/bin/datavouch gate examples/verification/passing.json \
  --policy examples/workflow/policy.json
```

To generate JSON, Markdown and standalone HTML in one evaluation, use a **new** directory:

```sh
.venv/bin/datavouch gate examples/verification/passing.json \
  --policy examples/workflow/policy.json \
  --output-dir /tmp/datavouch-review-1
```

Open `/tmp/datavouch-review-1/report.html` locally. `report.json` matches stdout exactly; `summary.md` is suitable for a pull request's workflow summary. Existing directories, including symlinks, are rejected to preserve prior evidence. A write error exits 2; discard partial artifacts from an unsuccessful write. Parent directories must already exist.

Repeat with `examples/verification/incorrect.json` (exit 1) and `examples/workflow/unknown.json` (exit 3). Use a different output directory for each invocation. To exercise allowed UNKNOWN, copy the policy and set `unknown` to `allow`; the latter fixture exits 0 while retaining evidence status UNKNOWN and gate status ALLOWED_UNKNOWN.

## Explicit policy

The versioned [example policy](../examples/workflow/policy.json) declares:

- `schema_version`: exactly `workflow-policy-0.1`.
- `unknown`: `block` or `allow`; a required choice, with `block` in the example.
- `comparison`: existing metric, threshold, sample count and normalization policy.
- `required_checks`: 1–100 correctness check names, each at most 300 characters.
- `reliability`: `max_failure_percent` and `max_increase_points`.

The external policy replaces the input's comparison policy, required check list and reliability thresholds. It cannot supply the reliability `complete` attestation. Windows, timestamps, execution cohorts and correctness evidence still come from the input. Evidence for unrequested checks is rejected by the verification schema. No caller input is mutated.

| Evidence | UNKNOWN policy | Gate | Exit |
| --- | --- | --- | --- |
| PASS | Either | PASS | 0 |
| FAIL | Either | FAIL | 1 |
| UNKNOWN | block | BLOCKED_UNKNOWN | 3 |
| UNKNOWN | allow | ALLOWED_UNKNOWN | 0 |
| Invalid input/policy or output error | Either | No successful report | 2 |

A known mandatory failure dominates missing evidence. An allowed UNKNOWN is a workflow exception, not verification success. Protect and review policy changes alongside code; a repository writer who can weaken policy or evidence can weaken the gate.

## Report contract

The deterministic `workflow-0.1` JSON contains `evidence_status`, `gate_status`, `exit_code`, `unknown_policy`, `checks` (name/status), a performance summary, limitations, and three SHA256 fingerprints. `input_sha256` and `policy_sha256` hash sorted, indented JSON with a trailing newline, UTF-8, and finite numbers; `effective_input_sha256` uses the existing verification report's canonicalization for the input after policy application. Fingerprints are reproducibility aids, not signatures. The committed [expected report](../examples/workflow/expected_report.json) provides a compatibility fixture. Breaking contract changes require a new schema version; consumers should reject unsupported versions and tolerate additive fields.

Artifacts omit raw source documents, job IDs and evidence references. User-supplied names and metric labels remain visible; review them before sharing. Markdown encodes check labels to prevent injected links or mentions; HTML escapes text and loads no scripts, styles or network resources. No actual savings or causal improvement is claimed.

## GitHub Actions

[The sample workflow](../.github/workflows/workload_verification.yml) runs the synthetic fixture on hosted runners using read-only repository permission and no cloud credentials. The gate's nonzero exit fails the step. Subsequent `always()` steps retain the summary and reports without masking that failure. Reports expire after seven days. It does not post comments, approve pull requests or enable auto-merge.

GitHub displays Markdown written to `GITHUB_STEP_SUMMARY` on the workflow run summary. See [official summary documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#adding-a-job-summary). Artifact upload is pinned to the reviewed [v7.0.2 release](https://github.com/actions/upload-artifact/releases/tag/v7.0.2).

For a consuming repository, install a trusted released wheel or an immutable trusted revision, copy the workflow pattern, and replace the synthetic input and policy paths with reviewed local evidence. The current sample installs this checkout to test its development version. Branch protection and trusted evidence production must be configured separately; the sample alone is not an enforcement boundary against malicious pull requests. Do not switch to `pull_request_target` or attach cloud credentials to untrusted PR execution.

## Real-environment validation steps

1. Run the local PASS, FAIL and UNKNOWN examples and inspect all three report formats.
2. After the project is committed to an authorized GitHub repository, run **Workload verification example** manually. Confirm its summary and artifact, then use a disposable branch to test FAIL and blocked UNKNOWN. Remote GitHub execution has not yet been validated.
3. For workload evidence, use sanitized inputs from authorized `sandbox-platform-services` runs in `eu`, with the same project for quota/billing. Run the gate locally first and compare with `datavouch verify` using equivalent policy. Do not include credentials or raw billing extracts in artifacts. Real financial reconciliation is a separate task.
