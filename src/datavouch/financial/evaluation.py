"""Auditable financial calculations. Efficiency is never assumed to be invoice savings."""

import hashlib
import json
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from fractions import Fraction
from typing import Any

from datavouch.core.configuration import _object
from datavouch.core.models import Status, nonempty
from datavouch.financial.models import Billing, Claim, Pricing, Usage, amount, overlap
from datavouch.verification.correctness import instant
from datavouch.verification.evaluation import verify


def money(value: Fraction) -> str:
    """Render amounts to 12 decimal places without changing threshold comparison precision."""
    with localcontext(Context(prec=100, rounding=ROUND_HALF_EVEN)):
        result = (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
            Decimal("0.000000000001"), rounding=ROUND_HALF_EVEN
        )
        return format(abs(result) if result == 0 else result, "f")


def cost(usage: Usage, pricing: Pricing) -> Fraction | None:
    if not usage.reference or not pricing.reference or pricing.rate is None:
        return None
    if pricing.valid_from is None or pricing.valid_to is None:
        return None
    if (
        not instant(pricing.valid_from)
        <= instant(usage.start)
        < instant(usage.end)
        <= instant(pricing.valid_to)
    ):
        return None
    rate = amount(pricing.rate)
    if pricing.model == "on_demand" and usage.billed_bytes is not None:
        return Fraction(usage.billed_bytes, 2**40) * rate
    if pricing.model == "capacity" and usage.billed_slot_hours is not None:
        return amount(usage.billed_slot_hours) * rate
    return None


def differences(
    before: Fraction, after: Fraction, baseline: Usage, candidate: Usage
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "baseline_cost": money(before),
        "candidate_cost": money(after),
        "raw_difference": money(before - after),
        "baseline_cost_at_candidate_volume": None,
        "normalized_difference": None,
        "normalized_classification": "unsupported",
    }
    if baseline.execution_ids and candidate.execution_ids:
        counterfactual = before * Fraction(
            len(candidate.execution_ids), len(baseline.execution_ids)
        )
        result.update(
            normalized_classification="counterfactual",
            baseline_cost_at_candidate_volume=money(counterfactual),
            normalized_difference=money(counterfactual - after),
        )
    return result


def registry_overlaps(claims: list[Claim]) -> tuple[int, list[tuple[str, str]]]:
    """Count every conflict, but bound diagnostic output to 100 pairs."""
    prepared = [
        (c, instant(c.start), instant(c.end), frozenset(c.evidence_ids))
        for c in sorted(claims, key=lambda c: c.id)
    ]
    count = 0
    preview: list[tuple[str, str]] = []
    for index, (left, start, end, evidence) in enumerate(prepared):
        for right, other_start, other_end, other_evidence in prepared[index + 1 :]:
            if not evidence.isdisjoint(other_evidence) or (
                left.scope == right.scope and start < other_end and other_start < end
            ):
                count += 1
                if len(preview) < 100:
                    preview.append((left.id, right.id))
    return count, preview


