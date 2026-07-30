from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from warehouse_ops.task_cli import main
from warehouse_ops.task_store import SQLiteTaskStore
from warehouse_ops.tasks import TaskStatus, WarehouseTask


FIXED_NOW = datetime(2026, 7, 26, 17, 0, tzinfo=timezone.utc)


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return FIXED_NOW.replace(tzinfo=None)
        return FIXED_NOW.astimezone(tz)


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
        with patch("warehouse_ops.task_cli.datetime", FixedDateTime), redirect_stdout(output):
            exit_code = main(["--database", str(self.database), *arguments])
        return exit_code, output.getvalue()

    def test_lists_tasks_with_status_filter(self) -> None:
        exit_code, output = self.run_cli("list", "--status", "OPEN")

        self.assertEqual(exit_code, 0)
        self.assertIn("task-001", output)
        self.assertIn("TVS-001", output)
        self.assertIn("Zemin / A-12", output)
        self.assertIn("2026-07-26T12:00:00+00:00", output)
        self.assertIn("warehouse-manager", output)

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

    def test_lists_escalated_tasks_and_specific_level(self) -> None:
        exit_code, output = self.run_cli("list", "--escalated")

        self.assertEqual(exit_code, 0)
        self.assertIn("task-001", output)
        self.assertIn("URGENT", output)
        self.assertIn("warehouse-manager", output)

        _, urgent_output = self.run_cli("list", "--escalation-level", "URGENT")
        self.assertIn("task-001", urgent_output)

        _, watch_output = self.run_cli("list", "--escalation-level", "WATCH")
        self.assertIn("No tasks found.", watch_output)

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
        self.assertEqual(float(rows[0]["overdue_hours"]), 5.0)
        self.assertEqual(rows[0]["escalation_level"], "URGENT")
        self.assertEqual(rows[0]["escalation_owner"], "warehouse-manager")
        self.assertEqual(rows[0]["sku"], "TVS-001")
        self.assertEqual(rows[0]["location"], "Zemin / A-12")
        self.assertEqual(rows[0]["created_at"], "2026-07-25T12:00:00+00:00")
        self.assertEqual(rows[0]["resolution_note"], "")

    def test_exports_only_requested_escalation_level(self) -> None:
        output_path = Path(self.temp_dir.name) / "urgent.csv"

        exit_code, output = self.run_cli(
            "export",
            str(output_path),
            "--escalation-level",
            "URGENT",
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("EXPORTED: 1 tasks", output)
        with output_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["task_id"], "task-001")
        self.assertEqual(rows[0]["escalation_level"], "URGENT")

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
        self.assertEqual(rows[0]["overdue_hours"], "0.00")
        self.assertEqual(rows[0]["escalation_level"], "NONE")
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
            self.assertIn("escalation_level", handle.seek(0) or handle.read())

    def test_notify_text_preview_preserves_human_readable_output(self) -> None:
        exit_code, output = self.run_cli("notify", "--dry-run")

        self.assertEqual(exit_code, 0)
        self.assertIn("DRY-RUN [URGENT] task=task-001", output)
        self.assertIn("NOTIFICATION PREVIEW: 1 active, 0 previously delivered", output)

    def test_notify_json_preview_returns_stable_machine_readable_contract(self) -> None:
        exit_code, output = self.run_cli("notify", "--dry-run", "--format", "json")

        self.assertEqual(exit_code, 0)
        document = json.loads(output)
        self.assertEqual(document["format_version"], 1)
        self.assertTrue(document["dry_run"])
        self.assertEqual(document["generated_at"], "2026-07-26T17:00:00+00:00")
        self.assertEqual(document["summary"], {"active": 1, "previously_delivered": 0})
        self.assertEqual(document["skipped_delivery_keys"], [])
        self.assertEqual(len(document["notifications"]), 1)

        notification = document["notifications"][0]
        self.assertEqual(notification["task_id"], "task-001")
        self.assertEqual(notification["escalation_level"], "URGENT")
        self.assertEqual(notification["escalation_owner"], "warehouse-manager")
        self.assertEqual(notification["severity"], "HIGH")
        self.assertEqual(notification["sku"], "TVS-001")
        self.assertEqual(notification["channel"], "console")
        self.assertIn("Counted stock differs", notification["message"])
        self.assertIn("task=task-001", notification["payload"])

    def test_notify_json_preview_does_not_persist_delivery(self) -> None:
        first_exit, first_output = self.run_cli("notify", "--dry-run", "--format", "json")
        second_exit, second_output = self.run_cli("notify", "--dry-run", "--format", "json")

        self.assertEqual(first_exit, 0)
        self.assertEqual(second_exit, 0)
        self.assertEqual(json.loads(first_output)["summary"], {"active": 1, "previously_delivered": 0})
        self.assertEqual(json.loads(second_output)["summary"], {"active": 1, "previously_delivered": 0})

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
