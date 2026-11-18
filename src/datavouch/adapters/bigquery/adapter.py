"""Versioned bridge to the existing bounded BigQuery collector."""

from pathlib import Path

from datavouch.adapters.bigquery.files import decode_config, load_fixture
from datavouch.adapters.contracts import API_VERSION, AdapterInfo, Exclusion, ObservationBatch
from datavouch.core.models import Metric


class BigQueryAdapter:
    info = AdapterInfo(
        "bigquery",
        "1.0.0",
        API_VERSION,
        "bigquery-config-0.1",
        ("fixture", "live"),
        (
            Metric("runtime", "ms"),
            Metric("slot_time", "slot_ms"),
            Metric("processed_bytes", "bytes"),
            Metric("billed_bytes", "bytes"),
        ),
    )

    def validate_config(self, config: object) -> None:
        decode_config(config)

    def collect(self, config: object, *, fixture: Path | None, live: bool) -> ObservationBatch:
        scope = decode_config(config)
        if live and fixture is None:
            from datavouch.adapters.bigquery.client import collect_live

            result = collect_live(scope)
        elif not live and fixture is not None:
            result = load_fixture(fixture, scope)
        else:
            raise ValueError("Select exactly one source")
        prefix = f"{scope.project}/{scope.location}/"
        return ObservationBatch(
            tuple(prefix + key for key in scope.job_ids),
            tuple(job.observation for job in result.jobs if job.observation is not None),
            tuple(prefix + key for key in result.missing_job_ids),
            tuple(
                Exclusion(prefix + job.job_id, job.issues)
                for job in result.jobs
                if job.observation is None
            ),
            result.eligible,
            (
                "Eligibility does not establish comparability, correctness or financial impact.",
                "Workload identity and input snapshot are caller assertions.",
                "Missing jobs, exclusions or mixed fingerprints make the batch ineligible.",
            ),
        )
