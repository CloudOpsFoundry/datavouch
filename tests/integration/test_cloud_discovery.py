"""Discovery is live metadata, bounded and intersected with deployment/user approval."""

import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from datavouch.web import discovery
from datavouch.web.access import LOCAL_ADMIN, Principal
from datavouch.web.app import create_app
from datavouch.web.connections import discovery_policy, load_configuration
from datavouch.web.discovery import ConnectionCatalog, DiscoveryError, Listing

POLICY = {
    "quota_project": "client-quota",
    "allowed_projects": ["client-analytics"],
    "allowed_locations": ["*"],
    "maximum_bytes_billed": 100000000,
    "timeout_seconds": 60,
}


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "connections.json"
    path.write_text(json.dumps({"connections": [], "discovery": POLICY}))
    return path


@pytest.fixture
def provider(monkeypatch):
    calls = []

    def listing(policy, project=""):
        calls.append(project)
        return Listing(
            (("client-analytics", "Analytics"), ("client-other", "Other"))
            if not project
            else (("eu", "EU"), ("us", "US")),
            "2026-11-18T12:00:00+00:00",
        )

    monkeypatch.setattr(discovery, "metadata_listing", listing)
    return calls


@pytest.mark.parametrize(
    "change",
    [
        {"allowed_projects": []},
        {"allowed_projects": ["*", "client-analytics"]},
        {"allowed_projects": ["client-analytics"] * 101},
        {"allowed_projects": [4]},
        {"allowed_locations": ["EU"]},
        {"allowed_locations": "eu"},
        {"quota_project": "bad project"},
        {"maximum_bytes_billed": True},
        {"timeout_seconds": 301},
        {"secret": "not-accepted"},
    ],
)
def test_discovery_policy_rejects_unsafe_configuration(change):
    with pytest.raises((ValueError, TypeError)):
        discovery_policy({**POLICY, **change})


def test_policy_and_user_filters_precede_location_fetch(config, provider):
    catalog = ConnectionCatalog(config)
    user = Principal("operator", "operator", frozenset({"gcp:client-analytics:eu"}))
    assert catalog.projects(user).entries == (("client-analytics", "Analytics"),)
    choices, _ = catalog.choices(user, "client-analytics")
    assert [c.id for c in choices] == ["gcp:client-analytics:eu"]
    with pytest.raises(DiscoveryError, match="Select a project"):
        catalog.choices(user, "client-other")
    assert catalog.projects(Principal("no-access", "operator", frozenset())).entries == ()
    assert provider == ["", "client-analytics"]
    assert catalog.resolve("gcp:client-other:eu") is None
    assert catalog.resolve("gcp:client-analytics:asia-east1") is None
    assert catalog.resolve("arbitrary") is None
    assert catalog.resolve("gcp:client-analytics:eu").location == "eu"
    config.write_text(json.dumps({"connections": [], "discovery": None}))
    assert catalog.resolve("gcp:client-analytics:eu") is None
    assert not catalog.enabled()


