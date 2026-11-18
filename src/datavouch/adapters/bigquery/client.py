"""Optional SDK transport. Import and authentication happen only on explicit live calls."""

import time
from datetime import UTC, datetime

from datavouch.adapters.bigquery.collector import collect_rows
from datavouch.adapters.bigquery.models import Collection, CollectionConfig, CollectionError
from datavouch.adapters.bigquery.queries import metadata_query


def collect_live(config: CollectionConfig) -> Collection:
    """Run a bounded metadata SELECT. Caller must authorize cloud access and query charges."""
    config.validate_live_window(datetime.now(UTC))
    try:
        from google.api_core.exceptions import Forbidden, GoogleAPICallError, Unauthorized
        from google.auth.exceptions import DefaultCredentialsError, RefreshError
        from google.cloud import bigquery
    except ImportError:
        raise CollectionError("Install datavouch[bigquery] to enable live collection") from None
    deadline = time.monotonic() + config.timeout_seconds
    try:
        with bigquery.Client(project=config.project, location=config.location) as client:
            job_config = bigquery.QueryJobConfig(
                use_legacy_sql=False,
                use_query_cache=False,
                maximum_bytes_billed=config.maximum_bytes_billed,
                job_timeout_ms=config.timeout_seconds * 1000,
                query_parameters=[
                    bigquery.ScalarQueryParameter("location", "STRING", config.location),
                    bigquery.ScalarQueryParameter("start_time", "TIMESTAMP", config.start),
                    bigquery.ScalarQueryParameter("end_time", "TIMESTAMP", config.end),
                    bigquery.ArrayQueryParameter("job_ids", "STRING", list(config.job_ids)),
                    bigquery.ScalarQueryParameter("row_limit", "INT64", len(config.job_ids) + 1),
                ],
            )
            job = client.query(
                metadata_query(config),
                job_config=job_config,
                location=config.location,
                retry=None,
                job_retry=None,
                timeout=config.timeout_seconds,
            )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            rows = job.result(
                timeout=remaining,
                page_size=101,
                max_results=len(config.job_ids) + 1,
                retry=None,
                job_retry=None,
            )
            return collect_rows((dict(row.items()) for row in rows), config, source="bigquery")
    except (Forbidden, Unauthorized):
        raise CollectionError(
            "BigQuery access denied. Check jobs.create and jobs.listAll permissions"
        ) from None
    except (DefaultCredentialsError, RefreshError):
        raise CollectionError(
            "Google Application Default Credentials are unavailable or invalid"
        ) from None
    except TimeoutError:
        raise CollectionError(
            "Metadata query timed out. Check its status before retrying"
        ) from None
    except GoogleAPICallError:
        raise CollectionError(
            "BigQuery metadata request failed. Check region, byte budget and service status"
        ) from None
