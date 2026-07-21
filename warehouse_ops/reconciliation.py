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
    sku: str | None = None
    event_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationLine:
    sku: str
    opening_quantity: int
    movement_delta: int
    expected_quantity: int
    counted_quantity: int | None
    variance: int | None


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    lines: tuple[ReconciliationLine, ...]
    issues: tuple[ReconciliationIssue, ...]

    @property
    def is_balanced(self) -> bool:
        return not self.issues and all(line.variance in {None, 0} for line in self.lines)


def reconcile_stock(
    opening_stock: Mapping[str, int],
    movements: Iterable[Movement],
    counted_stock: Mapping[str, int] | None = None,
) -> ReconciliationReport:
    """Reconcile expected stock against physical counts.

    Invalid movements are excluded from totals and returned as structured issues.
    Duplicate event IDs are ignored after the first occurrence to prevent double
    counting imported marketplace or warehouse events.
    """

    issues: list[ReconciliationIssue] = []
    deltas: dict[str, int] = {sku: 0 for sku in opening_stock}
    seen_event_ids: set[str] = set()

    for sku, quantity in opening_stock.items():
        if quantity < 0:
            issues.append(
                ReconciliationIssue(
                    code="NEGATIVE_OPENING_STOCK",
                    message=f"Opening quantity cannot be negative: {quantity}",
                    sku=sku,
                )
            )

    for movement in movements:
        if not movement.event_id.strip():
            issues.append(
                ReconciliationIssue(
                    code="MISSING_EVENT_ID",
                    message="Movement event ID is required.",
                    sku=movement.sku,
                )
            )
            continue

        if movement.event_id in seen_event_ids:
            issues.append(
                ReconciliationIssue(
                    code="DUPLICATE_EVENT",
                    message="Duplicate movement ignored.",
                    sku=movement.sku,
                    event_id=movement.event_id,
                )
            )
            continue
        seen_event_ids.add(movement.event_id)

        if movement.sku not in opening_stock:
            issues.append(
                ReconciliationIssue(
                    code="UNKNOWN_SKU",
                    message="Movement references an SKU missing from opening stock.",
                    sku=movement.sku,
                    event_id=movement.event_id,
                )
            )
            continue

        if movement.movement_type is not MovementType.ADJUSTMENT and movement.quantity <= 0:
            issues.append(
                ReconciliationIssue(
                    code="INVALID_QUANTITY",
                    message="Movement quantity must be greater than zero.",
                    sku=movement.sku,
                    event_id=movement.event_id,
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
                    sku=sku,
                )
            )
            continue

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
                    sku=sku,
                )
            )

        if variance not in {None, 0}:
            issues.append(
                ReconciliationIssue(
                    code="STOCK_VARIANCE",
                    message=f"Physical count differs from expected stock by {variance}.",
                    sku=sku,
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
            )
        )

    return ReconciliationReport(lines=tuple(lines), issues=tuple(issues))
