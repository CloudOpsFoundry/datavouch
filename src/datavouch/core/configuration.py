"""Strict JSON input decoding for offline experiments."""

import json
from pathlib import Path
from typing import Any

from datavouch.core.models import (
    Baseline,
    Change,
    Direction,
    Evidence,
    Execution,
    Experiment,
    Measurement,
    Metric,
    Observation,
    Policy,
    Workload,
)

MAX_INPUT_BYTES = 5_000_000


def _object(value: Any, required: set[str], optional: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or not required <= value.keys():
        raise ValueError(f"Expected an object with fields: {', '.join(sorted(required))}")
    if value.keys() - required - (optional or set()):
        raise ValueError("Unexpected configuration fields")
    return value


def _metric(value: Any) -> Metric:
    data = _object(value, {"name", "unit", "direction"})
    return Metric(data["name"], data["unit"], Direction(data["direction"]))


def _observations(value: Any) -> tuple[Observation, ...]:
    if not isinstance(value, list):
        raise ValueError("Expected an observation array")
    result = []
    for item in value:
        data = _object(
            item, {"workload", "execution", "measurements"}, {"input_units", "input_unit"}
        )
        workload = Workload(**_object(data["workload"], {"id", "environment", "input_snapshot"}))
        execution = Execution(**_object(data["execution"], {"id"}, {"successful", "cached"}))
        if not isinstance(data["measurements"], list):
            raise ValueError("Expected a measurement array")
        measurements = []
        for item in data["measurements"]:
            measurement = _object(item, {"metric", "value"})
            measurements.append(Measurement(_metric(measurement["metric"]), measurement["value"]))
        result.append(
            Observation(
                workload,
                execution,
                tuple(measurements),
                data.get("input_units"),
                data.get("input_unit"),
            )
        )
    return tuple(result)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("Duplicate JSON object key")
        data[key] = value
    return data


def load(path: Path) -> tuple[Experiment, Policy]:
    """Load bounded input. Reject ambiguous fields and malformed observations."""
    return decode(read_json(path))


def read_json(path: Path) -> Any:
    """Read a bounded JSON document without duplicate object keys."""
    with path.open("rb") as source:
        raw = source.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("Input exceeds the 5 MB limit")
    return json.loads(raw, object_pairs_hook=_unique_object)


def decode(value: Any) -> tuple[Experiment, Policy]:
    """Decode a comparison object using the shared model validation."""
    data = _object(value, {"experiment", "policy"})
    exp = _object(data["experiment"], {"id", "baseline", "candidate", "change"}, {"comparability"})
    evidence = exp.get("comparability")
    baseline = _object(exp["baseline"], {"observations"})
    experiment = Experiment(
        exp["id"],
        Baseline(_observations(baseline["observations"])),
        _observations(exp["candidate"]),
        Change(**_object(exp["change"], {"id", "description"})),
        None if evidence is None else Evidence(**_object(evidence, {"reference", "statement"})),
    )
    policy = _object(
        data["policy"], {"metric"}, {"max_regression_percent", "minimum_samples", "normalize"}
    )
    return experiment, Policy(
        _metric(policy["metric"]),
        policy.get("max_regression_percent", 0.0),
        policy.get("minimum_samples", 3),
        policy.get("normalize", False),
    )
