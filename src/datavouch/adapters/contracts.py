"""Version 1 collection contracts, independent of any provider SDK."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from datavouch.core.models import Metric, Observation, validate_observations

API_VERSION = "adapter-1"


class AdapterError(ValueError):
    """A safe collection boundary error."""


def bounded_text(value: object, maximum: int = 2048) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise AdapterError("Invalid bounded text")


def identifiers(values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple) or len(values) > 100:
        raise AdapterError("Expected an immutable collection of at most 100 IDs")
    for value in values:
        bounded_text(value)
    if len(set(values)) != len(values):
        raise AdapterError("Duplicate execution IDs")


@dataclass(frozen=True, slots=True)
class AdapterInfo:
    name: str
    version: str
    api_version: str
    config_version: str
    modes: tuple[str, ...]
    metrics: tuple[Metric, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", self.name):
            raise AdapterError("Invalid adapter name")
        if not isinstance(self.version, str) or not re.fullmatch(
            r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", self.version
        ):
            raise AdapterError("Expected a numeric major.minor.patch adapter version")
        bounded_text(self.api_version, 64)
        bounded_text(self.config_version, 64)
        if (
            not isinstance(self.modes, tuple)
            or not self.modes
            or any(mode not in ("fixture", "live") for mode in self.modes)
            or len(set(self.modes)) != len(self.modes)
        ):
            raise AdapterError("Declare unique supported collection modes")
        if (
            not isinstance(self.metrics, tuple)
            or not 1 <= len(self.metrics) <= 32
            or not all(isinstance(metric, Metric) for metric in self.metrics)
        ):
            raise AdapterError("Declare 1 to 32 immutable metrics")
        if len({m.name for m in self.metrics}) != len(self.metrics):
            raise AdapterError("Duplicate declared metric names")
        for metric in self.metrics:
            bounded_text(metric.name, 128)
            bounded_text(metric.unit, 128)


@dataclass(frozen=True, slots=True)
class Exclusion:
    execution_id: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        bounded_text(self.execution_id)
        if not isinstance(self.reasons, tuple) or not 1 <= len(self.reasons) <= 16:
            raise AdapterError("Declare bounded exclusion reasons")
        for reason in self.reasons:
            bounded_text(reason, 500)


@dataclass(frozen=True, slots=True)
class ObservationBatch:
    requested_ids: tuple[str, ...]
    observations: tuple[Observation, ...]
    missing_ids: tuple[str, ...]
    exclusions: tuple[Exclusion, ...]
    eligible: bool
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        identifiers(self.requested_ids)
        identifiers(self.missing_ids)
        if not self.requested_ids:
            raise AdapterError("At least one execution must be requested")
        validate_observations(self.observations)
        if not isinstance(self.exclusions, tuple) or not all(
            isinstance(item, Exclusion) for item in self.exclusions
        ):
            raise AdapterError("Expected immutable exclusions")
        observed = tuple(o.execution.id for o in self.observations)
        excluded = tuple(e.execution_id for e in self.exclusions)
        identifiers(observed)
        identifiers(excluded)
        accounted = observed + excluded + self.missing_ids
        if len(set(accounted)) != len(accounted) or set(accounted) != set(self.requested_ids):
            raise AdapterError("Every requested execution must appear in exactly one category")
        if any(
            not o.execution.successful or o.execution.cached or not o.measurements
            for o in self.observations
        ):
            raise AdapterError("Failed, cached or unmeasured executions must be excluded")
        if type(self.eligible) is not bool or (
            self.eligible and (not observed or excluded or self.missing_ids)
        ):
            raise AdapterError("Incomplete collections cannot be eligible")
        if not isinstance(self.notes, tuple) or not 1 <= len(self.notes) <= 16:
            raise AdapterError("Declare bounded collection limitations")
        for note in self.notes:
            bounded_text(note, 500)


class Adapter(Protocol):
    @property
    def info(self) -> AdapterInfo: ...

    def validate_config(self, config: object) -> None:
        """Validate without authentication, network access or mutations."""
        ...

    def collect(self, config: object, *, fixture: Path | None, live: bool) -> ObservationBatch:
        """Collect explicitly selected evidence; live access requires caller authorization."""
        ...
