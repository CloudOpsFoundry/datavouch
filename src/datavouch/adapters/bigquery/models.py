"""Validated collection scope and immutable provider evidence."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from datavouch.core.models import Observation, Workload


class CollectionError(ValueError):
    """Safe error suitable for display without provider response details."""


def timestamp(value: object) -> datetime:
    """Require an explicit time zone and normalize to UTC."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise CollectionError("Expected a timestamp with a time zone")
    return value.astimezone(UTC)


def validate_project(project: str) -> None:
    if not isinstance(project, str) or not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project):
        raise CollectionError("Expected a standard Google Cloud project ID")


def validate_location(location: str) -> None:
    if not isinstance(location, str) or not re.fullmatch(
        r"(?:us|eu|[a-z]+(?:-[a-z]+)+[0-9]+)", location
    ):
        raise CollectionError("Use a lowercase BigQuery region or us/eu")


def validate_budget(maximum_bytes_billed: int, timeout_seconds: int) -> None:
    if type(maximum_bytes_billed) is not int or not 1 <= maximum_bytes_billed <= 10**9:
        raise CollectionError("Byte budget must be between 1 and 1000000000")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300:
        raise CollectionError("Timeout must be between 1 and 300 seconds")


@dataclass(frozen=True, slots=True)
class CollectionConfig:
    project: str
    location: str
    start: datetime
    end: datetime
    job_ids: tuple[str, ...]
    workload: Workload
    maximum_bytes_billed: int = 100_000_000
    timeout_seconds: int = 60

    def __post_init__(self) -> None:
        validate_project(self.project)
        validate_location(self.location)
        start, end = timestamp(self.start), timestamp(self.end)
        if end <= start or end - start > timedelta(days=31):
            raise CollectionError("Collection window must be positive and at most 31 days")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        if not isinstance(self.workload, Workload):
            raise CollectionError("Expected explicit workload registration")
        if not isinstance(self.job_ids, tuple) or not 1 <= len(self.job_ids) <= 100:
            raise CollectionError("Select between 1 and 100 job IDs")
        if any(
            not isinstance(j, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", j)
            for j in self.job_ids
        ):
            raise CollectionError("Invalid job ID")
        if len(set(self.job_ids)) != len(self.job_ids):
            raise CollectionError("Duplicate selected job IDs")
        validate_budget(self.maximum_bytes_billed, self.timeout_seconds)

    def validate_live_window(self, now: datetime) -> None:
        current = timestamp(now)
        if self.end > current or self.start < current - timedelta(days=180):
            raise CollectionError("Live collection must stay within the past 180 days")


@dataclass(frozen=True, slots=True)
class JobEvidence:
    job_id: str
    creation_time: datetime
    fingerprint: str | None
    state: str
    failure_reason: str | None
    observation: Observation | None
    issues: tuple[str, ...]
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def reliability_eligible(self) -> bool:
        """Classified failures may omit normalized fingerprints."""
        if not self.issues:
            return self.observation is not None
        return (
            self.state == "DONE"
            and self.failure_reason is not None
            and "Job failed" in self.issues
            and set(self.issues) <= {"Job failed", "Normalized fingerprint is unavailable"}
        )


@dataclass(frozen=True, slots=True)
class Collection:
    config: CollectionConfig
    jobs: tuple[JobEvidence, ...]
    missing_job_ids: tuple[str, ...]
    source: str

    @property
    def eligible(self) -> bool:
        """Eligibility is necessary, not proof that two collections are comparable."""
        return (
            bool(self.jobs)
            and not self.missing_job_ids
            and len({j.fingerprint for j in self.jobs}) == 1
            and all(not j.issues for j in self.jobs)
        )

    @property
    def reliability_eligible(self) -> bool:
        """Require all selected jobs; compare fingerprints only where supplied."""
        fingerprints = {j.fingerprint for j in self.jobs if j.fingerprint is not None}
        return (
            bool(self.jobs)
            and not self.missing_job_ids
            and len(fingerprints) <= 1
            and all(j.reliability_eligible for j in self.jobs)
        )
