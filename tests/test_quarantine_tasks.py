import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from warehouse_ops.cli import main
from warehouse_ops.io import QuarantinedMovementRow
from warehouse_ops.quarantine import quarantine_rows_to_issues
from warehouse_ops.task_store import SQLiteTaskStore


class QuarantineTaskTests(unittest.TestCase):
    def test_converts_each_quarantined_row_to_high_priority_issue(self) -> None:
        issues = quarantine_rows_to_issues(
            [
                QuarantinedMovementRow(2, "invalid movement_type", "evt-1", "SKU-1", "LOST", "2"),
                QuarantinedMovementRow(3, "empty event_id", "", "SKU-2", "SALE", "1"),
            ]
        )

        self.assertEqual(len(issues), 2)
        self.assertEqual(issues[0].code, "QUARANTINED_MOVEMENT_ROW")
        self.assertEqual(issues[0].severity.value, "HIGH")
        self.assertEqual(issues[1].event_id, "quarantine-row-3")

    def test_cli_persists_quarantined_rows_as_deduplicated_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            opening = root / "opening.csv"
            movements = root / "movements.csv"
            report = root / "report.json"
            quarantine = root / "quarantine.csv"
            database = root / "warehouse.db"
            opening.write_text("sku,quantity\nSKU-1,10\n", encoding="utf-8")
            movements.write_text(
                "event_id,sku,movement_type,quantity\n"
                "evt-1,SKU-1,SALE,2\n"
                ",SKU-1,SALE,1\n",
                encoding="utf-8",
            )

            args = [
                "--opening", str(opening),
                "--movements", str(movements),
                "--output", str(report),
                "--movement-quarantine-output", str(quarantine),
                "--task-database", str(database),
            ]
            with redirect_stdout(io.StringIO()):
                first_exit = main(args)
                second_exit = main(args)

            self.assertEqual(first_exit, 1)
            self.assertEqual(second_exit, 1)
            with SQLiteTaskStore(database) as store:
                tasks = store.list_tasks()
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0].issue_code, "QUARANTINED_MOVEMENT_ROW")
            self.assertEqual(tasks[0].event_id, "quarantine-row-3")


if __name__ == "__main__":
    unittest.main()
