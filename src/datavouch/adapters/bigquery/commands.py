"""CLI orchestration for optional BigQuery collection."""

import sys
from pathlib import Path

from datavouch.adapters.bigquery.files import load_config, load_fixture, render_collection
from datavouch.adapters.bigquery.models import CollectionError


def collect_command(config_path: Path, fixture: Path | None, live: bool) -> int:
    """Print only sanitized evidence or a safe diagnostic."""
    try:
        config = load_config(config_path)
        if live:
            from datavouch.adapters.bigquery.client import collect_live

            result = collect_live(config)
        elif fixture is not None:
            result = load_fixture(fixture, config)
        else:
            raise CollectionError("Select a fixture or explicitly enable live collection")
        output = render_collection(result)
    except CollectionError as error:
        print(str(error), file=sys.stderr)
        return 2
    except (ValueError, OSError, TypeError, OverflowError, RecursionError):
        print("Invalid or unreadable BigQuery input. Check the documented schema.", file=sys.stderr)
        return 2
    print(output, end="")
    return 0 if result.eligible else 3
