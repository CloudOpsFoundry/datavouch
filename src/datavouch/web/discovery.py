"""Bounded, keyless BigQuery metadata discovery; never a grant of execution rights."""

import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from datavouch.web.access import Principal
from datavouch.web.connections import (
    Connection,
    DiscoveryPolicy,
    load_configuration,
    validate_scope,
)

PROJECT = re.compile(r"[a-z][a-z0-9-]{4,28}[a-z0-9]")
LOCATION = re.compile(r"(?:us|eu|[a-z]+(?:-[a-z]+)+[0-9]+)")


class DiscoveryError(ValueError):
    """Safe provider error without tokens, resource names or raw provider messages."""


@dataclass(frozen=True)
class Listing:
    entries: tuple[tuple[str, str], ...]
    checked_at: str
    incomplete: bool = False


def metadata_listing(policy: DiscoveryPolicy, project: str = "") -> Listing:
    """Read minimal REST fields with ADC, bounded pages, time and response bytes."""
    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
    except ImportError as exc:
        raise DiscoveryError(
            "Install the BigQuery extra to enable Google Cloud discovery."
        ) from exc
    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
            quota_project_id=policy.quota_project,
        )
        with AuthorizedSession(  # type: ignore[no-untyped-call]
            credentials, refresh_timeout=5, max_refresh_attempts=1
        ) as session:
            deadline = time.monotonic() + 25
            entries: dict[str, str] = {}
            incomplete = False
            paths = (
                [
                    (
                        "projects",
                        "projects",
                        "projects(projectReference(projectId),friendlyName),nextPageToken",
                    )
                ]
                if not project
                else [
                    (
                        f"projects/{project}/datasets",
                        "datasets",
                        "datasets(location),nextPageToken,unreachable",
                    ),
                    (
                        f"projects/{project}/jobs",
                        "jobs",
                        "jobs(jobReference(location)),nextPageToken",
                    ),
                ]
            )
            for path, field, fields in paths:
                page_cursor = ""
                for _ in range(3):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise DiscoveryError(
                            "Google Cloud discovery timed out. Refresh to try again."
                        )
                    params: dict[str, str | int] = {"maxResults": 100, "fields": fields}
                    if page_cursor:
                        params["pageToken"] = page_cursor
                    if field == "jobs":
                        params["allUsers"] = "true"
                        params["projection"] = "minimal"
                    with session.request(  # type: ignore[no-untyped-call]
                        "GET",
                        "https://bigquery.googleapis.com/bigquery/v2/" + path,
                        params=params,
                        timeout=min(5, remaining),
                        max_allowed_time=remaining,
                        allow_redirects=False,
                        stream=True,
                    ) as response:
                        if response.status_code in (401, 403):
                            raise DiscoveryError(
                                "Google Cloud denied discovery. Check backend credentials, "
                                "quota-project access and metadata permissions."
                            )
                        if response.status_code != 200:
                            raise DiscoveryError(
                                "Google Cloud discovery is unavailable. "
                                "Check the BigQuery API and retry."
                            )
                        raw = bytearray()
                        for chunk in response.iter_content(8192):
                            raw.extend(chunk)
                            if len(raw) > 65536 or time.monotonic() > deadline:
                                raise DiscoveryError(
                                    "Google Cloud discovery exceeded its response limit."
                                )
                        document = json.loads(raw)
                    if not isinstance(document, dict) or not isinstance(
                        document.get(field, []), list
                    ):
                        raise DiscoveryError("Google Cloud returned invalid discovery metadata.")
                    incomplete |= bool(document.get("unreachable"))
                    for row in document.get(field, []):
                        if not isinstance(row, dict):
                            raise DiscoveryError(
                                "Google Cloud returned invalid discovery metadata."
                            )
                        if field == "projects":
                            reference = row.get("projectReference", {})
                            value = reference.get("projectId", "")
                            if not isinstance(value, str) or not PROJECT.fullmatch(value):
                                continue
                            label = row.get("friendlyName") or value
                            if (
                                not isinstance(label, str)
                                or len(label) > 200
                                or not label.isprintable()
                            ):
                                label = value
                            entries[value] = label
                        else:
                            value = (
                                row.get("location")
                                if field == "datasets"
                                else row.get("jobReference", {}).get("location")
                            )
                            if isinstance(value, str) and LOCATION.fullmatch(value.lower()):
                                entries[value.lower()] = (
                                    value.upper()
                                    if value.lower() in ("eu", "us")
                                    else value.lower()
                                )
                    page_cursor = document.get("nextPageToken", "")
                    if not isinstance(page_cursor, str) or len(page_cursor) > 4096:
                        raise DiscoveryError("Google Cloud returned invalid pagination metadata.")
                    if not page_cursor:
                        break
                incomplete |= bool(page_cursor)
            return Listing(
                tuple(sorted(entries.items())), datetime.now(UTC).isoformat(), incomplete
            )
    except DiscoveryError:
        raise
    except Exception as exc:
        raise DiscoveryError(
            "Google Cloud discovery failed. Check backend Application Default Credentials, "
            "connectivity and metadata permissions."
        ) from exc


