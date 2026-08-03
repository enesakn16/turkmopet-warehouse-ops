from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .reconciliation import ReconciliationIssue


INTEGRATION_ISSUE_CODES = frozenset({"DUPLICATE_EVENT", "MISSING_EVENT_ID"})
WAREHOUSE_ISSUE_CODES = frozenset({
    "COUNTED_UNKNOWN_SKU",
    "CRITICAL_STOCK",
    "INVALID_QUANTITY",
    "NEGATIVE_EXPECTED_STOCK",
    "NEGATIVE_OPENING_STOCK",
    "STOCK_VARIANCE",
    "UNKNOWN_SKU",
})


class RoutingConfigError(ValueError):
    """Raised when a routing configuration cannot be applied safely."""


@dataclass(frozen=True, slots=True)
class RoutingRule:
    issue_code: str
    assignee: str
    message_contains: str = ""


@dataclass(frozen=True, slots=True)
class RoutingRules:
    rules: tuple[RoutingRule, ...]
    fallback_assignee: str = "operations-supervisor"

    @classmethod
    def from_csv(cls, path: str | Path) -> "RoutingRules":
        source = Path(path)
        try:
            with source.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                required = {"issue_code", "assignee"}
                if not reader.fieldnames or not required.issubset(reader.fieldnames):
                    raise RoutingConfigError(
                        "Routing CSV must contain issue_code and assignee columns."
                    )
                rules: list[RoutingRule] = []
                seen: set[tuple[str, str]] = set()
                fallback = "operations-supervisor"
                for row_number, row in enumerate(reader, start=2):
                    code = (row.get("issue_code") or "").strip().upper()
                    assignee = (row.get("assignee") or "").strip()
                    message_contains = (row.get("message_contains") or "").strip().casefold()
                    if not code or not assignee:
                        raise RoutingConfigError(
                            f"Routing CSV row {row_number} has an empty issue_code or assignee."
                        )
                    if code == "*":
                        if message_contains:
                            raise RoutingConfigError(
                                f"Routing CSV row {row_number}: fallback rule cannot use message_contains."
                            )
                        fallback = assignee
                        continue
                    key = (code, message_contains)
                    if key in seen:
                        raise RoutingConfigError(
                            f"Routing CSV row {row_number} duplicates rule {code!r}."
                        )
                    seen.add(key)
                    rules.append(RoutingRule(code, assignee, message_contains))
        except OSError as exc:
            raise RoutingConfigError(f"Cannot read routing CSV: {source}") from exc
        return cls(tuple(rules), fallback)


def default_routing_rules() -> RoutingRules:
    rules = [
        *(RoutingRule(code, "integration-team") for code in sorted(INTEGRATION_ISSUE_CODES)),
        RoutingRule("QUARANTINED_MOVEMENT_ROW", "integration-team", "event_id"),
        RoutingRule("QUARANTINED_MOVEMENT_ROW", "integration-team", "event id"),
        RoutingRule("QUARANTINED_MOVEMENT_ROW", "integration-team", "duplicate"),
        RoutingRule("QUARANTINED_MOVEMENT_ROW", "warehouse-operations"),
        *(RoutingRule(code, "warehouse-operations") for code in sorted(WAREHOUSE_ISSUE_CODES)),
    ]
    return RoutingRules(tuple(rules))


def route_issue(issue: ReconciliationIssue, rules: RoutingRules | None = None) -> str:
    """Return the queue responsible for an issue using deterministic first-match rules."""

    active_rules = rules or default_routing_rules()
    code = issue.code.strip().upper()
    message = issue.message.casefold()
    for rule in active_rules.rules:
        if rule.issue_code != code:
            continue
        if rule.message_contains and rule.message_contains not in message:
            continue
        return rule.assignee
    return active_rules.fallback_assignee
