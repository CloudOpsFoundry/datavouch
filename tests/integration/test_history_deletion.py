"""Admin bulk retention deletes durable evidence, never unauthorized or running runs."""

import html
import json
import re
import sqlite3

import pytest
from fastapi.testclient import TestClient
from test_product_workspace import PASSWORD, SECRET, application, headers, policy_file, pricing
from test_web_runs import browser_form, finish, fixture_worker, setup

from datavouch.web.runs import RunBusy, RunStore

__all__ = ["setup"]


def fields(response):
    return {
        name: html.unescape(value)
        for name, value in re.findall(
            r'type="hidden" name="([^"]+)" value="([^"]*)"', response.text
        )
    }


def seed(setup, monkeypatch):
    root, config, plan = setup
    fixture_worker(monkeypatch)
    store = RunStore(root, config)
    keys = []
    try:
        for index in range(2):
            keys.append(store.submit({**plan, "id": f"retention-{index}"}, "test"))
            finish(store)
            store.assess_financial(keys[-1], pricing())
    finally:
        store.close()
    return root, config, plan, keys


@pytest.mark.parametrize("mode,count", [("selected", 1), ("all", 2)])
def test_bulk_deletes_disk_history_and_stays_deleted_after_restart(setup, monkeypatch, mode, count):
    root, config, _, keys = seed(setup, monkeypatch)
    with TestClient(
        application(root, config), base_url="http://127.0.0.1", follow_redirects=False
    ) as client:
        client.auth = ("datavouch", PASSWORD)
        csrf = fields(client.get("/runs?q=retention-0"))["csrf"]
        values = {"csrf": csrf, "mode": mode, "run_" + keys[0]: "yes"}
        preview = client.post("/runs/deletion-preview", data=values)
        assert preview.status_code == 200
        assert all((root / key).exists() for key in keys)  # Preview is never deletion.
        confirmation = {**fields(preview), "confirmed": "yes"}
        assert len(json.loads(confirmation["selection"])) == count
        assert (
            client.post("/runs/delete-history", data={**confirmation, "confirmed": ""}).status_code
            == 400
        )
        assert client.post("/runs/delete-history", data=confirmation).status_code == 303
        for key in keys[:count]:
            assert not (root / key).exists()
            assert client.get("/runs/" + key).status_code == 404
            assert client.get("/runs/" + key + "/report.json").status_code == 404
        assert client.post("/runs/delete-history", data=confirmation).status_code == 409
        deleted = [r for r in client.get("/audit.json").json() if r["action"] == "run_deleted"]
        assert len(deleted) == count
    restored = RunStore(root, config)
    try:
        assert len(restored.list_runs()) == 2 - count
    finally:
        restored.close()
    with sqlite3.connect(root / ".owner.sqlite") as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [
            ("owner",)
        ]
        assert db.execute("SELECT count(*) FROM owner").fetchone() == (0,)


def test_snapshot_proof_excludes_new_runs_and_rejects_tampering(setup, monkeypatch):
    root, config, plan, keys = seed(setup, monkeypatch)
    with TestClient(
        application(root, config), base_url="http://127.0.0.1", follow_redirects=False
    ) as client:
        client.auth = ("datavouch", PASSWORD)
        values = {**fields(client.get("/runs")), "mode": "all"}
        preview = client.post("/runs/deletion-preview", data=values)
        confirmation = {**fields(preview), "confirmed": "yes"}
        bad = {**confirmation, "selection": json.dumps([keys[0]])}
        assert client.post("/runs/delete-history", data=bad).status_code == 403
        bad = {**confirmation, "csrf": "wrong"}
        assert client.post("/runs/delete-history", data=bad).status_code == 403
        assert (
            client.post(
                "/runs/delete-history",
                data=confirmation,
                headers={"Origin": "https://other.example"},
            ).status_code
            == 403
        )
        new = client.post(
            "/experiments/new", data=browser_form(client, {**plan, "id": "after-preview"})
        )
        assert new.status_code == 303
        assert client.post("/runs/delete-history", data=confirmation).status_code == 303
        assert client.get(new.headers["location"]).status_code == 200


def test_roles_scope_and_revocation(setup, monkeypatch):
    root, config, _, keys = seed(setup, monkeypatch)
    policy = policy_file(root)
    app = application(root, config, gateway_config=policy, gateway_secret=SECRET)
    with TestClient(
        app,
        base_url="https://datavouch.example.test",
        client=("127.0.0.1", 12345),
        follow_redirects=False,
    ) as client:
        for user in ("reader", "writer"):
            client.headers.update(headers(user))
            assert "Delete selected history" not in client.get("/runs").text
            assert client.post("/runs/deletion-preview", data={}).status_code == 403
            assert client.post("/runs/delete-history", data={}).status_code == 403
        client.headers.update(headers("outsider"))
        csrf = fields(client.get("/runs"))["csrf"]
        assert (
            client.post(
                "/runs/deletion-preview",
                data={"csrf": csrf, "mode": "selected", "run_" + keys[0]: "yes"},
            ).status_code
            == 404
        )
        assert (
            client.post("/runs/deletion-preview", data={"csrf": csrf, "mode": "all"}).status_code
            == 400
        )
        client.headers.update(headers("owner"))
        preview = client.post(
            "/runs/deletion-preview", data={**fields(client.get("/runs")), "mode": "all"}
        )
        confirmation = {**fields(preview), "confirmed": "yes"}
        changed = json.loads(policy.read_text())
        changed["principals"]["owner"]["connections"] = []
        policy.write_text(json.dumps(changed))
        assert client.post("/runs/delete-history", data=confirmation).status_code == 409
        assert all((root / key).exists() for key in keys)