def assess(document: Any) -> dict[str, Any]:
    root = _object(
        document,
        {
            "experiment_id",
            "claim_id",
            "scope",
            "baseline",
            "candidate",
            "pricing",
            "claims",
            "claims_complete",
        },
        {"billing", "review", "verification", "minimum_reduction"},
    )
    for key in ("experiment_id", "claim_id", "scope"):
        nonempty(root[key], key)
    if type(root["claims_complete"]) is not bool:
        raise ValueError("Claims registry completeness must be a boolean")
    minimum = amount(root.get("minimum_reduction", "0"))
    baseline, candidate = Usage.decode(root["baseline"]), Usage.decode(root["candidate"])
    if instant(baseline.end) > instant(candidate.start):
        raise ValueError("Baseline and candidate usage windows overlap")
    if set(baseline.execution_ids) & set(candidate.execution_ids):
        raise ValueError("Baseline and candidate execution IDs overlap")
    pricing = Pricing.decode(root["pricing"])
    if not isinstance(root["claims"], list) or len(root["claims"]) > 1000:
        raise ValueError("Expected a registry with at most 1000 claims")
    claims = [Claim.decode(c) for c in root["claims"]]
    if len({c.id for c in claims}) != len(claims):
        raise ValueError("Duplicate registry claim IDs")
    before_cost, after_cost = cost(baseline, pricing), cost(candidate, pricing)
    estimates = None
    if before_cost is not None and after_cost is not None:
        estimates = differences(before_cost, after_cost, baseline, candidate)
    billing = root.get("billing")
    billed_before = billed_after = None
    observed = None
    billing_reason = "Billing evidence is missing"
    if billing is not None:
        pair = _object(billing, {"baseline", "candidate"})
        billed_before, billed_after = (
            Billing.decode(pair["baseline"]),
            Billing.decode(pair["candidate"]),
        )
        if set(billed_before.evidence_ids) & set(billed_after.evidence_ids):
            raise ValueError("Baseline and candidate reuse billing evidence")
        complete = all(b.complete and b.evidence_ids for b in (billed_before, billed_after))
        matched = all(
            instant(b.start) == instant(u.start)
            and instant(b.end) == instant(u.end)
            and b.currency == pricing.currency
            and b.scope == root["scope"]
            for b, u in ((billed_before, baseline), (billed_after, candidate))
        )
        if complete and matched:
            observed = differences(
                amount(billed_before.net_cost, signed=True),
                amount(billed_after.net_cost, signed=True),
                baseline,
                candidate,
            )
            billing_reason = "Complete supplied net-cost periods match scope windows and currency"
        else:
            billing_reason = "Billing periods, currency or completeness do not support comparison"
    evidence_ids = tuple(
        sorted(
            set(
                (() if billed_before is None else billed_before.evidence_ids)
                + (() if billed_after is None else billed_after.evidence_ids)
            )
        )
    )
    current = Claim(root["claim_id"], root["scope"], candidate.start, candidate.end, evidence_ids)
    conflicts = sorted(c.id for c in claims if overlap(current, c))
    registry_count, registry_conflicts = registry_overlaps(claims)
    review = root.get("review")
    review_ok = False
    normalization_ok = len(baseline.execution_ids) == len(candidate.execution_ids) and instant(
        baseline.end
    ) - instant(baseline.start) == instant(candidate.end) - instant(candidate.start)
    if review is not None:
        record = _object(
            review,
            {"experiment_id", "scope", "reference", "method", "confounders_addressed"},
            {"normalization_reference", "capacity_change_reference"},
        )
        for key in ("experiment_id", "scope", "reference", "method"):
            nonempty(record[key], key)
        if type(record["confounders_addressed"]) is not bool:
            raise ValueError("Confounder review must be a boolean")
        for key in ("normalization_reference", "capacity_change_reference"):
            if record.get(key) is not None:
                nonempty(record[key], key)
        review_ok = (
            record["experiment_id"] == root["experiment_id"]
            and record["scope"] == root["scope"]
            and record["method"] in ("controlled_experiment", "independent_review")
            and record["confounders_addressed"]
        )
        if pricing.model == "capacity" and not record.get("capacity_change_reference"):
            review_ok = False
        normalization_ok = normalization_ok or bool(record.get("normalization_reference"))
    verification_status = Status.UNKNOWN
    binding = False
    if root.get("verification") is not None:
        verification = verify(root["verification"])
        verification_status = Status(verification["overall_status"])
        exp = verification["performance"]["experiment"]
        windows = root["verification"]["assurance"].get("windows")
        window_binding = windows is not None and all(
            instant(windows[key]) == instant(value)
            for key, value in (
                ("baseline_start", baseline.start),
                ("baseline_end", baseline.end),
                ("candidate_start", candidate.start),
                ("candidate_end", candidate.end),
            )
        )
        binding = (
            window_binding
            and exp["id"] == root["experiment_id"]
            and {o["execution"]["id"] for o in exp["baseline"]["observations"]}
            == set(baseline.execution_ids)
            and {o["execution"]["id"] for o in exp["candidate"]} == set(candidate.execution_ids)
        )
    reasons = []
    if pricing.model == "unknown":
        reasons.append("Pricing model is unsupported")
    if observed is None:
        reasons.append(billing_reason)
    if not review_ok:
        reasons.append("Independent attribution review or capacity change evidence is insufficient")
    if not normalization_ok:
        reasons.append("Unequal execution volume or period duration needs a normalization contract")
    if not baseline.execution_ids or not candidate.execution_ids:
        reasons.append("Zero execution volume cannot support normalized attribution")
    if not root["claims_complete"]:
        reasons.append("Claims registry coverage is incomplete")
    if not binding or verification_status != Status.PASS:
        reasons.append(
            "Passing verification is missing or not bound to this experiment's executions"
        )
    status = Status.UNKNOWN
    attributed = None
    if conflicts or registry_count:
        status = Status.FAIL
        reasons.append("Overlapping or reused claims cannot be aggregated")
    elif binding and verification_status == Status.FAIL:
        status = Status.FAIL
    elif not reasons and billed_before is not None and billed_after is not None:
        counterfactual = amount(billed_before.net_cost, signed=True) * Fraction(
            len(candidate.execution_ids), len(baseline.execution_ids)
        )
        impact = counterfactual - amount(billed_after.net_cost, signed=True)
        attributed = money(impact)
        status = Status.PASS if impact >= minimum else Status.FAIL
        reasons.append(
            "Reviewed counterfactual meets threshold"
            if status == Status.PASS
            else "Reviewed counterfactual falls below threshold"
        )
    digest = hashlib.sha256(
        json.dumps(document, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    return {
        "schema_version": "financial-0.1",
        "status": status,
        "currency": pricing.currency,
        "pricing_model": pricing.model,
        "estimated_costs": {
            "classification": "estimated" if estimates is not None else "unsupported",
            "values": estimates,
        },
        "observed_spending": {
            "classification": "measured" if observed is not None else "unsupported",
            "values": observed,
            "reason": billing_reason,
        },
        "attribution": {
            "classification": "counterfactual" if attributed is not None else "unsupported",
            "normalized_difference": attributed,
            "reasons": reasons,
        },
        "overlapping_claim_ids": conflicts,
        "registry_conflicts": registry_conflicts,
        "registry_conflict_count": registry_count,
        "registry_conflicts_truncated": registry_count > len(registry_conflicts),
        "eligible_for_aggregation": status == Status.PASS,
        "consumed_slot_ms_difference": None
        if baseline.consumed_slot_ms is None or candidate.consumed_slot_ms is None
        else baseline.consumed_slot_ms - candidate.consumed_slot_ms,
        "input_sha256": digest,
        "source": document,
        "limitations": [
            "Measured means supplied billing amounts, not independently reconciled invoices.",
            "Normalized differences are counterfactual, not realized monetary savings.",
            "References, billing completeness, scope identity and reviews are caller attestations.",
            "Pricing is supplied. Estimates exclude unspecified discounts, credits and free tiers.",
            "Consumed slot milliseconds are efficiency evidence, not purchased capacity charges.",
            "Amounts display 12 fractional digits; thresholds use exact rational values.",
        ],
    }
