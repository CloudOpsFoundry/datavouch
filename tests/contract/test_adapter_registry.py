"""Provider-independent extension contracts and existing BigQuery compatibility."""

import builtins
import copy
import importlib.util
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from datavouch.adapters.bigquery.adapter import BigQueryAdapter
from datavouch.adapters.bigquery.files import load_config, load_fixture
from datavouch.adapters.contracts import AdapterError, Exclusion
from datavouch.adapters.registry import Registry, builtin_registry, render
from datavouch.analysis.comparison import compare
from datavouch.core.models import (
    Baseline,
    Change,
    Evidence,
    Experiment,
    Measurement,
    Metric,
    Policy,
    Status,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples/adapters"


@pytest.fixture
def connector():
    return json.loads((EXAMPLES / "bigquery_connector.json").read_text())


@pytest.fixture
def batch(connector):
    return BigQueryAdapter().collect(
        connector["config"], fixture=ROOT / "examples/bigquery/jobs.json", live=False
    )


def test_bigquery_legacy_parity(connector, batch):
    previous = load_fixture(
        ROOT / "examples/bigquery/jobs.json",
        load_config(ROOT / "examples/bigquery/collection_config.json"),
    )
    assert batch.observations == tuple(j.observation for j in previous.jobs)
    assert batch.eligible == previous.eligible
    report = builtin_registry().collect(connector, fixture=ROOT / "examples/bigquery/jobs.json")
    assert json.loads(render(report)) == json.loads(
        (EXAMPLES / "expected_bigquery.json").read_text()
    )


def test_sdk_not_imported_for_registration_or_fixture(monkeypatch, connector):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith("google"):
            raise AssertionError("Unexpected SDK import")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    registry = builtin_registry()
    assert registry.list()[0].name == "bigquery"
    assert registry.collect(connector, fixture=ROOT / "examples/bigquery/jobs.json")["eligible"]


def test_explicit_live_bridge(monkeypatch, connector):
    from datavouch.adapters.bigquery import client

    collection = load_fixture(
        ROOT / "examples/bigquery/jobs.json",
        load_config(ROOT / "examples/bigquery/collection_config.json"),
    )
    transport = Mock(return_value=collection)
    monkeypatch.setattr(client, "collect_live", transport)
    report = builtin_registry().collect(connector, live=True)
    assert report["mode"] == "live"
    assert report["eligible"] is True
    transport.assert_called_once()


@pytest.mark.parametrize("kind", ["missing", "cached", "failed", "fingerprints"])
def test_bigquery_incomplete_evidence(connector, tmp_path, kind):
    rows = json.loads((ROOT / "examples/bigquery/jobs.json").read_text())
    if kind == "missing":
        rows.pop()
    elif kind == "cached":
        rows[0]["cache_hit"] = True
    elif kind == "failed":
        rows[0]["failure_reason"] = "invalidQuery"
    else:
        rows[0]["fingerprint"] = "abcdef"
    path = tmp_path / "rows.json"
    path.write_text(json.dumps(rows))
    report = builtin_registry().collect(connector, fixture=path)
    assert report["eligible"] is False
    assert len(report["requested_ids"]) == (
        len(report["observations"]) + len(report["missing_ids"]) + len(report["exclusions"])
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("adapter", "unregistered"),
        ("adapter", []),
        ("api_version", "adapter-2"),
        ("config_version", "wrong"),
        ("config", []),
    ],
)
def test_incompatible_connector_rejected_before_plugin(connector, field, value):
    adapter = Mock(info=BigQueryAdapter.info)
    registry = Registry()
    registry.register(adapter)
    connector[field] = value
    with pytest.raises(AdapterError):
        registry.collect(connector, fixture=Path("unused"))
    adapter.collect.assert_not_called()
    adapter.validate_config.assert_not_called()


@pytest.mark.parametrize(
    "fixture,live", [(None, False), (Path("x"), True), ("x", False), (None, 1)]
)
def test_source_selection(connector, fixture, live):
    with pytest.raises(AdapterError):
        builtin_registry().collect(connector, fixture=fixture, live=live)


def test_config_error_never_collects(connector):
    adapter = Mock(info=BigQueryAdapter.info)
    adapter.validate_config.side_effect = ValueError("credential-private-detail")
    registry = Registry()
    registry.register(adapter)
    with pytest.raises(AdapterError, match="validation failed") as error:
        registry.collect(connector, fixture=Path("x"))
    assert "credential-private" not in str(error.value)
    adapter.collect.assert_not_called()


def test_adapter_exception_redacted(connector):
    adapter = Mock(info=BigQueryAdapter.info)
    adapter.collect.side_effect = RuntimeError("provider-secret")
    registry = Registry()
    registry.register(adapter)
    with pytest.raises(AdapterError) as error:
        registry.collect(connector, fixture=Path("x"))
    assert "provider-secret" not in str(error.value)


