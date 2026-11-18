"""Translate bounded metadata rows without inferring workload equivalence."""

import re
from collections.abc import Iterable, Mapping

from datavouch.adapters.bigquery.models import (
    Collection,
    CollectionConfig,
    CollectionError,
    JobEvidence,
    timestamp,
)
from datavouch.core.models import Execution, Measurement, Metric, Observation

METRICS = (
    ("total_slot_ms", "slot_time", "slot_ms"),
    ("total_bytes_processed", "processed_bytes", "bytes"),
    ("total_bytes_billed", "billed_bytes", "bytes"),
)


def _job(row: Mapping[str, object], config: CollectionConfig) -> JobEvidence:
    job_id = row.get("job_id")
    if not isinstance(job_id, str) or job_id not in config.job_ids:
        raise CollectionError("Metadata contains an unrequested or missing job ID")
    if row.get("project_id") != config.project or row.get("location") != config.location:
        raise CollectionError("Metadata project or location does not match collection scope")
    created = timestamp(row.get("creation_time"))
    if not config.start <= created < config.end:
        raise CollectionError("Metadata falls outside the requested creation window")
    issues: list[str] = []
    state = row.get("state")
    if state not in ("PENDING", "RUNNING", "DONE"):
        raise CollectionError("Missing or invalid job state")
    failure = row.get("failure_reason")
    if failure is not None and (
        not isinstance(failure, str) or not re.fullmatch(r"[A-Za-z]{1,80}", failure)
    ):
        raise CollectionError("Invalid failure classification")
    fingerprint = row.get("fingerprint")
    if fingerprint is not None and (
        not isinstance(fingerprint, str) or not re.fullmatch(r"[a-fA-F0-9]{1,128}", fingerprint)
    ):
        raise CollectionError("Invalid normalized fingerprint")
    if (
        row.get("job_type") != "QUERY"
        or row.get("statement_type") != "SELECT"
        or row.get("parent_job_id") is not None
    ):
        issues.append("Only standalone SELECT query jobs are supported")
    if "parent_job_id" not in row:
        issues.append("Parent job metadata is missing")
    if state != "DONE":
        issues.append("Job is not complete")
    if "failure_reason" not in row:
        issues.append("Failure classification is missing")
    if failure is not None:
        issues.append("Job failed")
    cache = row.get("cache_hit")
    if type(cache) is not bool:
        issues.append("Cache status is missing")
    elif cache:
        issues.append("Cached execution is not eligible")
    if fingerprint is None:
        issues.append("Normalized fingerprint is unavailable")
    measurements = []
    start, end = row.get("start_time"), row.get("end_time")
    started, ended = None, None
    if start is None or end is None:
        issues.append("Execution timestamps are incomplete")
    else:
        started, ended = timestamp(start), timestamp(end)
        if started < created or ended < started:
            raise CollectionError("Inconsistent execution timestamps")
        measurements.append(
            Measurement(Metric("runtime", "ms"), (ended - started).total_seconds() * 1000)
        )
    for field, name, unit in METRICS:
        value = row.get(field)
        if value is None:
            continue
        if type(value) is not int or value < 0 or value > 2**63 - 1:
            raise CollectionError("Resource measurements must be nonnegative INT64 values")
        measurements.append(Measurement(Metric(name, unit), value))
    # Never expose partial rows as successful observations after silently dropping evidence.
    observation = None
    if not issues:
        observation = Observation(
            config.workload,
            Execution(f"{config.project}/{config.location}/{job_id}"),
            tuple(measurements),
        )
    return JobEvidence(
        job_id,
        created,
        fingerprint,
        str(state),
        failure,
        observation,
        tuple(issues),
        started,
        ended,
    )


def collect_rows(
    rows: Iterable[Mapping[str, object]], config: CollectionConfig, *, source: str = "fixture"
) -> Collection:
    """Reject duplicates and oversized results. Retain explicit exclusions and missing IDs."""
    jobs = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if index >= len(config.job_ids):
            raise CollectionError("Collection exceeded the selected job count")
        job = _job(row, config)
        if job.job_id in seen:
            raise CollectionError("Duplicate metadata records")
        seen.add(job.job_id)
        jobs.append(job)
    return Collection(
        config,
        tuple(sorted(jobs, key=lambda j: j.job_id)),
        tuple(sorted(set(config.job_ids) - seen)),
        source,
    )
