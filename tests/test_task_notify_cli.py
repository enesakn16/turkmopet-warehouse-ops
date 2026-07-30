from __future__ import annotations

import io
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


class WarehouseTaskNotifyCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "warehouse.db"
        timestamp = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
        task = WarehouseTask(
            task_id="task-urgent",
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
            store.save(task)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(self, *arguments: str) -> tuple[int, str]:
        output = io.StringIO()
        with patch("warehouse_ops.task_cli.datetime", FixedDateTime), redirect_stdout(output):
            exit_code = main(["--database", str(self.database), *arguments])
        return exit_code, output.getvalue()

    def test_notify_dry_run_previews_active_escalations(self) -> None:
        exit_code, output = self.run_cli("notify", "--dry-run")

        self.assertEqual(exit_code, 0)
        self.assertIn("DRY-RUN [URGENT] task=task-urgent", output)
        self.assertIn("NOTIFICATION PREVIEW: 1 active, 0 previously delivered", output)

    def test_notify_dry_run_never_records_delivery(self) -> None:
        self.assertEqual(self.run_cli("notify", "--dry-run")[0], 0)
        self.assertEqual(self.run_cli("notify", "--dry-run")[0], 0)

        with SQLiteTaskStore(self.database) as store:
            deliveries = store.list_deliveries()

        self.assertEqual(deliveries, ())


if __name__ == "__main__":
    unittest.main()
