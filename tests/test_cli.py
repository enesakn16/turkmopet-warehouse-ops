import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from warehouse_ops.cli import main
from warehouse_ops.task_store import SQLiteTaskStore


class ReconciliationCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.opening = self._write("opening.csv", "sku,quantity\nSKU-1,10\n")
        self.movements = self._write(
            "movements.csv",
            "event_id,sku,movement_type,quantity\nevt-1,SKU-1,sale,2\n",
        )
        self.counted = self._write("counted.csv", "sku,quantity\nSKU-1,7\n")
        self.report = self.root / "report.json"
        self.database = self.root / "warehouse.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write(self, name: str, content: str) -> Path:
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def _run(self) -> tuple[int, str]:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "--opening",
                    str(self.opening),
                    "--movements",
                    str(self.movements),
                    "--counted",
                    str(self.counted),
                    "--output",
                    str(self.report),
                    "--task-database",
                    str(self.database),
                ]
            )
        return exit_code, output.getvalue()

    def test_synchronizes_reconciliation_issues_into_sqlite(self) -> None:
        exit_code, output = self._run()

        self.assertEqual(exit_code, 1)
        self.assertTrue(self.report.exists())
        self.assertIn("1 created, 0 existing", output)
        with SQLiteTaskStore(self.database) as store:
            self.assertEqual(len(store.list_tasks()), 1)

    def test_repeated_run_does_not_duplicate_existing_task(self) -> None:
        self._run()
        exit_code, output = self._run()

        self.assertEqual(exit_code, 1)
        self.assertIn("0 created, 1 existing", output)
        with SQLiteTaskStore(self.database) as store:
            self.assertEqual(len(store.list_tasks()), 1)


if __name__ == "__main__":
    unittest.main()
