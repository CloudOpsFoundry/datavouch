# Offline comparison configuration

Use [the complete synthetic fixture](../examples/bigquery/comparison.json) as the input schema example. Input is bounded to 5 MB. Unknown fields, duplicate JSON keys, duplicate execution IDs, negative measurements and nonfinite values are rejected. All measurements have a name, explicit unit and direction (`lower` or `higher`). Units and directions must match exactly. Automatic unit conversion is not supported.

An experiment identifies its baseline observations, candidate observations and engineering change. Each observation identifies the workload, environment and input snapshot. Comparability evidence must cite a reference and describe why conditions are comparable. This is a caller assertion, not independent validation. Do not claim comparable conditions without supporting records. These records contain no timestamps, so observation window and chronological change validation are not supported yet.

The policy selects one metric, a nonnegative `max_regression_percent` (default 0), a positive integer `minimum_samples` (default 3), and a boolean `normalize` (default false). Sample count is an eligibility requirement, not a statistical confidence measure. Cached or unsuccessful executions, missing metrics, mismatching workloads and overlapping baseline/candidate IDs produce UNKNOWN.

The comparison uses arithmetic means. Relative regression is `100 * (candidate_mean / baseline_mean - 1)` for lower is better, with the sign reversed for higher is better. A result passes when regression is at or below the configured limit. Floating point boundary equality uses relative and absolute tolerances of `1e-12`. PASS means the configured metric check passed, not that the change improved the entire workload.

Normalization divides each execution's measurement by its positive input volume before calculating the mean. The input unit labels must match. This is the mean of per-execution ratios, not a volume weighted ratio. The caller must justify a linear input volume relationship. A zero baseline and nonzero candidate return UNKNOWN. Two zero means produce zero relative change.

Reports contain raw evidence, policy, limitations, results and an input digest. They exclude generation timestamps and sort observations by execution ID. Identical inputs produce identical report bytes, including when observation order differs. The experimental schema version is `0.1` and may change before a stable release.

CLI exits are 0 for metric PASS, 1 for metric FAIL, 2 for malformed input and 3 for metric UNKNOWN. The exit code evaluates only the selected metric. It does not imply correctness. The metric-only correctness result remains UNKNOWN. Use the separate `verify` command for configured correctness, reliability and an aggregate verdict. See [verification](verification.md).
