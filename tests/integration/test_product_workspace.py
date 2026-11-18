"""Product journeys using actual fixture replay, never cloud credentials."""

import json
import re
import threading

import pytest
from fastapi.testclient import TestClient
from test_web_runs import ROOT, browser_form, finish, fixture_worker, setup

from datavouch.financial.evaluation import assess
from datavouch.web.app import create_app
from datavouch.web.evidence import check_key, supplied_evidence
from datavouch.web.financial import financial_document
from datavouch.web.runs import RunBusy, RunStore

__all__ = ["setup"]
PASSWORD = "fixture-only-password"
SECRET = "fixture-gateway-secret-not-for-deployment"


def csrf(client, url):
    return re.search(r'name="csrf" value="([^"]+)"', client.get(url).text).group(1)


def application(root, config, **kwargs):
    return create_app(
        ROOT / "examples/viewer.json",
        PASSWORD,
        connections=config,
        run_directory=root,
        enable_live_execution=True,
        allow_raw_reports=True,
        **kwargs,
    )


def pricing():
    return {
        "scope": "fixture workload",
        "pricing_model": "on_demand",
        "currency": "USD",
        "rate": "5",
        "pricing_reference": "synthetic contract",
        "valid_from": "2026-01-01T00:00",
        "valid_to": "2027-01-01T00:00",
        "confirmed": "yes",
    }


@pytest.mark.parametrize("outcome,expected", [("true", "PASS"), ("false", "FAIL"), ("", "UNKNOWN")])
def test_complete_browser_journey(setup, monkeypatch, outcome, expected):
    root, config, plan = setup
    fixture_worker(monkeypatch)
    done = threading.Event()
    original = RunStore._execute

    def worker(self, *args):
        try:
            original(self, *args)
        finally:
            done.set()

    monkeypatch.setattr(RunStore, "_execute", worker)
    with TestClient(
        application(root, config), base_url="http://127.0.0.1", follow_redirects=False
    ) as client:
        client.auth = ("datavouch", PASSWORD)
        form = browser_form(client, plan)
        key = check_key("business_total")
        form.update(
            {
                key + "_outcome": outcome,
                key + "_reference": "fixture assertion",
                "evidence_confirmed": "yes",
            }
        )
        response = client.post("/experiments/new", data=form)
        assert response.status_code == 303, response.text
        assert done.wait(5)
        url = response.headers["location"]
        assert client.get(url + "/summary.json").json()["status"] == expected
        assert (
            client.get(url + "/report.json").content
            == (root / url.split("/")[-1] / "result/report.json").read_bytes()
        )
        assert plan["id"] in client.get("/runs?status=" + expected).text
        assert plan["id"] not in client.get("/runs?q=absent-workload").text
        assert "Processed bytes" in client.get(url).text
        values = {**pricing(), "csrf": csrf(client, url)}
        assert client.post(url + "/financial", data={**values, "csrf": "bad"}).status_code == 403
        assert client.post(url + "/financial", data=values).status_code == 303
        assert client.post(url + "/financial", data=values).status_code == 303
        files = list((root / url.split("/")[-1] / "financial").glob("*.json"))
        assert len(files) == 1
        stored = json.loads(files[0].read_text())
        assert stored["report"] == assess(stored["input"])
        assert client.get(url + "/financial/" + files[0].name).json() == stored["report"]
        invalid = {**values, "financial_json": '{"experiment_id":"wrong"}'}
        assert client.post(url + "/financial", data=invalid).status_code == 422
        assert client.post(url + "/delete", data={"csrf": values["csrf"]}).status_code == 400
        assert (
            client.post(
                url + "/delete", data={"csrf": values["csrf"], "confirmed": "yes"}
            ).status_code
            == 303
        )
        assert client.get(url).status_code == 404
        assert not (root / url.split("/")[-1]).exists()
        actions = [event["action"] for event in client.get("/audit.json").json()]
        assert "financial_assessed" in actions and "run_deleted" in actions


def policy_file(root):
    path = root.parent / "gateway.json"
    path.write_text(
        json.dumps(
            {
                "allowed_hosts": ["datavouch.example.test"],
                "trusted_proxy_networks": ["127.0.0.1/32"],
                "principals": {
                    "reader": {"role": "viewer", "connections": ["test"]},
                    "writer": {"role": "operator", "connections": ["test"]},
                    "owner": {"role": "admin", "connections": ["test"]},
                    "outsider": {"role": "admin", "connections": ["other"]},
                },
            }
        )
    )
    return path


