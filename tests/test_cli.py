import io
import json
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

    def _run_with_quarantine(self, *extra_args: str) -> tuple[int, str, Path]:
        quarantine = self.root / "quarantine.csv"
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "--opening",
                    str(self.opening),
                    "--movements",
                    str(self.movements),
                    "--output",
                    str(self.report),
                    "--movement-quarantine-output",
                    str(quarantine),
                    *extra_args,
                ]
            )
        return exit_code, output.getvalue(), quarantine

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

    def test_blocks_reconciliation_when_quarantined_row_count_exceeds_limit(self) -> None:
        self.movements.write_text(
            "event_id,sku,movement_type,quantity\n"
            "evt-1,SKU-1,sale,2\n"
            "evt-2,SKU-1,unknown,3\n",
            encoding="utf-8",
        )

        exit_code, output, quarantine = self._run_with_quarantine(
            "--max-quarantined-rows",
            "0",
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("quarantined row count 1 exceeds allowed maximum 0", output)
        self.assertTrue(quarantine.exists())
        self.assertFalse(self.report.exists())

    def test_blocks_reconciliation_when_quarantined_rate_exceeds_limit(self) -> None:
        self.movements.write_text(
            "event_id,sku,movement_type,quantity\n"
            "evt-1,SKU-1,sale,2\n"
            "evt-2,SKU-1,unknown,3\n"
            "evt-3,SKU-1,receipt,1\n",
            encoding="utf-8",
        )

        exit_code, output, _ = self._run_with_quarantine(
            "--max-quarantined-rate",
            "0.25",
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("33.33% exceeds allowed maximum 25.00%", output)
        self.assertFalse(self.report.exists())

    def test_allows_reconciliation_at_exact_quarantine_limits(self) -> None:
        self.movements.write_text(
            "event_id,sku,movement_type,quantity\n"
            "evt-1,SKU-1,sale,2\n"
            "evt-2,SKU-1,unknown,3\n",
            encoding="utf-8",
        )

        exit_code, output, quarantine = self._run_with_quarantine(
            "--max-quarantined-rows",
            "1",
            "--max-quarantined-rate",
            "0.5",
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("Quarantine: 1 rows", output)
        self.assertTrue(quarantine.exists())
        self.assertTrue(self.report.exists())

    def test_rejects_quality_limits_without_quarantine_output(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "--opening",
                    str(self.opening),
                    "--movements",
                    str(self.movements),
                    "--max-quarantined-rows",
                    "0",
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("require --movement-quarantine-output", output.getvalue())

    def test_quality_profile_blocks_reconciliation_with_reusable_limits(self) -> None:
        self.movements.write_text(
            "event_id,sku,movement_type,quantity\n"
            "evt-1,SKU-1,sale,2\n"
            "evt-2,SKU-1,unknown,3\n",
            encoding="utf-8",
        )
        profile = self._write(
            "quality-profile.json",
            '{"max_quarantined_rows": 0, "max_quarantined_rate": 0.5}\n',
        )

        exit_code, output, quarantine = self._run_with_quarantine(
            "--quality-profile",
            str(profile),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("quarantined row count 1 exceeds allowed maximum 0", output)
        self.assertTrue(quarantine.exists())
        self.assertFalse(self.report.exists())

    def test_explicit_cli_limit_overrides_matching_profile_value(self) -> None:
        self.movements.write_text(
            "event_id,sku,movement_type,quantity\n"
            "evt-1,SKU-1,sale,2\n"
            "evt-2,SKU-1,unknown,3\n",
            encoding="utf-8",
        )
        profile = self._write(
            "quality-profile.json",
            '{"max_quarantined_rows": 0, "max_quarantined_rate": 0.5}\n',
        )

        exit_code, output, quarantine = self._run_with_quarantine(
            "--quality-profile",
            str(profile),
            "--max-quarantined-rows",
            "1",
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("Quarantine: 1 rows", output)
        self.assertTrue(quarantine.exists())
        self.assertTrue(self.report.exists())

    def test_report_records_applied_quality_profile_and_effective_limits(self) -> None:
        self.movements.write_text(
            "event_id,sku,movement_type,quantity\n"
            "evt-1,SKU-1,sale,2\n"
            "evt-2,SKU-1,unknown,3\n"
            "evt-3,SKU-1,receipt,1\n",
            encoding="utf-8",
        )
        profile = self._write(
            "production-quality.json",
            '{"max_quarantined_rows": 5, "max_quarantined_rate": 0.5}\n',
        )

        exit_code, _, _ = self._run_with_quarantine(
            "--quality-profile",
            str(profile),
            "--max-quarantined-rows",
            "2",
        )

        self.assertEqual(exit_code, 1)
        payload = json.loads(self.report.read_text(encoding="utf-8"))
        audit = payload["quarantine_quality_gate"]
        self.assertEqual(audit["profile"], "production-quality.json")
        self.assertEqual(audit["max_quarantined_rows"], 2)
        self.assertEqual(audit["max_quarantined_rate"], 0.5)
        self.assertEqual(audit["valid_movement_rows"], 2)
        self.assertEqual(audit["quarantined_movement_rows"], 1)
        self.assertAlmostEqual(audit["quarantined_rate"], 1 / 3, places=6)

    def test_rejects_invalid_quality_profile_before_import(self) -> None:
        profile = self._write(
            "quality-profile.json",
            '{"max_quarantined_rate": 1.5}\n',
        )

        exit_code, output, _ = self._run_with_quarantine(
            "--quality-profile",
            str(profile),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("max_quarantined_rate must be between 0 and 1", output)
        self.assertFalse(self.report.exists())

    def test_rejects_non_utf8_quality_profile_without_traceback(self) -> None:
        profile = self.root / "quality-profile.json"
        profile.write_bytes(b'{"max_quarantined_rows": \xff}\n')

        exit_code, output, _ = self._run_with_quarantine(
            "--quality-profile",
            str(profile),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("quality profile must be valid UTF-8", output)
        self.assertFalse(self.report.exists())


if __name__ == "__main__":
    unittest.main()