class ConnectionCatalog:
    """One bounded cache per application; policy and principal checks are never cached."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        load_configuration(path)
        self.lock = threading.RLock()
        self.cache: dict[tuple[str, str], tuple[float, Listing]] = {}
        self.policy: DiscoveryPolicy | None = None
        self.last_refresh = -5.0

    def refresh(self) -> None:
        with self.lock:
            now = time.monotonic()
            if now - self.last_refresh >= 5:
                self.cache.clear()
                self.last_refresh = now

    def _listing(self, policy: DiscoveryPolicy, project: str = "") -> Listing:
        with self.lock:
            if policy != self.policy:
                self.cache.clear()
                self.policy = policy
            key = ("locations" if project else "projects", project)
            cached = self.cache.get(key)
            if cached and time.monotonic() - cached[0] < 60:
                return cached[1]
            self.cache.pop(key, None)  # Never serve expired results after a failed refresh.
            result = metadata_listing(policy, project)
            if len(self.cache) >= 101:
                self.cache.clear()
            self.cache[key] = (time.monotonic(), result)
            return result

    def enabled(self) -> bool:
        return load_configuration(self.path)[1] is not None

    def projects(self, user: Principal) -> Listing:
        static, policy = load_configuration(self.path)
        if policy is None:
            return Listing((), "")
        result = self._listing(policy)
        allowed = []
        for project, label in result.entries:
            if not policy.permits(project):
                continue
            if user.connections is not None and not (
                any(c.project == project and user.permits(c.id) for c in static)
                or any(c.startswith(f"gcp:{project}:") for c in user.connections)
            ):
                continue
            allowed.append((project, label))
        return Listing(tuple(allowed), result.checked_at, result.incomplete)

    def choices(self, user: Principal, project: str = "") -> tuple[tuple[Connection, ...], Listing]:
        static, policy = load_configuration(self.path)
        choices = [c for c in static if user.permits(c.id)]
        if not project or policy is None:
            return tuple(choices), Listing((), "")
        if not PROJECT.fullmatch(project) or project not in dict(self.projects(user).entries):
            raise DiscoveryError(
                "Select a project visible to your identity and approved by this deployment."
            )
        locations = self._listing(policy, project)
        for location, label in locations.entries:
            if not policy.permits(project, location):
                continue
            identity = f"gcp:{project}:{location}"
            if user.permits(identity) and not any(
                (c.project, c.location) == (project, location) for c in choices
            ):
                choices.append(
                    Connection(
                        identity,
                        f"Google Cloud · {label}",
                        project,
                        location,
                        policy.maximum_bytes_billed,
                        policy.timeout_seconds,
                    )
                )
        return tuple(choices), locations

    def resolve(self, identity: str) -> Connection | None:
        static, policy = load_configuration(self.path)
        existing = next((c for c in static if c.id == identity), None)
        if existing:
            return existing
        parts = identity.split(":")
        if len(parts) != 3 or parts[0] != "gcp" or policy is None:
            return None
        project, location = parts[1:]
        validate_scope(project, location, policy.maximum_bytes_billed, policy.timeout_seconds)
        if not policy.permits(project, location):
            return None
        if project not in dict(self._listing(policy).entries):
            return None
        if location not in dict(self._listing(policy, project).entries):
            return None
        return Connection(
            identity,
            "Google Cloud",
            project,
            location,
            policy.maximum_bytes_billed,
            policy.timeout_seconds,
        )
