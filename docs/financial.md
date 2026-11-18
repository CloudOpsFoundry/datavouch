# Financial evidence assessment

Run `datavouch finance examples/financial/reviewed.json` for a complete synthetic example. Run `datavouch finance examples/financial/estimate_only.json` to see estimates with attribution UNKNOWN. The example rate of 5 currency units per TiB is invented for testing. It is not a current provider price. Neither command reads credentials, queries billing data or fetches prices.

## Input and units

The input declares an experiment ID, claim ID and stable billing `scope`. Use the same canonical scope for the same charge pool across claims, such as a billing account, project, region and SKU or reservation. Do not use experiment IDs as billing scopes or create aliases to evade overlap checks.

`baseline` and `candidate` contain disjoint chronological `start`/`end` windows, distinct `execution_ids`, a usage evidence `reference`, and optional `billed_bytes`, `billed_slot_hours` and `consumed_slot_ms`. Timestamps require time zones. Execution count is the number of unique IDs. Monetary values and billed slot hours are bounded decimal strings, not binary floating point numbers. Integer quantities must be nonnegative INT64 values. Input JSON is limited to 5 MB.

`pricing` declares `model`, `currency`, a decimal-string `rate`, `reference`, `valid_from` and `valid_to`. A usable rate must cover both usage windows. Rates are not bundled or fetched. Supported models:

- `on_demand`: estimated cost is `billed_bytes / 2^40 * rate`, where the rate is currency per TiB. Use billing-adjusted byte quantities. The engine does not reconstruct billing minimums from processed bytes or apply free tiers and discounts automatically.
- `capacity`: estimated cost is `billed_slot_hours * rate`, where the rate is currency per billed slot hour. Billed capacity quantities must already account for the applicable allocation, commitment and autoscaling rules. Consumed job slot milliseconds cannot substitute for these quantities.
- `unknown`: financial attribution is unsupported. Available supplied billing differences can still be displayed without assigning them to an engineering change.

Pricing tables with multiple rates, tiering, currency conversion, annual forecasts and automated contract interpretation are not implemented. If a single applicable rate cannot represent the scope, omit it instead of inventing an average. Supported billing comparisons do not require a modeled rate when an independent review supports the known pricing model.

## Four evidence classifications

`estimated_costs` applies the supplied rate to declared billing quantities. `observed_spending` compares supplied net costs. These are separate measurements and may differ because estimates omit unspecified billing effects.

A billing record must specify `scope`, exact usage-period `start`/`end`, `currency`, `net_cost`, `reference`, globally stable `evidence_ids` and a boolean `complete`. Net cost must already include the relevant credits, adjustments and refunds using a documented accounting basis. Negative net values are supported. Do not treat the raw export cost column as net cost without reconciling credits. Periods, scopes and currencies must match. Incomplete billing produces unsupported comparison. Reusing the same billing evidence in baseline and candidate is an input error.

`measured` means a difference calculated from supplied billing evidence. It does not mean DataVouch authenticated the evidence, reconciled an invoice or confirmed payment. Billing data can arrive late or be adjusted, so completeness must be reviewed upstream.

For both estimated and measured amounts:

```text
raw_difference = baseline_cost - candidate_cost
baseline_cost_at_candidate_volume = baseline_cost * candidate_executions / baseline_executions
normalized_difference = baseline_cost_at_candidate_volume - candidate_cost
```

Positive differences mean lower candidate cost under the corresponding calculation. Normalized fields are explicitly classified `counterfactual`, even when their source amounts are measured. Normalization assumes a supported cost-per-execution relationship. It does not establish what the invoice would actually have been. Zero execution volume makes normalization unavailable. All threshold comparisons use exact rational values. Displayed amounts use 12 fractional digits with half-even rounding, so a very small difference can display as zero while retaining its exact sign for evaluation.

`unsupported` identifies missing or insufficient evidence. No report field claims realized monetary savings.

## Attribution requirements

The `verification` field embeds the full Phase 3 input, not a trusted PASS label. DataVouch recomputes verification and requires PASS. Experiment ID, selected baseline and candidate execution IDs, and both time windows must match the financial input. Failed correctness blocks financial attribution.

`review` requires matching `experiment_id` and `scope`, a nonempty independent evidence `reference`, a `method` of `controlled_experiment` or `independent_review`, and `confounders_addressed: true`. The referenced review must explain billing allocation, pricing and discount changes, workload changes, concurrent changes and any other relevant confounders. A true flag by itself is not independent proof. DataVouch validates the supplied contract but does not authenticate reviews or follow references.

Unequal execution counts or period durations require a `normalization_reference` explaining the supported model. Capacity attribution additionally requires a `capacity_change_reference` explaining the link between the engineering change and actual billed capacity. A lower consumed-slot metric alone cannot meet this requirement.

`minimum_reduction` is a nonnegative decimal-string threshold, default `"0"`, in the declared currency. Once all gates are met, the reviewed normalized net-cost difference is compared against that threshold. Equality passes. The attribution remains counterfactual, not a certified realized saving. A complete review may legitimately find no reduction or an increase.

## Preventing duplicate claims

`claims` is an explicit registry of up to 1000 prior claims, each with `id`, `scope`, `start`, `end` and `evidence_ids`. `claims_complete` must attest that the relevant registry is complete before attribution can pass. An empty list with completeness false does not establish absence of overlap.

The current claim's interval is the candidate period, and its evidence set contains both billing periods. The engine rejects aggregation when a claim ID is reused, billing evidence is shared, or half-open claim windows intersect on the same scope. Shared baseline billing evidence is conservatively treated as reuse even across different candidate periods. Adjacent windows do not overlap. Conflicts within the supplied registry also block aggregation.

Every registry conflict is counted. Only the first 100 pairs are displayed, with an explicit truncation flag. No portfolio total is calculated. Scope aliases, incomplete registries or newly invented IDs for reused billing rows cannot be detected independently, so stable identifiers and honest completeness are mandatory evidence-producer responsibilities.

## Results and testing

Exit 0 means the supplied evidence supports a reviewed counterfactual at or above the configured threshold. Exit 1 means a conflict, failed bound verification or below-threshold reviewed result. Exit 3 means attribution is unsupported. Exit 2 means malformed input. An estimate-only report normally exits 3 while still exposing the estimate.

The report contains pricing interpretation, all calculation values, attribution reasons, conflict information, an aggregation eligibility flag, source input, input digest and limitations. Schema version is `financial-0.1`. Keep sensitive billing input and reports outside public repositories. Identical inputs reproduce identical report bytes.

Synthetic tests independently check 2 TiB at a rate of 5 equals 10, capacity of 100 billed slot hours at 0.04 equals 4, volume normalization, signed credits, threshold boundaries and duplicate claims. Failure tests cover missing references, stale pricing, mismatched scopes and currencies, incomplete billing, failed correctness, unsupported models and zero volumes. No real billing export has been accessed or validated for this feature.

For a later real-data validation, obtain explicit authorization for a small sanitized billing extract, its accounting basis, pricing validity and scope. Reconcile credits and late adjustments independently. Do not enable exports, query financial tables or change IAM merely to make the example pass. Existing project access is not authorization to read billing data.

## Sources and overlap

[BigQuery pricing](https://cloud.google.com/bigquery/pricing) explains on-demand and capacity pricing. [Cloud Billing export documentation](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery) describes exported usage and cost evidence. [Cloud Billing reports](https://docs.cloud.google.com/billing/docs/how-to/reports) already provide cost reporting. DataVouch evaluates explicitly supplied change-related evidence rather than replacing those reports or claiming novel billing capabilities.