def test_refresh_ttl_failure_and_policy_changes(config, provider, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(discovery.time, "monotonic", lambda: now[0])
    catalog = ConnectionCatalog(config)
    catalog.projects(LOCAL_ADMIN)
    catalog.projects(LOCAL_ADMIN)
    assert provider == [""]
    catalog.refresh()
    catalog.projects(LOCAL_ADMIN)
    catalog.refresh()
    catalog.projects(LOCAL_ADMIN)
    assert provider == ["", ""]
    now[0] += 61
    catalog.projects(LOCAL_ADMIN)
    assert len(provider) == 3
    config.write_text(
        json.dumps({"connections": [], "discovery": {**POLICY, "allowed_projects": ["*"]}})
    )
    assert len(catalog.projects(LOCAL_ADMIN).entries) == 2
    assert len(provider) == 4
    now[0] += 61

    def failed(*args):
        raise DiscoveryError("Unavailable")

    monkeypatch.setattr(discovery, "metadata_listing", failed)
    with pytest.raises(DiscoveryError, match="Unavailable"):
        catalog.projects(LOCAL_ADMIN)
    assert ("projects", "") not in catalog.cache


@pytest.fixture
def rest(monkeypatch):
    import google.auth
    from google.auth.transport import requests

    adc = MagicMock(return_value=(object(), "ignored-project"))
    monkeypatch.setattr(google.auth, "default", adc)
    session = MagicMock()
    constructor = MagicMock()
    constructor.return_value.__enter__.return_value = session
    monkeypatch.setattr(requests, "AuthorizedSession", constructor)

    def reply(document, status=200):
        response = MagicMock()
        response.status_code = status
        response.iter_content.return_value = [json.dumps(document).encode()]
        response.__enter__.return_value = response
        return response

    return adc, session, reply


def test_rest_uses_adc_minimal_metadata_and_pagination(rest):
    adc, session, reply = rest
    session.request.side_effect = [
        reply(
            {
                "projects": [
                    {
                        "projectReference": {"projectId": "client-analytics"},
                        "friendlyName": "Analytics",
                    }
                ],
                "nextPageToken": "next",
            }
        ),
        reply({"projects": [{"projectReference": {"projectId": "not valid"}}]}),
    ]
    result = discovery.metadata_listing(discovery_policy(POLICY))
    assert result.entries == (("client-analytics", "Analytics"),)
    assert not result.incomplete
    assert adc.call_args.kwargs["quota_project_id"] == "client-quota"
    assert session.request.call_args.kwargs["params"]["pageToken"] == "next"
    assert all(c.args[0] == "GET" for c in session.request.call_args_list)
    session.request.reset_mock()
    session.request.side_effect = [
        reply({"datasets": [{"location": "EU"}], "unreachable": ["us"]}),
        reply(
            {
                "jobs": [
                    {"jobReference": {"location": "europe-west3"}},
                    {"jobReference": {"location": "invalid"}},
                ]
            }
        ),
    ]
    result = discovery.metadata_listing(discovery_policy(POLICY), "client-analytics")
    assert result.entries == (("eu", "EU"), ("europe-west3", "europe-west3"))
    assert result.incomplete
    for call in session.request.call_args_list:
        assert "client-analytics" in call.args[1]
        assert call.kwargs["allow_redirects"] is False
        assert call.kwargs["timeout"] <= 5
        assert "query" not in call.kwargs["params"]["fields"]
        assert "user_email" not in call.kwargs["params"]["fields"]


@pytest.mark.parametrize("status", [401, 403, 429, 500, 302])
def test_provider_errors_are_sanitized(rest, status):
    _, session, reply = rest
    session.request.return_value = reply({"error": "SECRET-PROVIDER-DETAIL"}, status)
    with pytest.raises(DiscoveryError) as error:
        discovery.metadata_listing(discovery_policy(POLICY))
    assert "SECRET" not in str(error.value)


def test_provider_page_and_response_limits(rest):
    _, session, reply = rest
    session.request.side_effect = [
        reply({"projects": [], "nextPageToken": "next"}) for _ in range(3)
    ]
    assert discovery.metadata_listing(discovery_policy(POLICY)).incomplete
    assert session.request.call_count == 3
    session.request.side_effect = None
    session.request.return_value = reply({"data": "x" * 65536})
    with pytest.raises(DiscoveryError, match="response limit"):
        discovery.metadata_listing(discovery_policy(POLICY))
    session.request.return_value = reply({"projects": "invalid"})
    with pytest.raises(DiscoveryError, match="invalid discovery"):
        discovery.metadata_listing(discovery_policy(POLICY))
    session.request.return_value = reply({"nextPageToken": 123})
    with pytest.raises(DiscoveryError, match="pagination"):
        discovery.metadata_listing(discovery_policy(POLICY))
    session.request.side_effect = RuntimeError("SECRET-CREDENTIAL")
    with pytest.raises(DiscoveryError) as error:
        discovery.metadata_listing(discovery_policy(POLICY))
    assert "SECRET" not in str(error.value)


def test_browser_project_selection_refresh_and_error(config, provider, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    with TestClient(
        create_app(root / "examples/viewer.json", "fixture-only-password", connections=config),
        base_url="http://127.0.0.1",
    ) as client:
        client.auth = ("datavouch", "fixture-only-password")
        page = client.get("/experiments/new")
        assert "Load locations" in page.text
        assert "client-analytics" in page.text
        assert "client-other" not in page.text
        assert "gcp:client-analytics:eu" not in page.text
        page = client.get("/experiments/new?project=client-analytics")
        assert 'value="gcp:client-analytics:eu"' in page.text
        assert 'value="gcp:client-analytics:us"' in page.text
        assert "Metadata checked" in page.text
        token = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
        assert client.post("/connections/refresh", data={"csrf": "wrong"}).status_code == 403
        response = client.post(
            "/connections/refresh",
            data={"csrf": token, "project": "client-analytics"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/experiments/new?project=client-analytics"
        assert client.get("/experiments/new?project=bad/project").status_code == 400
        assert (
            "Select a project visible" in client.get("/experiments/new?project=client-other").text
        )

        def failed(*args):
            raise DiscoveryError("Google Cloud discovery unavailable")

        monkeypatch.setattr(discovery, "metadata_listing", failed)
        page = client.get("/experiments/new?project=client-analytics")
        assert "Google Cloud discovery unavailable" in page.text
        assert 'value="gcp:client-analytics:eu"' not in page.text


def test_static_ids_cannot_impersonate_discovered_connections(config):
    config.write_text(
        json.dumps(
            {
                "connections": [
                    {
                        "id": "gcp:client-analytics:eu",
                        "label": "Test",
                        "project": "client-analytics",
                        "location": "eu",
                        "maximum_bytes_billed": 10,
                        "timeout_seconds": 1,
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="reserved"):
        load_configuration(config)


def test_discovered_scope_worker_checks_current_policy(config, provider, tmp_path, monkeypatch):
    from datetime import UTC, datetime

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 20, tzinfo=UTC)

    monkeypatch.setattr("datavouch.web.runs.datetime", Clock)
    from datavouch.web.runs import RunStore

    catalog = ConnectionCatalog(config)
    plan = json.loads(
        (Path(__file__).resolve().parents[2] / "examples/bigquery/experiment/plan.json").read_text()
    )
    for side in ("baseline", "candidate"):
        plan[side]["project"] = "client-analytics"
    store = RunStore(tmp_path / "runs", config, resolve_connection=catalog.resolve)
    try:
        assert store._authorize(plan, "gcp:client-analytics:eu") == 150
        with pytest.raises(ValueError, match="scope differs"):
            store._authorize(plan, "gcp:client-analytics:us")
        config.write_text(
            json.dumps({"connections": [], "discovery": {**POLICY, "maximum_bytes_billed": 1}})
        )
        with pytest.raises(ValueError, match="collection limits"):
            store._authorize(plan, "gcp:client-analytics:eu")
        config.write_text(
            json.dumps({"connections": [], "discovery": {**POLICY, "allowed_locations": ["us"]}})
        )
        with pytest.raises(ValueError, match="no longer approved"):
            store._authorize(plan, "gcp:client-analytics:eu")
    finally:
        store.close()


def test_gateway_discovery_respects_roles_and_exact_scopes(config, provider, tmp_path):
    gateway = tmp_path / "gateway.json"
    gateway.write_text(
        json.dumps(
            {
                "allowed_hosts": ["datavouch.example.test"],
                "trusted_proxy_networks": ["127.0.0.1/32"],
                "principals": {
                    "reader": {"role": "viewer", "connections": ["gcp:client-analytics:eu"]},
                    "writer": {"role": "operator", "connections": ["gcp:client-analytics:eu"]},
                },
            }
        )
    )
    root = Path(__file__).resolve().parents[2]
    app = create_app(
        root / "examples/viewer.json",
        "",
        connections=config,
        gateway_config=gateway,
        gateway_secret="fixture-only-gateway-secret-not-for-deployment",
    )
    with TestClient(
        app, base_url="https://datavouch.example.test", client=("127.0.0.1", 12345)
    ) as client:
        client.headers.update(
            {
                "X-DataVouch-Gateway-Token": "fixture-only-gateway-secret-not-for-deployment",
                "X-Auth-Request-User": "reader",
            }
        )
        assert client.get("/experiments/new").status_code == 403
        assert client.post("/connections/refresh", data={}).status_code == 403
        assert provider == []
        client.headers["X-Auth-Request-User"] = "writer"
        page = client.get("/experiments/new?project=client-analytics")
        assert 'value="gcp:client-analytics:eu"' in page.text
        assert 'value="gcp:client-analytics:us"' not in page.text
        token = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
        denied = client.post(
            "/experiments/new",
            data={"csrf": token, "connection": "gcp:client-analytics:us", "action": "validate"},
        )
        assert denied.status_code == 422
        assert "Select a connection approved" in denied.text
