"""``tests/tiers.py``: the slow and browser files conftest marks."""

from pathlib import Path

from tiers import BROWSER_FILES, SLOW_FILES


def test_slow_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    assert all((root / rel).is_file() for rel in SLOW_FILES)


def test_browser_files_are_slow() -> None:
    assert BROWSER_FILES <= SLOW_FILES
