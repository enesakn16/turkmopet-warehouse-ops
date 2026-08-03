from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from warehouse_ops.reconciliation import (
    IssueSeverity,
    ReconciliationIssue,
    ReconciliationReport,
)
from warehouse_ops.service import sync_reconciliation_tasks
from warehouse_ops.task_store import SQLiteTaskStore
from warehouse_ops.tasks import TaskStatus, assign_task, start_task


NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 7, 25, 13, 0, tzinfo=timezone.utc)


class TaskSynchronizationTests(unittest.TestCase):
    @staticmethod
    def _report(*issues: ReconciliationIssue) -> ReconciliationReport:
        return ReconciliationReport(lines=(), issues=issues)

    @staticmethod
    def _issue(code: str, sku: str, message: str | None = None) -> ReconciliationIssue:
        return ReconciliationIssue(
            code=code,
            message=message or f"Warehouse issue for {sku}.",
            severity=IssueSeverity.HIGH,
            sku=sku,
            location="Zemin / A-01",
        )

    def test_persists_new_tasks_and_reports_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with SQLiteTaskStore(Path(directory) / "warehouse.db") as store:
                result = sync_reconciliation_tasks(
                    self._report(
                        self._issue("STOCK_VARIANCE", "TVS-001"),
                        self._issue("CRITICAL_STOCK", "HONDA-002"),
                    ),
                    store,
                    now=NOW,
                )

                self.assertEqual(2, result.created_count)
                self.assertEqual(0, result.existing_count)
                self.assertEqual(2, result.total_count)
                self.assertEqual(2, len(store.list_tasks()))
                self.assertTrue(
                    all(task.assignee == "warehouse-operations" for task in result.created_tasks)
                )

    def test_routes_event_identity_errors_to_integration_team(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with SQLiteTaskStore(Path(directory) / "warehouse.db") as store:
                result = sync_reconciliation_tasks(
                    self._report(
                        self._issue("DUPLICATE_EVENT", "TVS-001"),
                        self._issue("MISSING_EVENT_ID", "HONDA-002"),
                    ),
                    store,
                    now=NOW,
                )

                self.assertEqual(
                    {"integration-team"},
                    {task.assignee for task in result.created_tasks},
                )

    def test_routes_quarantine_rows_by_validation_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with SQLiteTaskStore(Path(directory) / "warehouse.db") as store:
                result = sync_reconciliation_tasks(
                    self._report(
                        self._issue(
                            "QUARANTINED_MOVEMENT_ROW",
                            "TVS-001",
                            "Movement CSV row 2 was excluded: duplicate event_id",
                        ),
                        self._issue(
                            "QUARANTINED_MOVEMENT_ROW",
                            "HONDA-002",
                            "Movement CSV row 3 was excluded: invalid quantity",
                        ),
                    ),
                    store,
                    now=NOW,
                )

                assignments = {
                    task.sku: task.assignee
                    for task in result.created_tasks
                }
                self.assertEqual("integration-team", assignments["TVS-001"])
                self.assertEqual("warehouse-operations", assignments["HONDA-002"])

    def test_routes_unknown_issue_to_operations_supervisor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with SQLiteTaskStore(Path(directory) / "warehouse.db") as store:
                result = sync_reconciliation_tasks(
                    self._report(self._issue("UNMAPPED_ISSUE", "TVS-001")),
                    store,
                    now=NOW,
                )

                self.assertEqual("operations-supervisor", result.created_tasks[0].assignee)

    def test_repeated_sync_does_not_duplicate_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = self._report(self._issue("STOCK_VARIANCE", "TVS-001"))
            with SQLiteTaskStore(Path(directory) / "warehouse.db") as store:
                first = sync_reconciliation_tasks(report, store, now=NOW)
                repeated = sync_reconciliation_tasks(report, store, now=LATER)

                self.assertEqual(1, first.created_count)
                self.assertEqual(0, repeated.created_count)
                self.assertEqual(1, repeated.existing_count)
                self.assertEqual(1, len(store.list_tasks()))

    def test_sync_preserves_existing_assignment_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = self._report(self._issue("STOCK_VARIANCE", "TVS-001"))
            with SQLiteTaskStore(Path(directory) / "warehouse.db") as store:
                initial = sync_reconciliation_tasks(report, store, now=NOW)
                task = start_task(assign_task(initial.created_tasks[0], "Enes", now=LATER), now=LATER)
                store.save(task)

                sync_reconciliation_tasks(report, store, now=LATER)
                persisted = store.get(task.task_id)

                self.assertIsNotNone(persisted)
                assert persisted is not None
                self.assertEqual("Enes", persisted.assignee)
                self.assertEqual(TaskStatus.IN_PROGRESS, persisted.status)
                self.assertEqual(NOW, persisted.created_at)

    def test_adds_only_new_issue_during_later_sync(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first_issue = self._issue("STOCK_VARIANCE", "TVS-001")
            second_issue = self._issue("CRITICAL_STOCK", "HONDA-002")
            with SQLiteTaskStore(Path(directory) / "warehouse.db") as store:
                sync_reconciliation_tasks(self._report(first_issue), store, now=NOW)
                result = sync_reconciliation_tasks(
                    self._report(first_issue, second_issue),
                    store,
                    now=LATER,
                )

                self.assertEqual(1, result.created_count)
                self.assertEqual("CRITICAL_STOCK", result.created_tasks[0].issue_code)
                self.assertEqual("warehouse-operations", result.created_tasks[0].assignee)
                self.assertEqual(2, result.total_count)
                self.assertEqual(2, len(store.list_tasks()))


if __name__ == "__main__":
    unittest.main()
