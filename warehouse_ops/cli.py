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
from .service import sync_reconciliation_tasks
from .task_store import SQLiteTaskStore


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
    parser.add_argument(
        "--counted",
        help="Optional physical count CSV with sku,quantity columns",
    )
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
        "--task-database",
        help=(
            "Optional SQLite database path. When provided, reconciliation and "
            "quarantine issues are synchronized into persistent warehouse tasks."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    quarantined_rows = ()
    try:
        opening_stock = read_stock_csv(args.opening)
        if args.movement_quarantine_output:
            movement_import = read_movements_csv_with_quarantine(args.movements)
            movements = movement_import.movements
            quarantined_rows = movement_import.quarantined_rows
            write_movement_quarantine_csv(
                quarantined_rows,
                args.movement_quarantine_output,
            )
        else:
            movements = read_movements_csv(args.movements)
        counted_stock = read_stock_csv(args.counted) if args.counted else None
        product_metadata = (
            read_product_metadata_csv(args.metadata) if args.metadata else None
        )
    except CsvFormatError as exc:
        print(f"Import failed: {exc}")
        return 2

    report = reconcile_stock(
        opening_stock,
        movements,
        counted_stock,
        product_metadata,
    )
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
            task_result = sync_reconciliation_tasks(report, store)
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
