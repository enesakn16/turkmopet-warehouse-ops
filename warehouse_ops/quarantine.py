from __future__ import annotations

from typing import Iterable

from .io import QuarantinedMovementRow
from .reconciliation import IssueSeverity, ReconciliationIssue


def quarantine_rows_to_issues(
    rows: Iterable[QuarantinedMovementRow],
) -> tuple[ReconciliationIssue, ...]:
    """Convert excluded movement rows into stable, assignable warehouse issues.

    Quarantined records are HIGH severity because excluding a movement can change
    expected stock. A synthetic row event identifier keeps separate malformed rows
    independently assignable when the upstream event ID is blank.
    """

    issues: list[ReconciliationIssue] = []
    for row in rows:
        event_id = row.event_id.strip() or f"quarantine-row-{row.row_number}"
        sku = row.sku.strip() or None
        issues.append(
            ReconciliationIssue(
                code="QUARANTINED_MOVEMENT_ROW",
                message=(
                    f"Movement CSV row {row.row_number} was excluded from stock "
                    f"calculation and must be corrected: {row.reason}"
                ),
                severity=IssueSeverity.HIGH,
                sku=sku,
                event_id=event_id,
            )
        )
    return tuple(issues)
