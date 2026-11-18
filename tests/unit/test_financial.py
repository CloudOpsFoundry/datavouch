import copy
import json
from decimal import getcontext
from fractions import Fraction
from pathlib import Path

import pytest

from datavouch.core.models import Status
from datavouch.financial.evaluation import assess, money
from datavouch.financial.models import Claim, amount, overlap

EXAMPLE = Path(__file__).resolve().parents[2] / "examples/financial/reviewed.json"


@pytest.fixture
def document():
    return json.loads(EXAMPLE.read_text())


def test_independently_calculated_on_demand_and_net_spend(document):
    result = assess(document)
    assert result["status"] == Status.PASS
    estimate = result["estimated_costs"]
    assert estimate["classification"] == "estimated"
    assert estimate["values"]["baseline_cost"] == "10.000000000000"
    assert estimate["values"]["candidate_cost"] == "5.000000000000"
    assert estimate["values"]["raw_difference"] == "5.000000000000"
    assert estimate["values"]["normalized_classification"] == "counterfactual"
    assert result["observed_spending"]["classification"] == "measured"
    assert result["observed_spending"]["values"]["raw_difference"] == "4.000000000000"
    assert result["attribution"]["classification"] == "counterfactual"
    assert result["attribution"]["normalized_difference"] == "4.000000000000"
    assert result["consumed_slot_ms_difference"] == 1000
    assert result["eligible_for_aggregation"]
    assert result == assess(copy.deepcopy(document))


def test_volume_normalization_is_not_observed_savings(document):
    document.pop("verification")
    document["candidate"]["execution_ids"] = ["a0", "a1", "a2", "a3", "a4", "a5"]
    result = assess(document)
    values = result["observed_spending"]["values"]
    assert values["raw_difference"] == "4.000000000000"
    assert values["baseline_cost_at_candidate_volume"] == "16.000000000000"
    assert values["normalized_difference"] == "12.000000000000"
    assert values["normalized_classification"] == "counterfactual"
    assert result["status"] == Status.UNKNOWN
    assert any("normalization" in r for r in result["attribution"]["reasons"])


def test_capacity_consumption_is_not_billed_capacity(document):
    document["pricing"].update(model="capacity", rate="0.04")
    result = assess(document)
    assert result["estimated_costs"]["classification"] == "unsupported"
    assert result["status"] == Status.UNKNOWN
    assert result["consumed_slot_ms_difference"] == 1000
    document["baseline"]["billed_slot_hours"] = "100"
    document["candidate"]["billed_slot_hours"] = "80"
    result = assess(document)
    assert result["estimated_costs"]["values"]["raw_difference"] == "0.800000000000"
    assert result["status"] == Status.UNKNOWN
    document["review"]["capacity_change_reference"] = "synthetic-reservation-change-review"
    assert assess(document)["status"] == Status.PASS


@pytest.mark.parametrize("minimum,status", [("4", Status.PASS), ("4.000000000001", Status.FAIL)])
def test_threshold_boundaries(document, minimum, status):
    document["minimum_reduction"] = minimum
    assert assess(document)["status"] == status


def test_increased_cost_fails(document):
    document["billing"]["candidate"]["net_cost"] = "9"
    result = assess(document)
    assert result["status"] == Status.FAIL
    assert result["attribution"]["normalized_difference"] == "-1.000000000000"
    assert not result["eligible_for_aggregation"]


def test_signed_net_credits(document):
    document["billing"]["baseline"]["net_cost"] = "-1.20"
    document["billing"]["candidate"]["net_cost"] = "-2.30"
    assert assess(document)["observed_spending"]["values"]["raw_difference"] == "1.100000000000"