def test_preflight_prevents_partial_deletion_for_active_or_unknown_runs(setup, monkeypatch):
    root, config, _, keys = seed(setup, monkeypatch)
    store = RunStore(root, config)
    try:
        store.records[keys[1]]["state"] = "RUNNING"
        with pytest.raises(RunBusy):
            store.delete_many(keys)
        assert all((root / key).exists() for key in keys)
        store.records[keys[1]]["state"] = "COMPLETED"
        with pytest.raises(KeyError):
            store.delete_many([keys[0], "0" * 64])
        with pytest.raises(KeyError):
            store.delete_many(keys, permits=lambda _: False)
        assert all((root / key).exists() for key in keys)
        with pytest.raises(ValueError):
            store.delete_many([keys[0], keys[0]])
    finally:
        store.close()


def test_delete_all_respects_connection_scope(setup, monkeypatch):
    root, config, plan, keys = seed(setup, monkeypatch)
    connections = json.loads(config.read_text())
    connections["connections"].append({**connections["connections"][0], "id": "other"})
    config.write_text(json.dumps(connections))
    store = RunStore(root, config)
    hidden = store.submit({**plan, "id": "another-connection"}, "other")
    finish(store)
    store.close()
    policy = policy_file(root)
    with TestClient(
        application(root, config, gateway_config=policy, gateway_secret=SECRET),
        base_url="https://datavouch.example.test",
        client=("127.0.0.1", 12345),
        follow_redirects=False,
    ) as client:
        client.headers.update(headers("owner"))
        page = client.get("/runs")
        assert hidden not in page.text
        preview = client.post("/runs/deletion-preview", data={**fields(page), "mode": "all"})
        assert set(json.loads(fields(preview)["selection"])) == set(keys)
        assert (
            client.post(
                "/runs/delete-history", data={**fields(preview), "confirmed": "yes"}
            ).status_code
            == 303
        )
        assert (root / hidden).is_dir()
        assert all(not (root / key).exists() for key in keys)


def test_filesystem_failure_is_reported_and_retryable(setup, monkeypatch):
    root, config, _, keys = seed(setup, monkeypatch)
    with TestClient(
        application(root, config), base_url="http://127.0.0.1", follow_redirects=False
    ) as client:
        client.auth = ("datavouch", PASSWORD)
        preview = client.post(
            "/runs/deletion-preview", data={**fields(client.get("/runs")), "mode": "all"}
        )
        confirmation = {**fields(preview), "confirmed": "yes"}
        with monkeypatch.context() as patch:

            def fail(*args):
                raise OSError("private filesystem detail")

            patch.setattr("datavouch.web.runs.shutil.rmtree", fail)
            response = client.post("/runs/delete-history", data=confirmation)
            assert response.status_code == 409
            assert "Reload history" in response.text
            assert "private filesystem" not in response.text
            assert all((root / key).exists() for key in keys)
            events = client.get("/audit.json").json()
            assert not any(e["action"] == "run_deleted" for e in events)
        assert client.post("/runs/delete-history", data=confirmation).status_code == 303


@pytest.mark.parametrize("selection", ["null", "[]", "[1]", '["../"]', '["x"]', "{}", "not-json"])
def test_invalid_confirmation_never_deletes(setup, monkeypatch, selection):
    root, config, _, keys = seed(setup, monkeypatch)
    with TestClient(application(root, config), base_url="http://127.0.0.1") as client:
        client.auth = ("datavouch", PASSWORD)
        values = {
            **fields(client.get("/runs")),
            "selection": selection,
            "proof": "invalid",
            "confirmed": "yes",
        }
        assert client.post("/runs/delete-history", data=values).status_code == 400
        assert all((root / key).exists() for key in keys)


def test_confirmation_cannot_delete_recreated_same_plan(setup, monkeypatch):
    root, config, plan, keys = seed(setup, monkeypatch)
    captured = []
    original = RunStore.get

    def get(store, key):
        captured.append(store)
        return original(store, key)

    monkeypatch.setattr(RunStore, "get", get)
    with TestClient(
        application(root, config), base_url="http://127.0.0.1", follow_redirects=False
    ) as client:
        client.auth = ("datavouch", PASSWORD)
        preview = client.post(
            "/runs/deletion-preview",
            data={**fields(client.get("/runs")), "mode": "selected", "run_" + keys[0]: "yes"},
        )
        confirmation = {**fields(preview), "confirmed": "yes"}
        store = captured[-1]
        store.delete(keys[0])
        recreated = store.submit({**plan, "id": "retention-0"}, "test")
        finish(store)
        assert recreated == keys[0]  # Same deterministic plan ID, different stored instance.
        assert client.post("/runs/delete-history", data=confirmation).status_code == 403
        assert (root / recreated).exists()
