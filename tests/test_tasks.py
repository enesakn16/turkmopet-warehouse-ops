from datetime import datetime, timezone
import unittest

from warehouse_ops.reconciliation import (
    IssueSeverity,
    ReconciliationIssue,
    ReconciliationReport,
)
from warehouse_ops.tasks import (
    TaskStatus,
    TaskTransitionError,
    assign_task,
    create_tasks,
    resolve_task,
    start_task,
)


NOW = datetime(2026, 7, 24, 19, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 7, 24, 20, 0, tzinfo=timezone.utc)


class WarehouseTaskTests(unittest.TestCase):
    def _report(self) -> ReconciliationReport:
        return ReconciliationReport(
            lines=(),
            issues=(
                ReconciliationIssue(
                    code="STOCK_VARIANCE",
                    message="Physical count differs from expected stock by -4.",
                    severity=IssueSeverity.MEDIUM,
                    sku="TVS-FILTER-01",
                    location="Zemin / A-12",
                ),
                ReconciliationIssue(
                    code="CRITICAL_STOCK",
                    message="Expected stock 1 is at or below critical threshold 3.",
                    severity=IssueSeverity.CRITICAL,
                    sku="HONDA-BALATA-02",
                    location="Asma Kat / B-07",
                ),
            ),
        )

    def test_creates_prioritized_open_tasks(self) -> None:
        tasks = create_tasks(self._report(), now=NOW)

        self.assertEqual(2, len(tasks))
        self.assertEqual("CRITICAL_STOCK", tasks[0].issue_code)
        self.assertEqual(TaskStatus.OPEN, tasks[0].status)
        self.assertIsNone(tasks[0].assignee)
        self.assertEqual(NOW, tasks[0].created_at)

    def test_does_not_duplicate_existing_issue_task(self) -> None:
        initial = create_tasks(self._report(), now=NOW)
        repeated = create_tasks(self._report(), existing_tasks=initial, now=LATER)

        self.assertEqual(initial, repeated)

    def test_assign_start_and_resolve_task(self) -> None:
        task = create_tasks(self._report(), now=NOW)[0]
        assigned = assign_task(task, "Enes", now=LATER)
        started = start_task(assigned, now=LATER)
        resolved = resolve_task(started, "Raf sayımı tekrarlandı; stok düzeltildi.", now=LATER)

        self.assertEqual("Enes", assigned.assignee)
        self.assertEqual(TaskStatus.IN_PROGRESS, started.status)
        self.assertEqual(TaskStatus.RESOLVED, resolved.status)
        self.assertTrue(resolved.is_closed)
        self.assertEqual("Raf sayımı tekrarlandı; stok düzeltildi.", resolved.resolution_note)

    def test_cannot_start_unassigned_task(self) -> None:
        task = create_tasks(self._report(), now=NOW)[0]

        with self.assertRaises(TaskTransitionError):
            start_task(task, now=LATER)

    def test_cannot_resolve_open_task_or_reassign_resolved_task(self) -> None:
        task = create_tasks(self._report(), now=NOW)[0]
        with self.assertRaises(TaskTransitionError):
            resolve_task(task, "Resolved", now=LATER)

        resolved = resolve_task(start_task(assign_task(task, "Enes", now=LATER), now=LATER), "Done", now=LATER)
        with self.assertRaises(TaskTransitionError):
            assign_task(resolved, "Other", now=LATER)

    def test_assignee_and_resolution_note_are_required(self) -> None:
        task = create_tasks(self._report(), now=NOW)[0]
        with self.assertRaises(ValueError):
            assign_task(task, "   ", now=LATER)

        started = start_task(assign_task(task, "Enes", now=LATER), now=LATER)
        with self.assertRaises(ValueError):
            resolve_task(started, "   ", now=LATER)


if __name__ == "__main__":
    unittest.main()