def test_no_baseline_usage_division_by_zero(document):
    document["baseline"]["execution_ids"] = []
    result = assess(document)
    assert result["status"] == Status.UNKNOWN
    assert result["estimated_costs"]["values"]["normalized_difference"] is None
    assert result["observed_spending"]["values"]["normalized_difference"] is None


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.pop("billing"),
        lambda d: d.pop("verification"),
        lambda d: d.pop("review"),
        lambda d: d.update(claims_complete=False),
        lambda d: d["pricing"].update(model="unknown"),
        lambda d: d["billing"]["candidate"].update(complete=False),
        lambda d: d["billing"]["candidate"].update(evidence_ids=[]),
        lambda d: d["billing"]["candidate"].update(currency="EUR"),
        lambda d: d["billing"]["candidate"].update(scope="other"),
        lambda d: d["billing"]["candidate"].update(end="2026-11-14T00:00:00Z"),
        lambda d: d["review"].update(experiment_id="unrelated"),
        lambda d: d["review"].update(scope="other"),
        lambda d: d["review"].update(method="unsupported"),
        lambda d: d["review"].update(confounders_addressed=False),
        lambda d: d["candidate"].update(execution_ids=["unrelated"]),
        lambda d: d["verification"]["assurance"]["evidence"][0].update(observed=None),
        lambda d: d["verification"]["assurance"].pop("windows"),
    ],
)
def test_inadequate_attribution_is_unknown(document, change):
    change(document)
    result = assess(document)
    assert result["status"] == Status.UNKNOWN
    assert result["attribution"]["classification"] == "unsupported"
    assert not result["eligible_for_aggregation"]


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["pricing"].pop("rate"),
        lambda d: d["pricing"].pop("reference"),
        lambda d: d["pricing"].pop("valid_from"),
        lambda d: d["pricing"].pop("valid_to"),
        lambda d: d["pricing"].update(valid_to="2026-11-11T00:00:00Z"),
        lambda d: d["baseline"].pop("reference"),
        lambda d: d["baseline"].pop("billed_bytes"),
    ],
)
def test_missing_pricing_evidence_never_fabricates_estimates(document, change):
    change(document)
    assert assess(document)["estimated_costs"]["classification"] == "unsupported"


def test_failed_correctness_blocks_financial_attribution(document):
    document["verification"]["assurance"]["evidence"][0]["observed"] = False
    result = assess(document)
    assert result["status"] == Status.FAIL
    assert result["attribution"]["normalized_difference"] is None


def claim(document, **updates):
    data = {
        "id": "previous",
        "scope": document["scope"],
        "start": document["candidate"]["start"],
        "end": document["candidate"]["end"],
        "evidence_ids": [],
    }
    data.update(updates)
    return data


@pytest.mark.parametrize(
    "updates",
    [
        {},
        {"id": "synthetic-claim-1", "scope": "other"},
        {"scope": "other", "evidence_ids": ["synthetic-billing-baseline"]},
    ],
)
def test_overlap_blocks_aggregation(document, updates):
    document["claims"] = [claim(document, **updates)]
    result = assess(document)
    assert result["status"] == Status.FAIL
    assert result["overlapping_claim_ids"]
    assert result["attribution"]["normalized_difference"] is None
    assert not result["eligible_for_aggregation"]


def test_adjacent_scopes_and_registry_internal_conflicts(document):
    document["claims"] = [
        claim(document, start="2026-11-11T00:00:00Z", end=document["candidate"]["start"])
    ]
    assert assess(document)["status"] == Status.PASS
    document["claims"] = [
        claim(document, id="old-a", scope="other"),
        claim(document, id="old-b", scope="other"),
    ]
    result = assess(document)
    assert result["status"] == Status.FAIL
    assert result["registry_conflicts"] == [("old-a", "old-b")]
    a = Claim.decode(document["claims"][0])
    b = Claim.decode(claim(document, id="different", scope="distinct"))
    assert not overlap(a, b)


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(extra=True),
        lambda d: d.update(claims_complete=1),
        lambda d: d["baseline"].update(start=d["baseline"]["end"]),
        lambda d: d["candidate"].update(start=d["baseline"]["start"]),
        lambda d: d["candidate"].update(execution_ids=["b0"]),
        lambda d: d["candidate"].update(execution_ids=["a0", "a0"]),
        lambda d: d["candidate"].update(execution_ids="a0"),
        lambda d: d["candidate"].update(execution_ids=[""]),
        lambda d: d["candidate"].update(execution_ids=[str(i) for i in range(1001)]),
        lambda d: d["candidate"].update(billed_bytes=True),
        lambda d: d["candidate"].update(consumed_slot_ms=-1),
        lambda d: d["candidate"].update(billed_bytes=2**63),
        lambda d: d["pricing"].update(model="free_magic"),
        lambda d: d["pricing"].update(currency="usd"),
        lambda d: d["pricing"].update(valid_from=d["pricing"]["valid_to"]),
        lambda d: d["billing"]["candidate"].update(evidence_ids=["synthetic-billing-baseline"]),
        lambda d: d["billing"]["candidate"].update(start=d["billing"]["candidate"]["end"]),
        lambda d: d["billing"]["candidate"].update(complete=1),
        lambda d: d["review"].update(confounders_addressed="yes"),
        lambda d: d.update(claims={}),
        lambda d: d.update(claims=[{}] * 1001),
        lambda d: d.update(claims=[claim(d), claim(d)]),
        lambda d: d.update(claims=[claim(d, start=d["candidate"]["end"])]),
    ],
)
def test_malformed_evidence_is_rejected(document, change):
    change(document)
    with pytest.raises(ValueError):
        assess(document)


