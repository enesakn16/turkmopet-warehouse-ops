from __future__ import annotations

import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from warehouse_ops.task_cli import main
from warehouse_ops.task_store import SQLiteTaskStore
from warehouse_ops.tasks import TaskStatus, WarehouseTask


class WarehouseTaskCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "warehouse.db"
        timestamp = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
        self.task = WarehouseTask(
            task_id="task-001",
            issue_code="STOCK_VARIANCE",
            issue_message="Counted stock differs from expected stock.",
            severity="HIGH",
            sku="TVS-001",
            event_id=None,
            location="Zemin / A-12",
            status=TaskStatus.OPEN,
            assignee=None,
            created_at=timestamp,
            updated_at=timestamp,
        )
        with SQLiteTaskStore(self.database) as store:
            store.save(self.task)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(self, *arguments: str) -> tuple[int, str]:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["--database", str(self.database), *arguments])
        return exit_code, output.getvalue()

    def test_lists_tasks_with_status_filter(self) -> None:
        exit_code, output = self.run_cli("list", "--status", "OPEN")

        self.assertEqual(exit_code, 0)
        self.assertIn("task-001", output)
        self.assertIn("TVS-001", output)
        self.assertIn("Zemin / A-12", output)
        self.assertIn("2026-07-26T12:00:00+00:00", output)

    def test_lists_only_overdue_unresolved_tasks(self) -> None:
        exit_code, output = self.run_cli("list", "--overdue")

        self.assertEqual(exit_code, 0)
        self.assertIn("task-001", output)
        self.assertIn("yes", output)

        self.assertEqual(self.run_cli("assign", "task-001", "Enes")[0], 0)
        self.assertEqual(self.run_cli("start", "task-001")[0], 0)
        self.assertEqual(
            self.run_cli("resolve", "task-001", "--note", "Raf yeniden sayıldı.")[0],
            0,
        )
        _, resolved_output = self.run_cli("list", "--overdue")
        self.assertIn("No tasks found.", resolved_output)

    def test_exports_excel_friendly_filtered_task_queue(self) -> None:
        output_path = Path(self.temp_dir.name) / "reports" / "open-tasks.csv"

        exit_code, output = self.run_cli(
            "export",
            str(output_path),
            "--status",
            "OPEN",
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("EXPORTED: 1 tasks", output)
        with output_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["task_id"], "task-001")
        self.assertEqual(rows[0]["status"], "OPEN")
        self.assertEqual(rows[0]["severity"], "HIGH")
        self.assertEqual(rows[0]["due_at"], "2026-07-26T12:00:00+00:00")
        self.assertEqual(rows[0]["is_overdue"], "yes")
        self.assertEqual(rows[0]["sku"], "TVS-001")
        self.assertEqual(rows[0]["location"], "Zemin / A-12")
        self.assertEqual(rows[0]["created_at"], "2026-07-25T12:00:00+00:00")
        self.assertEqual(rows[0]["resolution_note"], "")

    def test_export_respects_assignee_filter_and_resolution_fields(self) -> None:
        self.assertEqual(self.run_cli("assign", "task-001", "Enes")[0], 0)
        self.assertEqual(self.run_cli("start", "task-001")[0], 0)
        self.assertEqual(
            self.run_cli("resolve", "task-001", "--note", "Raf yeniden sayıldı.")[0],
            0,
        )
        output_path = Path(self.temp_dir.name) / "resolved.csv"

        exit_code, _ = self.run_cli(
            "export",
            str(output_path),
            "--status",
            "RESOLVED",
            "--assignee",
            "Enes",
        )

        self.assertEqual(exit_code, 0)
        with output_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["assignee"], "Enes")
        self.assertEqual(rows[0]["is_overdue"], "no")
        self.assertEqual(rows[0]["resolution_note"], "Raf yeniden sayıldı.")

    def test_export_writes_header_for_empty_queue(self) -> None:
        output_path = Path(self.temp_dir.name) / "empty.csv"

        exit_code, output = self.run_cli(
            "export",
            str(output_path),
            "--status",
            "RESOLVED",
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("EXPORTED: 0 tasks", output)
        with output_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
            self.assertEqual(rows, [])
            self.assertIn("due_at", handle.seek(0) or handle.read())

    def test_assign_start_and_resolve_lifecycle(self) -> None:
        self.assertEqual(self.run_cli("assign", "task-001", "Enes")[0], 0)
        self.assertEqual(self.run_cli("start", "task-001")[0], 0)
        self.assertEqual(
            self.run_cli("resolve", "task-001", "--note", "Raf yeniden sayıldı.")[0],
            0,
        )

        with SQLiteTaskStore(self.database) as store:
            task = store.get("task-001")

        self.assertIsNotNone(task)
        assert task is not None
        self.assertEqual(task.status, TaskStatus.RESOLVED)
        self.assertEqual(task.assignee, "Enes")
        self.assertEqual(task.resolution_note, "Raf yeniden sayıldı.")

    def test_missing_task_returns_operational_error(self) -> None:
        exit_code, output = self.run_cli("start", "missing-task")

        self.assertEqual(exit_code, 2)
        self.assertIn("Task not found", output)

    def test_invalid_transition_does_not_modify_task(self) -> None:
        exit_code, output = self.run_cli("start", "task-001")

        self.assertEqual(exit_code, 2)
        self.assertIn("must be assigned", output)
        with SQLiteTaskStore(self.database) as store:
            task = store.get("task-001")
        self.assertIsNotNone(task)
        assert task is not None
        self.assertEqual(task.status, TaskStatus.OPEN)


if __name__ == "__main__":
    unittest.main()
