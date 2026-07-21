from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .reconciliation import Movement, MovementType, ReconciliationReport


class CsvFormatError(ValueError):
    """Raised when an imported warehouse CSV is missing or contains invalid data."""


def _read_rows(path: str | Path, required_columns: set[str]) -> list[dict[str, str]]:
    csv_path = Path(path)
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            missing = required_columns - columns
            if missing:
                missing_text = ", ".join(sorted(missing))
                raise CsvFormatError(f"{csv_path}: missing required columns: {missing_text}")
            return [
                {key: (value or "").strip() for key, value in row.items() if key is not None}
                for row in reader
                if any((value or "").strip() for value in row.values())
            ]
    except OSError as exc:
        raise CsvFormatError(f"Could not read {csv_path}: {exc}") from exc


def _parse_quantity(raw: str, *, path: str | Path, row_number: int) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise CsvFormatError(
            f"{path}: row {row_number} has invalid integer quantity: {raw!r}"
        ) from exc


def read_stock_csv(path: str | Path) -> dict[str, int]:
    """Read a ``sku,quantity`` CSV into a stock mapping.

    Duplicate SKUs are rejected because silently overwriting one row would hide an
    upstream export or counting error.
    """

    rows = _read_rows(path, {"sku", "quantity"})
    stock: dict[str, int] = {}
    for row_number, row in enumerate(rows, start=2):
        sku = row["sku"]
        if not sku:
            raise CsvFormatError(f"{path}: row {row_number} has an empty SKU")
        if sku in stock:
            raise CsvFormatError(f"{path}: row {row_number} duplicates SKU {sku!r}")
        stock[sku] = _parse_quantity(row["quantity"], path=path, row_number=row_number)
    return stock


def read_movements_csv(path: str | Path) -> tuple[Movement, ...]:
    """Read movement rows from CSV.

    Required columns are ``event_id,sku,movement_type,quantity``. Movement type
    values must match :class:`MovementType`, for example ``RECEIPT`` or ``SALE``.
    """

    rows = _read_rows(path, {"event_id", "sku", "movement_type", "quantity"})
    movements: list[Movement] = []
    for row_number, row in enumerate(rows, start=2):
        try:
            movement_type = MovementType(row["movement_type"].upper())
        except ValueError as exc:
            allowed = ", ".join(item.value for item in MovementType)
            raise CsvFormatError(
                f"{path}: row {row_number} has invalid movement_type "
                f"{row['movement_type']!r}; expected one of: {allowed}"
            ) from exc

        movements.append(
            Movement(
                event_id=row["event_id"],
                sku=row["sku"],
                movement_type=movement_type,
                quantity=_parse_quantity(
                    row["quantity"], path=path, row_number=row_number
                ),
            )
        )
    return tuple(movements)


def report_to_dict(report: ReconciliationReport) -> dict[str, object]:
    """Convert a reconciliation report to a stable JSON-compatible payload."""

    return {
        "is_balanced": report.is_balanced,
        "summary": {
            "line_count": len(report.lines),
            "issue_count": len(report.issues),
        },
        "lines": [asdict(line) for line in report.lines],
        "issues": [asdict(issue) for issue in report.issues],
    }


def write_report_json(
    report: ReconciliationReport,
    path: str | Path,
    *,
    indent: int = 2,
) -> Path:
    """Write a reconciliation report as UTF-8 JSON and return its path."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report_to_dict(report), ensure_ascii=False, indent=indent) + "\n",
        encoding="utf-8",
    )
    return output_path


def write_issues_csv(
    issues: Iterable[object],
    path: str | Path,
) -> Path:
    """Write issue objects with code/message/sku/event_id fields to CSV."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["code", "message", "sku", "event_id"]
        )
        writer.writeheader()
        for issue in issues:
            writer.writerow(
                {
                    "code": getattr(issue, "code"),
                    "message": getattr(issue, "message"),
                    "sku": getattr(issue, "sku", None) or "",
                    "event_id": getattr(issue, "event_id", None) or "",
                }
            )
    return output_path