def headers(subject):
    return {"X-DataVouch-Gateway-Token": SECRET, "X-Auth-Request-User": subject}


def test_gateway_roles_isolation_and_revocation(setup, monkeypatch):
    root, config, plan = setup
    fixture_worker(monkeypatch)
    store = RunStore(root, config)
    key = store.submit(plan, "test")
    finish(store)
    store.close()
    policy = policy_file(root)
    app = application(root, config, gateway_config=policy, gateway_secret=SECRET)
    with TestClient(
        app, base_url="https://datavouch.example.test", client=("127.0.0.1", 12345)
    ) as client:
        assert client.get("/").status_code == 403
        assert client.get("/", auth=("datavouch", PASSWORD)).status_code == 403
        assert client.get("/", headers=headers("unknown")).status_code == 403
        assert (
            client.get(
                "/", headers={**headers("reader"), "X-DataVouch-Gateway-Token": "wrong"}
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/", headers=[*headers("reader").items(), ("X-Auth-Request-User", "owner")]
            ).status_code
            == 403
        )
        url = "/runs/" + key
        client.headers.update(headers("reader"))
        assert client.get(url).status_code == 200
        assert client.get(url + "/report.json").status_code == 403
        assert client.get("/experiments/new").status_code == 403
        assert client.post(url + "/financial", data={}).status_code == 403
        assert client.get("/audit.json").status_code == 403
        client.headers.update(headers("writer"))
        writer_token = csrf(client, url)
        assert client.get("/experiments/new").status_code == 200
        assert client.get(url + "/report.json").status_code == 200
        assert client.post(url + "/delete", data={}).status_code == 403
        client.headers.update(headers("outsider"))
        assert client.get(url).status_code == 404
        assert plan["id"] not in client.get("/runs").text
        assert client.get("/audit.json").json() == []
        client.headers.update(headers("owner"))
        assert (
            client.post(url + "/financial", data={**pricing(), "csrf": writer_token}).status_code
            == 403
        )
        assert client.get("/audit.json").status_code == 200
        document = json.loads(policy.read_text())
        del document["principals"]["owner"]
        policy.write_text(json.dumps(document))
        assert client.get(url).status_code == 403


def test_gateway_untrusted_peer_and_invalid_origins(setup):
    root, config, plan = setup
    policy = policy_file(root)
    with TestClient(
        create_app(ROOT / "examples/viewer.json", "", gateway_config=policy, gateway_secret=SECRET),
        base_url="https://datavouch.example.test",
        client=("192.0.2.1", 23456),
    ) as client:
        assert (
            client.get(
                "/", headers={**headers("owner"), "X-Forwarded-For": "127.0.0.1"}
            ).status_code
            == 403
        )
    with TestClient(
        create_app(ROOT / "examples/viewer.json", PASSWORD), base_url="http://127.0.0.1"
    ) as client:
        client.auth = ("datavouch", PASSWORD)
        for origin in ("null", "https://attacker.example", "http://[invalid"):
            assert client.post("/experiments/new", headers={"Origin": origin}).status_code == 403


def test_evidence_binding_and_confirmation(setup):
    _, _, plan = setup
    # Guided evidence binds candidate IDs server-side; advanced evidence must match.
    name = plan["assurance"]["required_checks"][0]
    field = check_key(name)
    values = {
        field + "_outcome": "true",
        field + "_reference": "independent fixture",
        "evidence_confirmed": "yes",
    }
    check = supplied_evidence(values, plan)[0]
    assert check["experiment_id"] == plan["id"]
    for invalid in (
        {**values, "evidence_confirmed": ""},
        {**values, field + "_reference": ""},
        {**values, field + "_outcome": "maybe"},
    ):
        with pytest.raises(ValueError):
            supplied_evidence(invalid, plan)
    for changed in (
        {**check, "experiment_id": "other"},
        {**check, "execution_ids": ["other"]},
        {**check, "name": "unrequested"},
    ):
        with pytest.raises(ValueError):
            supplied_evidence(
                {"evidence_json": json.dumps([changed]), "evidence_confirmed": "yes"}, plan
            )
    with pytest.raises(ValueError):
        supplied_evidence({"evidence_json": '[{"name":"a","name":"b"}]'}, plan)
    with pytest.raises(ValueError):
        supplied_evidence({**values, "evidence_json": json.dumps([check])}, plan)


