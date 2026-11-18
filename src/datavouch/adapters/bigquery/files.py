"""Bounded offline fixtures and deterministic collection JSON."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from datavouch.adapters.bigquery.collector import collect_rows
from datavouch.adapters.bigquery.models import (
    Collection,
    CollectionConfig,
    CollectionError,
    timestamp,
)
from datavouch.core.models import Workload


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CollectionError("Duplicate JSON field")
        result[key] = value
    return result


def _read(path: Path) -> Any:
    with path.open("rb") as source:
        raw = source.read(5_000_001)
    if len(raw) > 5_000_000:
        raise CollectionError("JSON input exceeds 5 MB")
    return json.loads(raw, object_pairs_hook=_unique)


def load_config(path: Path) -> CollectionConfig:
    """Load explicit collection scope and caller registered workload identity."""
    return decode_config(_read(path))


def decode_config(data: object) -> CollectionConfig:
    """Validate provider configuration without transport or filesystem access."""
    required = {"project", "location", "start", "end", "job_ids", "workload"}
    optional = {"maximum_bytes_billed", "timeout_seconds"}
    if (
        not isinstance(data, dict)
        or not required <= data.keys()
        or data.keys() - required - optional
    ):
        raise CollectionError("Invalid collection configuration fields")
    if not isinstance(data["job_ids"], list) or not isinstance(data["workload"], dict):
        raise CollectionError("Expected job ID array and workload object")
    return CollectionConfig(
        data["project"],
        data["location"],
        timestamp(data["start"]),
        timestamp(data["end"]),
        tuple(data["job_ids"]),
        Workload(**data["workload"]),
        data.get("maximum_bytes_billed", 100_000_000),
        data.get("timeout_seconds", 60),
    )


def load_fixture(path: Path, config: CollectionConfig) -> Collection:
    """Use the same row validation as the live transport, without loading cloud libraries."""
    rows = _read(path)
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise CollectionError("Expected an array of metadata objects")
    return collect_rows(rows, config)


def render_collection(collection: Collection, *, include_times: bool = False) -> str:
    """Preserve safe metadata and explicitly identify missing or excluded jobs."""
    data = asdict(collection)
    data["config"]["job_ids"] = sorted(data["config"]["job_ids"])
    data["schema_version"] = (
        "bigquery-collection-0.2" if include_times else "bigquery-collection-0.1"
    )
    if not include_times:
        # Preserve the existing collection contract for callers and adapter fixtures.
        for job in data["jobs"]:
            job.pop("started_at")
            job.pop("completed_at")
    data["eligible"] = collection.eligible
    data["fingerprint_groups"] = {
        fingerprint: [j.job_id for j in collection.jobs if j.fingerprint == fingerprint]
        for fingerprint in sorted({j.fingerprint for j in collection.jobs if j.fingerprint})
    }
    data["observations"] = [asdict(job.observation) for job in collection.jobs if job.observation]
    data["limitations"] = [
        "Fingerprint equality does not establish matching parameters, data or environment.",
        "Workload registration and input snapshot are caller assertions.",
        "No correctness, reliability threshold or financial conclusion is supported.",
        "Do not compare observations from collections marked ineligible.",
        "Multiple fingerprint groups require separate collection scopes.",
    ]

    def encode(value: object) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError("Unsupported collection value")

    return json.dumps(data, default=encode, sort_keys=True, indent=2, allow_nan=False) + "\n"
