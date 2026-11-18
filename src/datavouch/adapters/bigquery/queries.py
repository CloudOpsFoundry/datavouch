"""Fixed read-only SQL. Only validated identifiers are interpolated."""

from datavouch.adapters.bigquery.models import CollectionConfig


def metadata_query(config: CollectionConfig) -> str:
    """Select minimal job evidence with partition pruning and explicit row bounds."""
    # Identifiers pass strict allowlists in immutable CollectionConfig. Values use parameters.
    return f"""SELECT
  project_id, @location AS location, job_id, creation_time, start_time, end_time,
  job_type, statement_type, parent_job_id, state, cache_hit,
  error_result.reason AS failure_reason,
  total_slot_ms, total_bytes_processed, total_bytes_billed,
  query_info.query_hashes.normalized_literals AS fingerprint
FROM `{config.project}.region-{config.location}.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE creation_time >= @start_time AND creation_time < @end_time
  AND job_id IN UNNEST(@job_ids)
ORDER BY creation_time, job_id
LIMIT @row_limit"""  # nosec B608
