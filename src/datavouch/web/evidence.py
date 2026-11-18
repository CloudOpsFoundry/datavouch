"""Decode independently supplied correctness evidence without executing expressions."""

import hashlib
import json
from typing import Any

from datavouch.verification.correctness import decode_check

METRICS = {
    "runtime": ("Runtime", "ms"),
    "slot_time": ("Slot consumption", "slot_ms"),
    "processed_bytes": ("Processed bytes", "bytes"),
    "billed_bytes": ("Billed bytes", "bytes"),
}


def strict_json(value: str) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("Duplicate JSON fields are not allowed")
            result[key] = item
        return result

    return json.loads(value, object_pairs_hook=unique)


def check_key(name: str) -> str:
    return "check_" + hashlib.sha256(name.encode()).hexdigest()[:16]


def supplied_evidence(values: dict[str, str], plan: dict[str, Any]) -> list[dict[str, Any]]:
    checks = plan["assurance"]["required_checks"]
    execution_ids = [
        f"{plan['candidate']['project']}/{plan['candidate']['location']}/{job}"
        for job in plan["candidate"]["job_ids"]
    ]
    evidence = strict_json(values.get("evidence_json", "") or "[]")
    if not isinstance(evidence, list) or len(evidence) > 100:
        raise ValueError("Evidence JSON must be an array of at most 100 checks")
    for name in checks:
        key = check_key(name)
        outcome = values.get(key + "_outcome", "")
        if outcome not in {"", "true", "false"}:
            raise ValueError("Select a supported correctness outcome")
        if outcome:
            reference = values.get(key + "_reference", "").strip()
            if not reference:
                raise ValueError(f"{name}: supply an independent evidence reference")
            evidence.append(
                {
                    "name": name,
                    "kind": "assertion",
                    "expected": True,
                    "observed": outcome == "true",
                    "reference": reference,
                    "experiment_id": plan["id"],
                    "execution_ids": execution_ids,
                }
            )
    if evidence and values.get("evidence_confirmed") != "yes":
        raise ValueError("Confirm that supplied evidence covers these candidate executions")
    seen: set[str] = set()
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("Each evidence record must be an object")
        check = decode_check(item)
        if check.name not in checks or check.name in seen:
            raise ValueError("Evidence names must be required and unique")
        if check.experiment_id != plan["id"] or set(check.execution_ids) != set(execution_ids):
            raise ValueError(
                "Evidence must cover this experiment and exactly its candidate job IDs"
            )
        seen.add(check.name)
    return evidence
