"""Deployment-owned BigQuery scopes; never supplied by browser clients."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from datavouch.adapters.bigquery.models import CollectionConfig
from datavouch.core.models import Workload


@dataclass(frozen=True)
class Connection:
    id: str
    label: str
    project: str
    location: str
    maximum_bytes_billed: int
    timeout_seconds: int


def load_connections(path: Path | None) -> tuple[Connection, ...]:
    if path is None:
        return ()
    with path.open("rb") as source:
        raw = source.read(65537)
    if len(raw) > 65536:
        raise ValueError("Connection configuration exceeds 64 KiB")

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate connection configuration key")
            result[key] = value
        return result

    document = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(document, dict) or set(document) != {"connections"}:
        raise ValueError("Expected connections configuration")
    rows = document["connections"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise ValueError("Configure between 1 and 100 connections")
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(Connection.__dataclass_fields__):
            raise ValueError("Invalid connection fields")
        connection = Connection(**row)
        for value in (connection.id, connection.label):
            if not isinstance(value, str) or not value.strip() or len(value) > 200:
                raise ValueError("Invalid connection label or ID")
        start = datetime(2026, 1, 1, tzinfo=UTC)
        CollectionConfig(
            connection.project,
            connection.location,
            start,
            start + timedelta(days=1),
            ("validation",),
            Workload("configuration", "configuration", "configuration"),
            connection.maximum_bytes_billed,
            connection.timeout_seconds,
        )
        result.append(connection)
    if len({c.id for c in result}) != len(result):
        raise ValueError("Duplicate connection ID")
    return tuple(result)
