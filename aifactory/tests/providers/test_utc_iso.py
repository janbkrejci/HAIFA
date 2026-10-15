from __future__ import annotations

import pytest

from aifactory.providers.base import utc_iso


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-09-27T11:00:05Z", "2026-09-27T11:00:05.000+00:00"),
        ("2026-09-27T11:00:00.4513593Z", "2026-09-27T11:00:00.451+00:00"),
        ("2026-09-27T13:00:00.123456+02:00", "2026-09-27T11:00:00.123+00:00"),
        ("2026-09-27T11:00:00", "2026-09-27T11:00:00.000+00:00"),
        ("", None),
        ("yesterday", None),
        (None, None),
        (17, None),
    ],
)
def test_utc_iso(value: object, expected: str | None) -> None:
    assert utc_iso(value) == expected
