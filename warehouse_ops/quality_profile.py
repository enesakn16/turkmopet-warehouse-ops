from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class QualityProfileError(ValueError):
    """Raised when a quarantine quality profile cannot be trusted."""


@dataclass(frozen=True)
class QualityProfile:
    max_quarantined_rows: int | None = None
    max_quarantined_rate: float | None = None

    @classmethod
    def from_json(cls, path: str | Path) -> "QualityProfile":
        profile_path = Path(path)
        try:
            profile_text = profile_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise QualityProfileError(
                f"cannot read quality profile {profile_path}: {exc}"
            ) from exc
        except UnicodeDecodeError as exc:
            raise QualityProfileError(
                f"quality profile must be valid UTF-8: {profile_path}"
            ) from exc

        try:
            raw = json.loads(profile_text)
        except json.JSONDecodeError as exc:
            raise QualityProfileError(
                f"invalid JSON in quality profile {profile_path}: line {exc.lineno}, column {exc.colno}"
            ) from exc

        if not isinstance(raw, dict):
            raise QualityProfileError("quality profile root must be a JSON object")

        allowed_keys = {"max_quarantined_rows", "max_quarantined_rate"}
        unknown_keys = sorted(set(raw) - allowed_keys)
        if unknown_keys:
            raise QualityProfileError(
                "unknown quality profile fields: " + ", ".join(unknown_keys)
            )

        max_rows = _optional_non_negative_int(raw.get("max_quarantined_rows"))
        max_rate = _optional_rate(raw.get("max_quarantined_rate"))
        if max_rows is None and max_rate is None:
            raise QualityProfileError(
                "quality profile must define max_quarantined_rows and/or max_quarantined_rate"
            )

        return cls(
            max_quarantined_rows=max_rows,
            max_quarantined_rate=max_rate,
        )


def _optional_non_negative_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise QualityProfileError("max_quarantined_rows must be a non-negative integer")
    return value


def _optional_rate(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QualityProfileError("max_quarantined_rate must be a number between 0 and 1")
    rate = float(value)
    if not 0 <= rate <= 1:
        raise QualityProfileError("max_quarantined_rate must be between 0 and 1")
    return rate
