"""Deployment-owned BigQuery scopes; never supplied by browser clients."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datavouch.adapters.bigquery.models import validate_budget, validate_location, validate_project


@dataclass(frozen=True)
class Connection:
    id: str
    label: str
    project: str
    location: str
    maximum_bytes_billed: int
    timeout_seconds: int


@dataclass(frozen=True)
class DiscoveryPolicy:
    quota_project: str
    allowed_projects: tuple[str, ...]
    allowed_locations: tuple[str, ...]
    maximum_bytes_billed: int
    timeout_seconds: int

    def permits(self, project: str, location: str | None = None) -> bool:
        return ("*" in self.allowed_projects or project in self.allowed_projects) and (
            location is None or "*" in self.allowed_locations or location in self.allowed_locations
        )


def validate_scope(project: str, location: str, maximum: int, timeout: int) -> None:
    validate_project(project)
    validate_location(location)
    validate_budget(maximum, timeout)


def discovery_policy(value: Any) -> DiscoveryPolicy | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != set(DiscoveryPolicy.__dataclass_fields__):
        raise ValueError("Invalid discovery configuration fields")
    for key in ("allowed_projects", "allowed_locations"):
        items = value[key]
        if (
            not isinstance(items, list)
            or not 1 <= len(items) <= 100
            or any(not isinstance(item, str) for item in items)
            or len(set(items)) != len(items)
            or ("*" in items and items != ["*"])
        ):
            raise ValueError("Discovery allowlists require unique names or a single wildcard")
    policy = DiscoveryPolicy(
        **{
            **value,
            "allowed_projects": tuple(value["allowed_projects"]),
            "allowed_locations": tuple(value["allowed_locations"]),
        }
    )
    validate_project(policy.quota_project)
    validate_budget(policy.maximum_bytes_billed, policy.timeout_seconds)
    for project in policy.allowed_projects:
        if project != "*":
            validate_project(project)
    for location in policy.allowed_locations:
        if location != "*":
            validate_location(location)
    return policy


def load_configuration(path: Path | None) -> tuple[tuple[Connection, ...], DiscoveryPolicy | None]:
    if path is None:
        return (), None
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
    if (
        not isinstance(document, dict)
        or "connections" not in document
        or set(document) - {"connections", "discovery"}
    ):
        raise ValueError("Expected connections configuration")
    rows = document["connections"]
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError("Configure at most 100 connections")
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(Connection.__dataclass_fields__):
            raise ValueError("Invalid connection fields")
        connection = Connection(**row)
        for value in (connection.id, connection.label):
            if not isinstance(value, str) or not value.strip() or len(value) > 200:
                raise ValueError("Invalid connection label or ID")
        if connection.id.startswith("gcp:"):
            raise ValueError("The gcp: prefix is reserved for discovered connections")
        validate_scope(
            connection.project,
            connection.location,
            connection.maximum_bytes_billed,
            connection.timeout_seconds,
        )
        result.append(connection)
    if len({c.id for c in result}) != len(result):
        raise ValueError("Duplicate connection ID")
    return tuple(result), discovery_policy(document.get("discovery"))


def load_connections(path: Path | None) -> tuple[Connection, ...]:
    return load_configuration(path)[0]
