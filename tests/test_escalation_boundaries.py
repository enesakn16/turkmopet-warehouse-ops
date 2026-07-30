from datetime import datetime, timedelta, timezone
import unittest

from warehouse_ops.tasks import EscalationLevel, TaskStatus, WarehouseTask


class EscalationBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        created_at = datetime(2026, 7, 30, 6, 0, tzinfo=timezone.utc)
        self.task = WarehouseTask(
            task_id="boundary-task",
            issue_code="STOCK_VARIANCE",
            issue_message="Physical count differs from expected stock.",
            severity="CRITICAL",
            sku="TEST-SKU",
            event_id=None,
            location="A-01",
            status=TaskStatus.OPEN,
            assignee=None,
            created_at=created_at,
            updated_at=created_at,
        )

    def test_four_hours_overdue_is_urgent(self) -> None:
        now = self.task.due_at + timedelta(hours=4)

        self.assertEqual(EscalationLevel.URGENT, self.task.escalation_level(now=now))

    def test_exactly_twenty_four_hours_overdue_remains_urgent(self) -> None:
        now = self.task.due_at + timedelta(hours=24)

        self.assertEqual(EscalationLevel.URGENT, self.task.escalation_level(now=now))

    def test_more_than_twenty_four_hours_overdue_is_critical(self) -> None:
        now = self.task.due_at + timedelta(hours=24, seconds=1)

        self.assertEqual(EscalationLevel.CRITICAL, self.task.escalation_level(now=now))


if __name__ == "__main__":
    unittest.main()
