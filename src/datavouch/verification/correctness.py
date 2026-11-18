"""Evaluate independently supplied evidence, never execute assertions or collect output data."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from datavouch.core.models import Experiment, Status, nonempty, nonnegative


def instant(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Expected an ISO timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Timestamp must specify a time zone")
    return parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    status: Status
    reason: str


@dataclass(frozen=True, slots=True)
class CorrectnessEvidence:
    name: str
    kind: str
    reference: str | None
    experiment_id: str
    execution_ids: tuple[str, ...]
    expected: str | bool | float | tuple[str, ...] | None
    observed: str | bool | float | tuple[str, ...] | None
    method: str | None = None
    as_of: str | None = None

    def __post_init__(self) -> None:
        nonempty(self.name, "check name")
        nonempty(self.experiment_id, "experiment id")
        if self.kind not in ("assertion", "schema", "sha256", "freshness", "row_count"):
            raise ValueError("Unsupported correctness check kind")
        if self.reference is not None:
            nonempty(self.reference, "evidence reference")
        if not isinstance(self.execution_ids, tuple):
            raise ValueError("Execution IDs must be immutable")
        for execution_id in self.execution_ids:
            nonempty(execution_id, "execution id")
        if len(set(self.execution_ids)) != len(self.execution_ids):
            raise ValueError("Duplicate evidence execution IDs")
        if self.method is not None:
            nonempty(self.method, "method")
        if self.as_of is not None:
            instant(self.as_of)
        for value in (self.expected, self.observed):
            if value is None:
                continue
            if self.kind == "assertion" and type(value) is not bool:
                raise ValueError("Assertions require boolean outcomes")
            if self.kind == "schema":
                if not isinstance(value, tuple) or not value:
                    raise ValueError("Schema requires nonempty ordered field descriptors")
                for field in value:
                    nonempty(field, "schema field descriptor")
                if len(set(value)) != len(value):
                    raise ValueError("Duplicate schema field descriptors")
            if self.kind == "sha256" and (
                not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)
            ):
                raise ValueError("Expected a lowercase SHA256 digest")
            if self.kind == "row_count":
                if type(value) is not int or value < 0:
                    raise ValueError("Row counts must be nonnegative integers")
        if self.kind == "freshness":
            if self.expected is not None:
                nonnegative(self.expected, "maximum age seconds")  # type: ignore[arg-type]
            if self.observed is not None:
                instant(self.observed)


def decode_check(data: dict[str, Any]) -> CorrectnessEvidence:
    required = {"name", "kind", "experiment_id", "execution_ids"}
    optional = {"reference", "expected", "observed", "method", "as_of"}
    if not required <= data.keys() or data.keys() - required - optional:
        raise ValueError("Invalid correctness evidence fields")
    if not isinstance(data["execution_ids"], list):
        raise ValueError("Expected execution ID array")
    values = dict(data)
    values["execution_ids"] = tuple(data["execution_ids"])
    values.setdefault("reference", None)
    for key in ("expected", "observed"):
        value = values.get(key)
        values[key] = tuple(value) if isinstance(value, list) else value
    return CorrectnessEvidence(**values)


def evaluate(check: CorrectnessEvidence, experiment: Experiment) -> CheckResult:
    reason = None
    if check.experiment_id != experiment.id or set(check.execution_ids) != {
        o.execution.id for o in experiment.candidate
    }:
        reason = "Evidence does not cover this experiment's candidate executions"
    elif (
        not experiment.candidate
        or not check.reference
        or check.expected is None
        or check.observed is None
    ):
        reason = "Required independent evidence is missing"
    elif check.kind == "row_count":
        reason = "Row counts alone do not establish correctness"
    elif check.kind == "sha256" and not check.method:
        reason = "Checksum requires a shared canonicalization and coverage contract"
    elif check.kind == "freshness" and check.as_of is None:
        reason = "Freshness requires an explicit evaluation time"
    if reason:
        return CheckResult(check.name, Status.UNKNOWN, reason)
    if check.kind == "freshness":
        age = (instant(check.as_of) - instant(check.observed)).total_seconds()
        if age < 0:
            return CheckResult(check.name, Status.UNKNOWN, "Freshness timestamp is in the future")
        passed = age <= float(check.expected)  # type: ignore[arg-type]
    else:
        passed = check.expected == check.observed
    return CheckResult(
        check.name,
        Status.PASS if passed else Status.FAIL,
        "Configured correctness check passed" if passed else "Configured correctness check failed",
    )
