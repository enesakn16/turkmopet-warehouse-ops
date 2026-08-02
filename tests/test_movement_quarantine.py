import csv
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from warehouse_ops.cli import main
from warehouse_ops.io import (
    CsvFormatError,
    read_movements_csv_with_quarantine,
    write_movement_quarantine_csv,
)


class MovementQuarantineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write(self, name: str, content: str) -> Path:
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_valid_rows_continue_and_invalid_rows_are_quarantined(self) -> None:
        path = self.write(
            "movements.csv",
            "event_id,sku,movement_type,quantity\n"
            "evt-1,SKU-1,SALE,2\n"
            "evt-2,SKU-1,LOST,1\n"
            "evt-3,SKU-1,RETURN,abc\n"
            ",SKU-2,SALE,1\n"
            "evt-4,,SALE,1\n",
        )

        result = read_movements_csv_with_quarantine(path)

        self.assertEqual([item.event_id for item in result.movements], ["evt-1"])
        self.assertEqual(len(result.quarantined_rows), 4)
        self.assertEqual(
            [item.row_number for item in result.quarantined_rows],
            [3, 4, 5, 6],
        )
        self.assertIn("invalid movement_type", result.quarantined_rows[0].reason)
        self.assertIn("invalid integer quantity", result.quarantined_rows[1].reason)
        self.assertIn("empty event_id", result.quarantined_rows[2].reason)
        self.assertIn("empty SKU", result.quarantined_rows[3].reason)

    def test_duplicate_event_id_is_quarantined_case_insensitively(self) -> None:
        path = self.write(
            "movements.csv",
            "event_id,sku,movement_type,quantity\n"
            "EVT-1,SKU-1,SALE,1\n"
            "evt-1,SKU-2,SALE,1\n",
        )

        result = read_movements_csv_with_quarantine(path)

        self.assertEqual(len(result.movements), 1)
        self.assertEqual(len(result.quarantined_rows), 1)
        self.assertIn("duplicates event_id", result.quarantined_rows[0].reason)

    def test_missing_headers_still_fail_the_whole_import(self) -> None:
        path = self.write("movements.csv", "sku,quantity\nSKU-1,1\n")

        with self.assertRaisesRegex(CsvFormatError, "missing required columns"):
            read_movements_csv_with_quarantine(path)

    def test_quarantine_csv_is_excel_compatible(self) -> None:
        source = self.write(
            "movements.csv",
            "event_id,sku,movement_type,quantity\nevt-1,SKU-1,LOST,2\n",
        )
        result = read_movements_csv_with_quarantine(source)
        output = write_movement_quarantine_csv(
            result.quarantined_rows, self.root / "reports" / "quarantine.csv"
        )

        self.assertTrue(output.read_bytes().startswith(b"\xef\xbb\xbf"))
        with output.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["row_number"], "2")
        self.assertEqual(rows[0]["event_id"], "evt-1")
        self.assertIn("invalid movement_type", rows[0]["reason"])

    def test_cli_reconciles_valid_rows_and_returns_review_status(self) -> None:
        opening = self.write("opening.csv", "sku,quantity\nSKU-1,10\n")
        movements = self.write(
            "movements.csv",
            "event_id,sku,movement_type,quantity\n"
            "evt-1,SKU-1,SALE,2\n"
            "evt-2,SKU-1,LOST,1\n",
        )
        report = self.root / "report.json"
        quarantine = self.root / "quarantine.csv"

        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "--opening",
                    str(opening),
                    "--movements",
                    str(movements),
                    "--output",
                    str(report),
                    "--movement-quarantine-output",
                    str(quarantine),
                ]
            )

        self.assertEqual(exit_code, 1)
        payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(payload["lines"][0]["expected_quantity"], 8)
        self.assertIn("Quarantine: 1 rows", stdout.getvalue())
        with quarantine.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
