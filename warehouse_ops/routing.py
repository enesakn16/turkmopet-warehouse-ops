from __future__ import annotations

from .reconciliation import ReconciliationIssue


INTEGRATION_ISSUE_CODES = frozenset({
    "DUPLICATE_EVENT",
    "MISSING_EVENT_ID",
})

WAREHOUSE_ISSUE_CODES = frozenset({
    "COUNTED_UNKNOWN_SKU",
    "CRITICAL_STOCK",
    "INVALID_QUANTITY",
    "NEGATIVE_EXPECTED_STOCK",
    "NEGATIVE_OPENING_STOCK",
    "STOCK_VARIANCE",
    "UNKNOWN_SKU",
})


def route_issue(issue: ReconciliationIssue) -> str:
    """Return the operational queue responsible for a reconciliation issue.

    Event identity problems point to the integration pipeline. Stock, SKU,
    quantity and count problems remain with warehouse operations. Quarantined
    rows use their validation message to distinguish event identity errors from
    physical warehouse data errors.
    """

    code = issue.code.upper()
    if code in INTEGRATION_ISSUE_CODES:
        return "integration-team"
    if code == "QUARANTINED_MOVEMENT_ROW":
        message = issue.message.casefold()
        if "event_id" in message or "event id" in message or "duplicate" in message:
            return "integration-team"
        return "warehouse-operations"
    if code in WAREHOUSE_ISSUE_CODES:
        return "warehouse-operations"
    return "operations-supervisor"
