from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Mapping


class MovementType(StrEnum):
    RECEIPT = "RECEIPT"
    SALE = "SALE"
    RETURN = "RETURN"
    TRANSFER_OUT = "TRANSFER_OUT"
    ADJUSTMENT = "ADJUSTMENT"


class IssueSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class ProductMetadata:
    floor: str | None = None
    shelf: str | None = None
    critical_stock: int | None = None

    @property
    def location(self) -> str | None:
        parts = [part for part in (self.floor, self.shelf) if part]
        return " / ".join(parts) or None


@dataclass(frozen=True, slots=True)
class Movement:
    event_id: str
    sku: str
    movement_type: MovementType
    quantity: int

    def delta(self) -> int:
        if self.movement_type in {MovementType.RECEIPT, MovementType.RETURN}:
            return self.quantity
        if self.movement_type in {MovementType.SALE, MovementType.TRANSFER_OUT}:
            return -self.quantity
        return self.quantity


@dataclass(frozen=True, slots=True)
class ReconciliationIssue:
    code: str
    message: str
    severity: IssueSeverity
    sku: str | None = None
    event_id: str | None = None
    location: str | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationLine:
    sku: str
    opening_quantity: int
    movement_delta: int
    expected_quantity: int
    counted_quantity: int | None
    variance: int | None
    location: str | None
    critical_stock: int | None


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    lines: tuple[ReconciliationLine, ...]
    issues: tuple[ReconciliationIssue, ...]

    @property
    def is_balanced(self) -> bool:
        return not self.issues and all(line.variance in {None, 0} for line in self.lines)

    @property
    def prioritized_issues(self) -> tuple[ReconciliationIssue, ...]:
        rank = {
            IssueSeverity.CRITICAL: 0,
            IssueSeverity.HIGH: 1,
            IssueSeverity.MEDIUM: 2,
            IssueSeverity.LOW: 3,
        }
        return tuple(sorted(self.issues, key=lambda issue: (rank[issue.severity], issue.location or "", issue.sku or "")))


def _variance_severity(variance: int, expected_quantity: int, critical_stock: int | None) -> IssueSeverity:
    magnitude = abs(variance)
    if expected_quantity <= 0 or (critical_stock is not None and expected_quantity <= critical_stock):
        return IssueSeverity.CRITICAL
    if magnitude >= 10:
        return IssueSeverity.HIGH
    if magnitude >= 3:
        return IssueSeverity.MEDIUM
    return IssueSeverity.LOW


def reconcile_stock(
    opening_stock: Mapping[str, int],
    movements: Iterable[Movement],
    counted_stock: Mapping[str, int] | None = None,
    product_metadata: Mapping[str, ProductMetadata] | None = None,
) -> ReconciliationReport:
    """Reconcile expected stock against physical counts and prioritize exceptions."""

    issues: list[ReconciliationIssue] = []
    deltas: dict[str, int] = {sku: 0 for sku in opening_stock}
    seen_event_ids: set[str] = set()
    metadata = product_metadata or {}

    def issue_location(sku: str | None) -> str | None:
        return metadata.get(sku, ProductMetadata()).location if sku else None

    for sku, quantity in opening_stock.items():
        if quantity < 0:
            issues.append(
                ReconciliationIssue(
                    code="NEGATIVE_OPENING_STOCK",
                    message=f"Opening quantity cannot be negative: {quantity}",
                    severity=IssueSeverity.CRITICAL,
                    sku=sku,
                    location=issue_location(sku),
                )
            )

    for movement in movements:
        if not movement.event_id.strip():
            issues.append(
                ReconciliationIssue(
                    code="MISSING_EVENT_ID",
                    message="Movement event ID is required.",
                    severity=IssueSeverity.HIGH,
                    sku=movement.sku,
                    location=issue_location(movement.sku),
                )
            )
            continue

        if movement.event_id in seen_event_ids:
            issues.append(
                ReconciliationIssue(
                    code="DUPLICATE_EVENT",
                    message="Duplicate movement ignored.",
                    severity=IssueSeverity.HIGH,
                    sku=movement.sku,
                    event_id=movement.event_id,
                    location=issue_location(movement.sku),
                )
            )
            continue
        seen_event_ids.add(movement.event_id)

        if movement.sku not in opening_stock:
            issues.append(
                ReconciliationIssue(
                    code="UNKNOWN_SKU",
                    message="Movement references an SKU missing from opening stock.",
                    severity=IssueSeverity.HIGH,
                    sku=movement.sku,
                    event_id=movement.event_id,
                    location=issue_location(movement.sku),
                )
            )
            continue

        if movement.movement_type is not MovementType.ADJUSTMENT and movement.quantity <= 0:
            issues.append(
                ReconciliationIssue(
                    code="INVALID_QUANTITY",
                    message="Movement quantity must be greater than zero.",
                    severity=IssueSeverity.MEDIUM,
                    sku=movement.sku,
                    event_id=movement.event_id,
                    location=issue_location(movement.sku),
                )
            )
            continue

        deltas[movement.sku] += movement.delta()

    counted = counted_stock or {}
    all_skus = sorted(set(opening_stock) | set(counted))
    lines: list[ReconciliationLine] = []

    for sku in all_skus:
        if sku not in opening_stock:
            issues.append(
                ReconciliationIssue(
                    code="COUNTED_UNKNOWN_SKU",
                    message="Physical count contains an SKU missing from opening stock.",
                    severity=IssueSeverity.HIGH,
                    sku=sku,
                    location=issue_location(sku),
                )
            )
            continue

        product = metadata.get(sku, ProductMetadata())
        opening_quantity = opening_stock[sku]
        movement_delta = deltas.get(sku, 0)
        expected_quantity = opening_quantity + movement_delta
        counted_quantity = counted.get(sku)
        variance = None if counted_quantity is None else counted_quantity - expected_quantity

        if expected_quantity < 0:
            issues.append(
                ReconciliationIssue(
                    code="NEGATIVE_EXPECTED_STOCK",
                    message=f"Expected stock fell below zero: {expected_quantity}",
                    severity=IssueSeverity.CRITICAL,
                    sku=sku,
                    location=product.location,
                )
            )

        if variance not in {None, 0}:
            issues.append(
                ReconciliationIssue(
                    code="STOCK_VARIANCE",
                    message=f"Physical count differs from expected stock by {variance}.",
                    severity=_variance_severity(variance, expected_quantity, product.critical_stock),
                    sku=sku,
                    location=product.location,
                )
            )

        if product.critical_stock is not None and expected_quantity <= product.critical_stock:
            issues.append(
                ReconciliationIssue(
                    code="CRITICAL_STOCK",
                    message=(
                        f"Expected stock {expected_quantity} is at or below critical threshold "
                        f"{product.critical_stock}."
                    ),
                    severity=IssueSeverity.CRITICAL,
                    sku=sku,
                    location=product.location,
                )
            )

        lines.append(
            ReconciliationLine(
                sku=sku,
                opening_quantity=opening_quantity,
                movement_delta=movement_delta,
                expected_quantity=expected_quantity,
                counted_quantity=counted_quantity,
                variance=variance,
                location=product.location,
                critical_stock=product.critical_stock,
            )
        )

    return ReconciliationReport(lines=tuple(lines), issues=tuple(issues))
