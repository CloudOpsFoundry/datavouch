"""Contributor example: explicit local runtime fixtures, no network or SDK."""

from pathlib import Path

from datavouch.adapters.contracts import API_VERSION, AdapterInfo, ObservationBatch, identifiers
from datavouch.core.configuration import read_json
from datavouch.core.models import Execution, Measurement, Metric, Observation, Workload


class LocalMetricsAdapter:
    info = AdapterInfo(
        "local-metrics",
        "1.0.0",
        API_VERSION,
        "local-metrics-config-1",
        ("fixture",),
        (Metric("runtime", "ms"),),
    )

    def validate_config(self, config: object) -> None:
        if not isinstance(config, dict) or set(config) != {"workload", "execution_ids"}:
            raise ValueError("Expected workload and execution IDs")
        if not isinstance(config["workload"], dict) or not isinstance(
            config["execution_ids"], list
        ):
            raise ValueError("Expected workload object and execution ID array")
        Workload(**config["workload"])
        identifiers(tuple(config["execution_ids"]))
        if not config["execution_ids"]:
            raise ValueError("Select at least one execution")

    def collect(self, config: object, *, fixture: Path | None, live: bool) -> ObservationBatch:
        self.validate_config(config)
        if not isinstance(config, dict) or fixture is None or live:
            raise ValueError("Only explicit offline fixtures are supported")
        workload = Workload(**config["workload"])
        requested = tuple(config["execution_ids"])
        rows = read_json(fixture)
        if not isinstance(rows, list) or len(rows) > len(requested):
            raise ValueError("Expected bounded runtime rows")
        observations = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"execution_id", "runtime_ms"}:
                raise ValueError("Unexpected fixture fields")
            if row["execution_id"] not in requested:
                raise ValueError("Unrequested execution")
            observations.append(
                Observation(
                    workload,
                    Execution(row["execution_id"]),
                    (Measurement(Metric("runtime", "ms"), row["runtime_ms"]),),
                )
            )
        seen = {o.execution.id for o in observations}
        missing = tuple(sorted(set(requested) - seen))
        return ObservationBatch(
            requested,
            tuple(observations),
            missing,
            (),
            not missing,
            ("Synthetic fixture values; no live platform or correctness validation.",),
        )