def test_financial_binding_capacity_and_limits(setup, monkeypatch):
    root, config, plan = setup
    fixture_worker(monkeypatch)
    with_store = RunStore(root, config)
    try:
        key = with_store.submit(plan, "test")
        finish(with_store)
        verification = with_store.verification(key)
        doc = financial_document({**pricing(), "pricing_model": "capacity"}, verification)
        assert doc["baseline"]["billed_slot_hours"] is None
        assert assess(doc)["status"] == "UNKNOWN"
        doc["baseline"]["execution_ids"] = ["unrelated"]
        with pytest.raises(ValueError, match="match"):
            financial_document({"financial_json": json.dumps(doc)}, verification)
        for index in range(10):
            with_store.assess_financial(key, {**pricing(), "scope": f"scope{index}"})
        with pytest.raises(ValueError, match="ten"):
            with_store.assess_financial(key, {**pricing(), "scope": "eleven"})
        with_store.records[key]["state"] = "RUNNING"
        with pytest.raises(RunBusy):
            with_store.delete(key)
    finally:
        with_store.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("allowed_hosts", ["*"]),
        ("allowed_hosts", []),
        ("trusted_proxy_networks", ["0.0.0.0/0"]),
        ("trusted_proxy_networks", []),
        ("principals", []),
        ("principals", {"": {"role": "admin", "connections": []}}),
        ("principals", {"person": {"role": "root", "connections": []}}),
        ("principals", {"person": {"role": "admin", "connections": [""]}}),
    ],
)
def test_invalid_gateway_policy_fails_closed(setup, field, value):
    root, _, _ = setup
    policy = policy_file(root)
    document = json.loads(policy.read_text())
    document[field] = value
    policy.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        create_app(ROOT / "examples/viewer.json", "", gateway_config=policy, gateway_secret=SECRET)


@pytest.mark.parametrize("secret", ["short", " " * 40, "é" * 40, "x" * 257])
def test_invalid_backend_secret(setup, secret):
    root, _, _ = setup
    with pytest.raises(ValueError, match="secret"):
        create_app(
            ROOT / "examples/viewer.json",
            "",
            gateway_config=policy_file(root),
            gateway_secret=secret,
        )


def test_actor_revoked_before_worker_and_audit_failure(setup, monkeypatch):
    root, config, plan = setup
    calls = []

    def authorize(subject, connection):
        calls.append((subject, connection))
        if len(calls) > 1:
            raise ValueError("revoked")

    def forbidden(*args, **kwargs):
        pytest.fail("A revoked actor must not collect cloud metadata")

    monkeypatch.setattr("datavouch.web.runs.subprocess.run", forbidden)
    store = RunStore(root, config, authorize)
    try:
        key = store.submit(plan, "test", "writer")
        finish(store)
        assert calls == [("writer", "test"), ("writer", "test")]
        assert store.get(key)["state"] == "ERROR"
    finally:
        store.close()
    fixture_worker(monkeypatch)
    store = RunStore(root, config)
    original = store.audit

    def broken(action, *args):
        if action != "run_submitted":
            raise OSError("fixture disk error")
        return original(action, *args)

    monkeypatch.setattr(store, "audit", broken)
    try:
        key = store.submit({**plan, "id": "audit-failure"}, "test")
        finish(store)
        assert store.get(key)["state"] == "ERROR"
        assert "audit" in store.get(key)["message"]
    finally:
        store.close()


@pytest.mark.parametrize(
    "metric,unit",
    [
        ("runtime", "ms"),
        ("slot_time", "slot_ms"),
        ("processed_bytes", "bytes"),
        ("billed_bytes", "bytes"),
    ],
)
def test_metric_selection_exports_matching_policy(setup, metric, unit):
    _, config, plan = setup
    app = create_app(ROOT / "examples/viewer.json", PASSWORD, connections=config)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.auth = ("datavouch", PASSWORD)
        form = browser_form(client, plan)
        form.update(action="download", metric=metric)
        response = client.post("/experiments/new", data=form)
        assert response.status_code == 200
        policy = response.json()["policy"]["metric"]
        assert policy == {"name": metric, "unit": unit, "direction": "lower"}
