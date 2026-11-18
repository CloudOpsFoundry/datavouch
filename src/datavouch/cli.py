"""Command line interface."""

import argparse
import sys
from pathlib import Path

from datavouch import __version__
from datavouch.analysis.comparison import compare
from datavouch.core.configuration import load
from datavouch.core.models import Status
from datavouch.reports.json_report import render


def main(argv: list[str] | None = None) -> int:
    """Run offline comparison. Exit 0=pass, 1=fail, 2=error, 3=unknown metric."""
    parser = argparse.ArgumentParser(description="DataVouch: Measure. Validate. Trust.")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")
    comparison = subparsers.add_parser(
        "compare", help="Compare a synthetic or authorised JSON input"
    )
    comparison.add_argument("input", type=Path)
    verification = subparsers.add_parser(
        "verify", help="Verify required correctness and reliability checks"
    )
    verification.add_argument("input", type=Path)
    financial = subparsers.add_parser(
        "finance", help="Assess supplied pricing and billing evidence"
    )
    financial.add_argument("input", type=Path)
    gate = subparsers.add_parser("gate", help="Apply an explicit offline CI verification policy")
    gate.add_argument("input", type=Path)
    gate.add_argument("--policy", type=Path, required=True)
    gate.add_argument("--output-dir", type=Path)
    server = subparsers.add_parser("serve", help="Start the authenticated local report viewer")
    server.add_argument("catalog", type=Path)
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--allow-raw-reports", action="store_true")
    subparsers.add_parser("adapters", help="List registered adapter versions and capabilities")
    generic = subparsers.add_parser("collect", help="Collect through a versioned connector")
    generic.add_argument("config", type=Path)
    generic_source = generic.add_mutually_exclusive_group(required=True)
    generic_source.add_argument("--fixture", type=Path)
    generic_source.add_argument("--live", action="store_true")
    collection = subparsers.add_parser("collect-bigquery", help="Collect bounded BigQuery metadata")
    collection.add_argument("config", type=Path)
    source = collection.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", type=Path, help="Offline synthetic metadata JSON")
    source.add_argument(
        "--live", action="store_true", help="Run an authorized billable metadata query"
    )
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "adapters":
        from datavouch.adapters.commands import adapters_command

        return adapters_command()
    if args.command == "collect":
        from datavouch.adapters.commands import collect_command as generic_collect

        return generic_collect(args.config, args.fixture, args.live)
    if args.command == "gate":
        from datavouch.workflow.commands import gate_command

        return gate_command(args.input, args.policy, args.output_dir)
    if args.command == "serve":
        from datavouch.web.commands import serve_command

        return serve_command(args.catalog, args.port, args.allow_raw_reports)
    if args.command == "finance":
        from datavouch.financial.commands import finance_command

        return finance_command(args.input)
    if args.command == "verify":
        from datavouch.verification.commands import verify_command

        return verify_command(args.input)
    if args.command == "collect-bigquery":
        from datavouch.adapters.bigquery.commands import collect_command

        return collect_command(args.config, args.fixture, args.live)
    try:
        experiment, policy = load(args.input)
        report = compare(experiment, policy)
        output = render(report)
    except (ValueError, OSError, TypeError, OverflowError, RecursionError):
        print(
            "Invalid or unreadable comparison input. Check the documented schema.", file=sys.stderr
        )
        return 2
    print(output, end="")
    return {Status.PASS: 0, Status.FAIL: 1, Status.UNKNOWN: 3}[report.results[0].status]
