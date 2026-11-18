"""Copy and adapt this contract template for an explicitly trusted adapter.

Run: python -m pytest examples/adapters/test_contract_template.py
"""

import json
from pathlib import Path

import pytest
from local_metrics import LocalMetricsAdapter

from datavouch.adapters.contracts import AdapterError
from datavouch.adapters.registry import Registry, render

HERE = Path(__file__).parent


@pytest.fixture
def registry():
    registry = Registry()
    registry.register(LocalMetricsAdapter())
    return registry


@pytest.fixture
def connector():
    return json.loads((HERE / "baseline_connector.json").read_text())


def test_offline_determinism(registry, connector):
    first = registry.collect(connector, fixture=HERE / "baseline.json")
    second = registry.collect(connector, fixture=HERE / "baseline.json")
    assert first["eligible"] is True
    assert render(first) == render(second)
    assert len(first["observations"]) == 3


def test_explicit_source_required(registry, connector):
    with pytest.raises(AdapterError):
        registry.collect(connector)


def test_unsupported_live_rejected(registry, connector):
    with pytest.raises(AdapterError, match="does not support"):
        registry.collect(connector, live=True)


def test_missing_is_not_eligible(registry, connector, tmp_path):
    fixture = tmp_path / "missing.json"
    fixture.write_text("[]")
    report = registry.collect(connector, fixture=fixture)
    assert report["eligible"] is False
    assert report["missing_ids"] == connector["config"]["execution_ids"]


def test_config_version_rejected(registry, connector):
    connector["config_version"] = "unsupported"
    with pytest.raises(AdapterError, match="version"):
        registry.collect(connector, fixture=HERE / "baseline.json")


def test_unrequested_record_rejected(registry, connector, tmp_path):
    fixture = tmp_path / "unexpected.json"
    fixture.write_text('[{"execution_id":"unrequested","runtime_ms":1}]')
    with pytest.raises(AdapterError):
        registry.collect(connector, fixture=fixture)
