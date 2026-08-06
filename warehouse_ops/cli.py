from __future__ import annotations

import argparse
from pathlib import Path

from .io import (
    CsvFormatError,
    read_movements_csv,
    read_movements_csv_with_quarantine,
    read_product_metadata_csv,
    read_stock_csv,
    write_issues_csv,
    write_movement_quarantine_csv,
    write_report_json,
)
from .quarantine import quarantine_rows_to_issues
from .reconciliation import ReconciliationReport, reconcile_stock
from .routing import RoutingConfigError, RoutingRules
from .service import sync_reconciliation_tasks
from .task_store import SQLiteTaskStore


def _non_negative_int(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return value


def _rate(raw: str) -> float:
    value = float(raw)
    if not 0 <= value <= 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="warehouse-reconcile",
        description="Reconcile stock files and optionally synchronize review tasks.",
    )
    parser.add_argument("--opening", required=True, help="CSV with sku,quantity columns")
    parser.add_argument(
        "--movements",
        required=True,
        help="CSV with event_id,sku,movement_type,quantity columns",
    )
    parser.add_argument("--counted", help="Optional physical count CSV with sku,quantity columns")
    parser.add_argument(
        "--metadata",
        help="Optional CSV with sku,floor,shelf,critical_stock columns",
    )
    parser.add_argument(
        "--output",
        default="reconciliation-report.json",
        help="JSON report path (default: reconciliation-report.json)",
    )
    parser.add_argument(
        "--issues-output",
        help="Optional CSV path for prioritized issues requiring operational review",
    )
    parser.add_argument(
        "--movement-quarantine-output",
        help=(
            "Optional CSV path for invalid movement rows. When provided, valid rows "
            "continue to reconciliation while invalid rows are excluded and recorded."
        ),
    )
    parser.add_argument(
        "--max-quarantined-rows",
        type=_non_negative_int,
        help=(
            "Abort with exit code 2 when quarantined movement rows exceed this count. "
            "Requires --movement-quarantine-output."
        ),
    )
    parser.add_argument(
        "--max-quarantined-rate",
        type=_rate,
        help=(
            "Abort with exit code 2 when the quarantined share exceeds this 0-1 rate. "
            "Requires --movement-quarantine-output."
        ),
    )
    parser.add_argument(
        "--task-database",
        help=(
            "Optional SQLite database path. When provided, reconciliation and "
            "quarantine issues are synchronized into persistent warehouse tasks."
        ),
    )
    parser.add_argument(
        "--routing-config",
        help=(
            "Optional CSV with issue_code,assignee,message_contains rules. "
            "Used only when --task-database is provided."
        ),
    )
    return parser


def _quarantine_gate_error(
    *,
    valid_count: int,
    quarantined_count: int,
    max_rows: int | None,
    max_rate: float | None,
) -> str | None:
    if max_rows is not None and quarantined_count > max_rows:
        return (
            f"quarantined row count {quarantined_count} exceeds allowed maximum "
            f"{max_rows}"
        )

    total_count = valid_count + quarantined_count
    quarantine_rate = quarantined_count / total_count if total_count else 0.0
    if max_rate is not None and quarantine_rate > max_rate:
        return (
            f"quarantined row rate {quarantine_rate:.2%} exceeds allowed maximum "
            f"{max_rate:.2%}"
        )
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.routing_config and not args.task_database:
        print("Import failed: --routing-config requires --task-database.")
        return 2

    quality_gate_requested = (
        args.max_quarantined_rows is not None or args.max_quarantined_rate is not None
    )
    if quality_gate_requested and not args.movement_quarantine_output:
        print(
            "Import failed: quarantine quality limits require "
            "--movement-quarantine-output."
        )
        return 2

    try:
        routing_rules = RoutingRules.from_csv(args.routing_config) if args.routing_config else None
    except RoutingConfigError as exc:
        print(f"Import failed: {exc}")
        return 2

    quarantined_rows = ()
    try:
        opening_stock = read_stock_csv(args.opening)
        if args.movement_quarantine_output:
            movement_import = read_movements_csv_with_quarantine(args.movements)
            movements = movement_import.movements
            quarantined_rows = movement_import.quarantined_rows
            write_movement_quarantine_csv(quarantined_rows, args.movement_quarantine_output)

            gate_error = _quarantine_gate_error(
                valid_count=len(movements),
                quarantined_count=len(quarantined_rows),
                max_rows=args.max_quarantined_rows,
                max_rate=args.max_quarantined_rate,
            )
            if gate_error:
                print(
                    f"Import blocked by quarantine quality gate: {gate_error}. "
                    f"Quarantine: {Path(args.movement_quarantine_output)}."
                )
                return 2
        else:
            movements = read_movements_csv(args.movements)
        counted_stock = read_stock_csv(args.counted) if args.counted else None
        product_metadata = read_product_metadata_csv(args.metadata) if args.metadata else None
    except CsvFormatError as exc:
        print(f"Import failed: {exc}")
        return 2

    report = reconcile_stock(opening_stock, movements, counted_stock, product_metadata)
    quarantine_issues = quarantine_rows_to_issues(quarantined_rows)
    if quarantine_issues:
        report = ReconciliationReport(
            lines=report.lines,
            issues=report.issues + quarantine_issues,
        )

    output_path = write_report_json(report, args.output)

    if args.issues_output:
        write_issues_csv(report.prioritized_issues, args.issues_output)

    task_summary = ""
    if args.task_database:
        with SQLiteTaskStore(args.task_database) as store:
            task_result = sync_reconciliation_tasks(
                report,
                store,
                routing_rules=routing_rules,
            )
        task_summary = (
            f" Tasks: {task_result.created_count} created, "
            f"{task_result.existing_count} existing."
        )

    quarantine_summary = ""
    if args.movement_quarantine_output:
        quarantine_summary = (
            f" Quarantine: {len(quarantined_rows)} rows -> "
            f"{Path(args.movement_quarantine_output)}."
        )

    status = "BALANCED" if report.is_balanced else "REVIEW_REQUIRED"
    print(
        f"{status}: {len(report.lines)} SKUs, {len(report.issues)} issues. "
        f"Report: {Path(output_path)}.{task_summary}{quarantine_summary}"
    )
    return 0 if report.is_balanced else 1


if __name__ == "__main__":
    raise SystemExit(main())
