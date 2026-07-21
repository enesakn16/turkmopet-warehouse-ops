import unittest

from warehouse_ops import Movement, MovementType, reconcile_stock


class ReconcileStockTests(unittest.TestCase):
    def test_balanced_stock_after_receipts_and_sales(self) -> None:
        report = reconcile_stock(
            opening_stock={"SKU-1": 10},
            movements=[
                Movement("evt-1", "SKU-1", MovementType.RECEIPT, 5),
                Movement("evt-2", "SKU-1", MovementType.SALE, 3),
            ],
            counted_stock={"SKU-1": 12},
        )

        self.assertTrue(report.is_balanced)
        self.assertEqual(report.lines[0].expected_quantity, 12)
        self.assertEqual(report.lines[0].variance, 0)

    def test_duplicate_event_is_ignored(self) -> None:
        report = reconcile_stock(
            opening_stock={"SKU-1": 10},
            movements=[
                Movement("evt-1", "SKU-1", MovementType.SALE, 2),
                Movement("evt-1", "SKU-1", MovementType.SALE, 2),
            ],
        )

        self.assertEqual(report.lines[0].expected_quantity, 8)
        self.assertIn("DUPLICATE_EVENT", {issue.code for issue in report.issues})

    def test_unknown_sku_does_not_change_totals(self) -> None:
        report = reconcile_stock(
            opening_stock={"SKU-1": 10},
            movements=[Movement("evt-1", "SKU-X", MovementType.RECEIPT, 5)],
        )

        self.assertEqual(report.lines[0].expected_quantity, 10)
        self.assertIn("UNKNOWN_SKU", {issue.code for issue in report.issues})

    def test_physical_variance_is_reported(self) -> None:
        report = reconcile_stock(
            opening_stock={"SKU-1": 10},
            movements=[Movement("evt-1", "SKU-1", MovementType.SALE, 2)],
            counted_stock={"SKU-1": 7},
        )

        self.assertFalse(report.is_balanced)
        self.assertEqual(report.lines[0].variance, -1)
        self.assertIn("STOCK_VARIANCE", {issue.code for issue in report.issues})

    def test_negative_expected_stock_is_reported(self) -> None:
        report = reconcile_stock(
            opening_stock={"SKU-1": 1},
            movements=[Movement("evt-1", "SKU-1", MovementType.SALE, 3)],
        )

        self.assertEqual(report.lines[0].expected_quantity, -2)
        self.assertIn("NEGATIVE_EXPECTED_STOCK", {issue.code for issue in report.issues})


if __name__ == "__main__":
    unittest.main()