@pytest.mark.parametrize("bad_result", [None, {}, "unexpected"])
def test_wrong_result_type(connector, bad_result):
    adapter = Mock(info=BigQueryAdapter.info)
    adapter.collect.return_value = bad_result
    registry = Registry()
    registry.register(adapter)
    with pytest.raises(AdapterError):
        registry.collect(connector, fixture=Path("x"))


def test_undeclared_metric_rejected(connector, batch):
    observation = replace(
        batch.observations[0], measurements=(Measurement(Metric("runtime", "s"), 1),)
    )
    adapter = Mock(info=BigQueryAdapter.info)
    adapter.collect.return_value = replace(
        batch, observations=(observation, *batch.observations[1:])
    )
    registry = Registry()
    registry.register(adapter)
    with pytest.raises(AdapterError):
        registry.collect(connector, fixture=Path("x"))


def test_configuration_isolated(connector, batch):
    before = copy.deepcopy(connector)
    adapter = Mock(info=BigQueryAdapter.info)
    adapter.validate_config.side_effect = lambda c: c.clear()
    adapter.collect.return_value = batch
    registry = Registry()
    registry.register(adapter)
    registry.collect(connector, fixture=Path("x"))
    assert connector == before
    assert adapter.collect.call_args.args[0] == before["config"]


def test_registration_boundaries():
    registry = builtin_registry()
    with pytest.raises(AdapterError, match="already"):
        registry.register(BigQueryAdapter())
    with pytest.raises(AdapterError, match="Incompatible"):
        registry.register(Mock(info=replace(BigQueryAdapter.info, api_version="adapter-2")))
    with pytest.raises(AdapterError):
        registry.register(object())
    with pytest.raises(AdapterError):
        registry.register(Mock(info=BigQueryAdapter.info, collect=None))
    assert len(registry.list()) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "Bad Name"),
        ("version", "v1"),
        ("version", "01.0.0"),
        ("api_version", ""),
        ("config_version", "x" * 65),
        ("modes", []),
        ("modes", ("live", "live")),
        ("modes", ("write",)),
        ("metrics", []),
        ("metrics", (Metric("runtime", "ms"), Metric("runtime", "s"))),
    ],
)
def test_descriptor_validation(field, value):
    with pytest.raises(AdapterError):
        replace(BigQueryAdapter.info, **{field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("requested_ids", ()),
        ("requested_ids", ("x", "x")),
        ("requested_ids", tuple(str(i) for i in range(101))),
        ("requested_ids", ("",)),
        ("missing_ids", ("unexpected",)),
        ("exclusions", []),
        ("eligible", 1),
        ("notes", ()),
        ("notes", ("x" * 501,)),
    ],
)
def test_batch_validation(batch, field, value):
    with pytest.raises(ValueError):
        replace(batch, **{field: value})


def test_missing_cannot_be_eligible(batch):
    with pytest.raises(AdapterError):
        replace(
            batch,
            observations=batch.observations[1:],
            missing_ids=(batch.observations[0].execution.id,),
        )


def test_failed_cached_and_empty_measurements_excluded(batch):
    observation = batch.observations[0]
    for changed in (
        replace(observation.execution, successful=False),
        replace(observation.execution, cached=True),
    ):
        with pytest.raises(AdapterError):
            replace(
                batch,
                observations=(replace(observation, execution=changed), *batch.observations[1:]),
            )
    with pytest.raises(AdapterError):
        replace(
            batch, observations=(replace(observation, measurements=()), *batch.observations[1:])
        )


@pytest.mark.parametrize("reasons", [(), [], ("",), ("x" * 501,), ("x",) * 17])
def test_exclusion_validation(reasons):
    with pytest.raises(AdapterError):
        Exclusion("id", reasons)


def test_independent_example_uses_unchanged_comparison_engine():
    spec = importlib.util.spec_from_file_location(
        "contributor_adapter", EXAMPLES / "local_metrics.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    adapter = module.LocalMetricsAdapter()
    registry = Registry()
    registry.register(adapter)
    batches = []
    for name in ("baseline", "candidate"):
        connector = json.loads((EXAMPLES / f"{name}_connector.json").read_text())
        report = registry.collect(connector, fixture=EXAMPLES / f"{name}.json")
        assert report["eligible"]
        batches.append(
            adapter.collect(connector["config"], fixture=EXAMPLES / f"{name}.json", live=False)
        )
    experiment = Experiment(
        "extension-test",
        Baseline(batches[0].observations),
        batches[1].observations,
        Change("rewrite", "Synthetic change"),
        Evidence("fixture", "Same synthetic workload"),
    )
    result = compare(experiment, Policy(Metric("runtime", "ms"), 5))
    assert result.results[0].status == Status.PASS
    assert result.results[0].baseline_mean == 100
    assert result.results[0].candidate_mean == 80