@pytest.mark.parametrize(
    "value", [1, 1.1, True, None, "NaN", "Infinity", "1e10", "1.0000000000001", "-1", "1" * 19]
)
def test_invalid_money(value):
    with pytest.raises(ValueError):
        amount(value)


def test_exact_arithmetic_and_decimal_context_independence(document):
    assert amount("0.1") + amount("0.2") == amount("0.3")
    assert money(Fraction(1, 3)) == "0.333333333333"
    original = getcontext().prec
    expected = assess(document)
    try:
        getcontext().prec = 2
        assert assess(document) == expected
    finally:
        getcontext().prec = original


def test_window_binding_and_supported_volume_review(document):
    document["candidate"]["end"] = "2026-11-14T00:00:00Z"
    document["billing"]["candidate"]["end"] = document["candidate"]["end"]
    document["review"]["normalization_reference"] = "duration adjustment review"
    assert assess(document)["status"] == Status.UNKNOWN


def test_conflict_diagnostics_are_bounded_without_hiding_count(document):
    document["claims"] = [claim(document, id=f"claim-{i:03}", scope="other") for i in range(30)]
    result = assess(document)
    assert result["registry_conflict_count"] == 435  # 30 * 29 / 2
    assert len(result["registry_conflicts"]) == 100
    assert result["registry_conflicts_truncated"]
    assert result["status"] == Status.FAIL


def test_reviewed_normalization_requires_matching_verification(document):
    document["candidate"]["execution_ids"] = document["candidate"]["execution_ids"][:2]
    document["verification"]["comparison"]["experiment"]["candidate"] = document["verification"][
        "comparison"
    ]["experiment"]["candidate"][:2]
    document["verification"]["comparison"]["policy"]["minimum_samples"] = 2
    document["verification"]["assurance"]["completed_at"].pop("a2")
    document["verification"]["assurance"]["started_at"].pop("a2")
    for evidence in document["verification"]["assurance"]["evidence"]:
        evidence["execution_ids"] = ["a0", "a1"]
    assert assess(document)["status"] == Status.UNKNOWN
    document["review"]["normalization_reference"] = "synthetic linear cost per execution review"
    result = assess(document)
    assert result["status"] == Status.PASS
    assert result["attribution"]["normalized_difference"] == "1.333333333333"  # 8 * 2 / 3 - 4


def test_zero_price_and_missing_slot_usage(document):
    document["pricing"]["rate"] = "0"
    document["baseline"].pop("consumed_slot_ms")
    result = assess(document)
    assert result["estimated_costs"]["values"]["raw_difference"] == "0.000000000000"
    assert result["consumed_slot_ms_difference"] is None


def test_distinct_registry_scopes_do_not_create_false_conflicts(document):
    document["claims"] = [
        claim(document, id="a", scope="other-a"),
        claim(document, id="b", scope="other-b"),
    ]
    result = assess(document)
    assert result["registry_conflict_count"] == 0
    assert result["registry_conflicts"] == []
    assert result["status"] == Status.PASS


def test_display_ignores_callers_decimal_traps():
    from decimal import Inexact, localcontext

    with localcontext() as context:
        context.traps[Inexact] = True
        assert money(Fraction(1, 3)) == "0.333333333333"
