from __future__ import annotations

import argparse
from pathlib import Path

from .io import CsvFormatError, read_movements_csv, read_stock_csv, write_issues_csv, write_report_json
from .reconciliation import reconcile_stock


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="warehouse-reconcile",
        description="Reconcile opening stock, movements and optional physical counts.",
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
        "--output",
        default="reconciliation-report.json",
        help="JSON report path (default: reconciliation-report.json)",
    )
    parser.add_argument(
        "--issues-output",
        help="Optional CSV path for issues requiring operational review",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        opening_stock = read_stock_csv(args.opening)
        movements = read_movements_csv(args.movements)
        counted_stock = read_stock_csv(args.counted) if args.counted else None
    except CsvFormatError as exc:
        print(f"Import failed: {exc}")
        return 2

    report = reconcile_stock(opening_stock, movements, counted_stock)
    output_path = write_report_json(report, args.output)

    if args.issues_output:
        write_issues_csv(report.issues, args.issues_output)

    status = "BALANCED" if report.is_balanced else "REVIEW_REQUIRED"
    print(
        f"{status}: {len(report.lines)} SKUs, {len(report.issues)} issues. "
        f"Report: {Path(output_path)}"
    )
    return 0 if report.is_balanced else 1


if __name__ == "__main__":
    raise SystemExit(main())
