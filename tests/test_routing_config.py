import tempfile
import unittest
from pathlib import Path

from warehouse_ops.reconciliation import IssueSeverity, ReconciliationIssue
from warehouse_ops.routing import RoutingConfigError, RoutingRules, route_issue


class RoutingConfigTests(unittest.TestCase):
    def _issue(self, code: str, message: str = "Warehouse issue") -> ReconciliationIssue:
        return ReconciliationIssue(
            code=code,
            message=message,
            severity=IssueSeverity.HIGH,
            sku="SKU-1",
            location=None,
        )

    def _config(self, content: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "routing.csv"
        path.write_text(content, encoding="utf-8")
        return path

    def test_routes_with_first_matching_message_rule(self) -> None:
        rules = RoutingRules.from_csv(
            self._config(
                "issue_code,assignee,message_contains\n"
                "QUARANTINED_MOVEMENT_ROW,integration,event_id\n"
                "QUARANTINED_MOVEMENT_ROW,warehouse,\n"
                "*,supervisor,\n"
            )
        )

        self.assertEqual(
            "integration",
            route_issue(
                self._issue("QUARANTINED_MOVEMENT_ROW", "duplicate event_id"),
                rules,
            ),
        )
        self.assertEqual(
            "warehouse",
            route_issue(
                self._issue("QUARANTINED_MOVEMENT_ROW", "invalid quantity"),
                rules,
            ),
        )

    def test_uses_configured_fallback_for_unknown_issue(self) -> None:
        rules = RoutingRules.from_csv(
            self._config("issue_code,assignee\nSTOCK_VARIANCE,stock-team\n*,lead\n")
        )
        self.assertEqual("lead", route_issue(self._issue("NEW_ISSUE"), rules))

    def test_rejects_duplicate_rules(self) -> None:
        path = self._config(
            "issue_code,assignee,message_contains\n"
            "STOCK_VARIANCE,team-a,\n"
            "stock_variance,team-b,\n"
        )
        with self.assertRaisesRegex(RoutingConfigError, "duplicates rule"):
            RoutingRules.from_csv(path)

    def test_rejects_missing_required_columns(self) -> None:
        path = self._config("code,owner\nSTOCK_VARIANCE,team-a\n")
        with self.assertRaisesRegex(RoutingConfigError, "must contain"):
            RoutingRules.from_csv(path)


if __name__ == "__main__":
    unittest.main()
