import csv
import json
import tempfile
import unittest
from pathlib import Path

from warehouse_ops import MovementType, reconcile_stock
from warehouse_ops.io import (
    CsvFormatError,
    read_movements_csv,
    read_product_metadata_csv,
    read_stock_csv,
    write_issues_csv,
    write_report_json,
)


class CsvIoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write(self, name: str, content: str) -> Path:
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_reads_stock_csv_with_utf8_bom(self) -> None:
        path = self.root / "opening.csv"
        path.write_text("\ufeffsku,quantity\nSKU-1,12\n", encoding="utf-8")

        self.assertEqual(read_stock_csv(path), {"SKU-1": 12})

    def test_duplicate_stock_sku_is_rejected(self) -> None:
        path = self.write("opening.csv", "sku,quantity\nSKU-1,10\nSKU-1,11\n")

        with self.assertRaisesRegex(CsvFormatError, "duplicates SKU"):
            read_stock_csv(path)

    def test_reads_product_metadata(self) -> None:
        path = self.write(
            "metadata.csv",
            "sku,floor,shelf,critical_stock\nSKU-1,Zemin,A-12,3\nSKU-2,Asma,,\n",
        )

        metadata = read_product_metadata_csv(path)

        self.assertEqual(metadata["SKU-1"].location, "Zemin / A-12")
        self.assertEqual(metadata["SKU-1"].critical_stock, 3)
        self.assertEqual(metadata["SKU-2"].location, "Asma")
        self.assertIsNone(metadata["SKU-2"].critical_stock)

    def test_negative_critical_stock_is_rejected(self) -> None:
        path = self.write(
            "metadata.csv",
            "sku,floor,shelf,critical_stock\nSKU-1,Zemin,A-12,-1\n",
        )

        with self.assertRaisesRegex(CsvFormatError, "negative critical_stock"):
            read_product_metadata_csv(path)

    def test_reads_movement_types_case_insensitively(self) -> None:
        path = self.write(
            "movements.csv",
            "event_id,sku,movement_type,quantity\nevt-1,SKU-1,sale,2\n",
        )

        movements = read_movements_csv(path)

        self.assertEqual(movements[0].movement_type, MovementType.SALE)
        self.assertEqual(movements[0].quantity, 2)

    def test_invalid_movement_type_reports_row(self) -> None:
        path = self.write(
            "movements.csv",
            "event_id,sku,movement_type,quantity\nevt-1,SKU-1,LOST,2\n",
        )

        with self.assertRaisesRegex(CsvFormatError, "row 2"):
            read_movements_csv(path)

    def test_json_and_issue_csv_outputs(self) -> None:
        opening = self.write("opening.csv", "sku,quantity\nSKU-1,10\n")
        movements = self.write(
            "movements.csv",
            "event_id,sku,movement_type,quantity\nevt-1,SKU-1,SALE,2\n",
        )
        counted = self.write("counted.csv", "sku,quantity\nSKU-1,7\n")
        metadata_path = self.write(
            "metadata.csv",
            "sku,floor,shelf,critical_stock\nSKU-1,Zemin,A-12,8\n",
        )

        report = reconcile_stock(
            read_stock_csv(opening),
            read_movements_csv(movements),
            read_stock_csv(counted),
            read_product_metadata_csv(metadata_path),
        )
        json_path = write_report_json(report, self.root / "out" / "report.json")
        issues_path = write_issues_csv(
            report.prioritized_issues,
            self.root / "out" / "issues.csv",
        )

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertFalse(payload["is_balanced"])
        self.assertEqual(payload["summary"]["issue_count"], 2)
        self.assertEqual(payload["issues"][0]["severity"], "CRITICAL")

        with issues_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["severity"], "CRITICAL")
        self.assertEqual(rows[0]["location"], "Zemin / A-12")
        self.assertEqual(
            {row["code"] for row in rows},
            {"CRITICAL_STOCK", "STOCK_VARIANCE"},
        )


if __name__ == "__main__":
    unittest.main()
