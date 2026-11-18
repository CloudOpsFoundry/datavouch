import json
from pathlib import Path

import pytest

from datavouch.core.configuration import load

EXAMPLE = Path(__file__).resolve().parents[2] / "examples/bigquery/comparison.json"


def test_valid_fixture():
    experiment, policy = load(EXAMPLE)
    assert len(experiment.candidate) == 3
    assert policy.minimum_samples == 3


@pytest.mark.parametrize(
    "text",
    [
        "{}",
        "[]",
        '{"experiment":{},"experiment":{}}',
        "not json",
        '{"experiment":{},"policy":{},"extra":1}',
    ],
)
def test_invalid_json(tmp_path, text):
    path = tmp_path / "input.json"
    path.write_text(text)
    with pytest.raises(ValueError):
        load(path)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["experiment"].update(candidate={}),
        lambda d: d["experiment"]["candidate"][0].update(measurements={}),
        lambda d: d["policy"].update(minimum_samples=False),
        lambda d: d["policy"]["metric"].update(direction="invalid"),
        lambda d: d["experiment"]["candidate"][0]["measurements"][0].update(value=float("nan")),
    ],
)
def test_bad_fields(tmp_path, mutation):
    data = json.loads(EXAMPLE.read_text())
    mutation(data)
    path = tmp_path / "input.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load(path)


def test_bounded_input(tmp_path):
    path = tmp_path / "large.json"
    path.write_bytes(b" " * 5_000_001)
    with pytest.raises(ValueError, match="5 MB"):
        load(path)
