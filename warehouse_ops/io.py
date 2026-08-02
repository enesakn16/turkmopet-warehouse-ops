from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .reconciliation import (
    Movement,
    MovementType,
    ProductMetadata,
    ReconciliationReport,
)


class CsvFormatError(ValueError):
    """Raised when an imported warehouse CSV is missing or contains invalid data."""


@dataclass(frozen=True, slots=True)
class QuarantinedMovementRow:
    """A movement row excluded from reconciliation with its original values."""

    row_number: int
    reason: str
    event_id: str
    sku: str
    movement_type: str
    quantity: str


@dataclass(frozen=True, slots=True)
class MovementImportResult:
    """Valid movements and rows that could not be safely imported."""

    movements: tuple[Movement, ...]
    quarantined_rows: tuple[QuarantinedMovementRow, ...]


MOVEMENT_COLUMNS = {"event_id", "sku", "movement_type", "quantity"}


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


def read_product_metadata_csv(path: str | Path) -> dict[str, ProductMetadata]:
    """Read warehouse location and critical-stock thresholds from CSV.

    Required columns are ``sku,floor,shelf,critical_stock``. Floor and shelf may be
    blank, while ``critical_stock`` may be blank when no threshold is configured.
    Duplicate SKUs and negative thresholds are rejected.
    """

    rows = _read_rows(path, {"sku", "floor", "shelf", "critical_stock"})
    metadata: dict[str, ProductMetadata] = {}
    for row_number, row in enumerate(rows, start=2):
        sku = row["sku"]
        if not sku:
            raise CsvFormatError(f"{path}: row {row_number} has an empty SKU")
        if sku in metadata:
            raise CsvFormatError(f"{path}: row {row_number} duplicates SKU {sku!r}")

        raw_threshold = row["critical_stock"]
        threshold = None
        if raw_threshold:
            threshold = _parse_quantity(raw_threshold, path=path, row_number=row_number)
            if threshold < 0:
                raise CsvFormatError(
                    f"{path}: row {row_number} has negative critical_stock: {threshold}"
                )

        metadata[sku] = ProductMetadata(
            floor=row["floor"] or None,
            shelf=row["shelf"] or None,
            critical_stock=threshold,
        )
    return metadata


def _movement_from_row(
    row: dict[str, str], *, path: str | Path, row_number: int
) -> Movement:
    event_id = row["event_id"]
    sku = row["sku"]
    if not event_id:
        raise CsvFormatError(f"{path}: row {row_number} has an empty event_id")
    if not sku:
        raise CsvFormatError(f"{path}: row {row_number} has an empty SKU")

    try:
        movement_type = MovementType(row["movement_type"].upper())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in MovementType)
        raise CsvFormatError(
            f"{path}: row {row_number} has invalid movement_type "
            f"{row['movement_type']!r}; expected one of: {allowed}"
        ) from exc

    return Movement(
        event_id=event_id,
        sku=sku,
        movement_type=movement_type,
        quantity=_parse_quantity(row["quantity"], path=path, row_number=row_number),
    )


def read_movements_csv(path: str | Path) -> tuple[Movement, ...]:
    """Read movement rows strictly and fail on the first invalid row."""

    rows = _read_rows(path, MOVEMENT_COLUMNS)
    return tuple(
        _movement_from_row(row, path=path, row_number=row_number)
        for row_number, row in enumerate(rows, start=2)
    )


def read_movements_csv_with_quarantine(path: str | Path) -> MovementImportResult:
    """Import valid movement rows while isolating invalid rows for review.

    File-level errors such as missing headers still fail the import because no row can
    be interpreted safely. Row-level validation errors are captured without allowing
    the invalid movement to affect stock calculations.
    """

    rows = _read_rows(path, MOVEMENT_COLUMNS)
    movements: list[Movement] = []
    quarantined: list[QuarantinedMovementRow] = []
    seen_event_ids: set[str] = set()

    for row_number, row in enumerate(rows, start=2):
        try:
            movement = _movement_from_row(row, path=path, row_number=row_number)
            event_key = movement.event_id.casefold()
            if event_key in seen_event_ids:
                raise CsvFormatError(
                    f"{path}: row {row_number} duplicates event_id {movement.event_id!r}"
                )
            seen_event_ids.add(event_key)
            movements.append(movement)
        except CsvFormatError as exc:
            quarantined.append(
                QuarantinedMovementRow(
                    row_number=row_number,
                    reason=str(exc),
                    event_id=row.get("event_id", ""),
                    sku=row.get("sku", ""),
                    movement_type=row.get("movement_type", ""),
                    quantity=row.get("quantity", ""),
                )
            )

    return MovementImportResult(tuple(movements), tuple(quarantined))


def write_movement_quarantine_csv(
    rows: Iterable[QuarantinedMovementRow], path: str | Path
) -> Path:
    """Write excluded movement rows to an Excel-compatible audit file."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "row_number",
                "reason",
                "event_id",
                "sku",
                "movement_type",
                "quantity",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    return output_path


def report_to_dict(report: ReconciliationReport) -> dict[str, object]:
    """Convert a reconciliation report to a stable JSON-compatible payload."""

    return {
        "is_balanced": report.is_balanced,
        "summary": {
            "line_count": len(report.lines),
            "issue_count": len(report.issues),
        },
        "lines": [asdict(line) for line in report.lines],
        "issues": [asdict(issue) for issue in report.prioritized_issues],
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
    """Write prioritized operational issues to an Excel-friendly UTF-8 CSV."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["severity", "code", "message", "sku", "event_id", "location"],
        )
        writer.writeheader()
        for issue in issues:
            severity = getattr(issue, "severity", "")
            writer.writerow(
                {
                    "severity": getattr(severity, "value", severity),
                    "code": getattr(issue, "code"),
                    "message": getattr(issue, "message"),
                    "sku": getattr(issue, "sku", None) or "",
                    "event_id": getattr(issue, "event_id", None) or "",
                    "location": getattr(issue, "location", None) or "",
                }
            )
    return output_path
