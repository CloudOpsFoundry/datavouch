"""Financial assessment bound to a saved experiment, without billing API access."""

from typing import Any

from datavouch.financial.evaluation import assess
from datavouch.web.evidence import strict_json
from datavouch.web.temporal import picker_timestamp


def financial_document(values: dict[str, str], verification: dict[str, Any]) -> dict[str, Any]:
    experiment = verification["comparison"]["experiment"]
    windows = verification["assurance"]["windows"]
    cohorts = {
        "baseline": experiment["baseline"]["observations"],
        "candidate": experiment["candidate"],
    }
    if values.get("financial_json", "").strip():
        document = strict_json(values["financial_json"])
        if not isinstance(document, dict) or document.get("experiment_id") != experiment["id"]:
            raise ValueError("Financial evidence must identify this experiment")
        if "verification" in document and document["verification"] != verification:
            raise ValueError("Financial evidence contains a different verification input")
    else:
        document = {
            "experiment_id": experiment["id"],
            "claim_id": experiment["id"] + "-financial",
            "scope": values.get("scope", ""),
            "pricing": {
                "model": values.get("pricing_model", ""),
                "currency": values.get("currency", ""),
                "rate": values.get("rate") or None,
                "reference": values.get("pricing_reference") or None,
                "valid_from": picker_timestamp(values["valid_from"], "Price effective start")
                if values.get("valid_from")
                else None,
                "valid_to": picker_timestamp(values["valid_to"], "Price effective end")
                if values.get("valid_to")
                else None,
            },
            "claims": [],
            "claims_complete": False,
        }
        for side, observations in cohorts.items():
            usage: dict[str, Any] = {
                "start": windows[side + "_start"],
                "end": windows[side + "_end"],
                "execution_ids": [o["execution"]["id"] for o in observations],
                "reference": "saved-verification/" + experiment["id"] + "/" + side,
            }
            for metric, field in [
                ("billed_bytes", "billed_bytes"),
                ("slot_time", "consumed_slot_ms"),
            ]:
                numbers = [
                    next(
                        (m["value"] for m in o["measurements"] if m["metric"]["name"] == metric),
                        None,
                    )
                    for o in observations
                ]
                usage[field] = (
                    sum(numbers) if numbers and all(type(n) is int for n in numbers) else None
                )
            usage["billed_slot_hours"] = values.get(side + "_billed_slot_hours") or None
            document[side] = usage
    for side, observations in cohorts.items():
        supplied = document.get(side)
        if (
            not isinstance(supplied, dict)
            or supplied.get("start") != windows[side + "_start"]
            or supplied.get("end") != windows[side + "_end"]
            or set(supplied.get("execution_ids", []))
            != {o["execution"]["id"] for o in observations}
        ):
            raise ValueError("Financial windows and execution IDs must match the saved experiment")
    document["verification"] = verification
    assess(document)
    return document
