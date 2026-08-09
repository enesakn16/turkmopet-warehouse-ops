import argparse
import tempfile
import unittest
from pathlib import Path

from warehouse_ops.cli import _rate
from warehouse_ops.quality_profile import QualityProfile, QualityProfileError


class QuarantineRateValidationTests(unittest.TestCase):
    def test_cli_rejects_non_finite_rates(self) -> None:
        for raw in ("nan", "NaN", "inf", "-inf", "Infinity"):
            with self.subTest(raw=raw):
                with self.assertRaises(argparse.ArgumentTypeError):
                    _rate(raw)

    def test_quality_profile_rejects_non_finite_rates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for raw in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(raw=raw):
                    profile = root / "quality-profile.json"
                    profile.write_text(
                        f'{{"max_quarantined_rate": {raw}}}\n',
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(
                        QualityProfileError,
                        "finite number between 0 and 1",
                    ):
                        QualityProfile.from_json(profile)


if __name__ == "__main__":
    unittest.main()
