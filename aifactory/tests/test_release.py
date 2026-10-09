from pathlib import Path

import pytest
from bundle.build import version
from bundle.release import stamp


def test_ci_version_and_repository_are_embedded_together(tmp_path: Path) -> None:
    package = tmp_path / "src/aifactory"
    (package / "web").mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "0.1.0"\n')
    (package / "web/updates.py").write_text('UPDATE_REPOSITORY = "old/repo"\n')
    assert stamp(42, "example/haifa", tmp_path) == "0.1.42"
    assert version(tmp_path) == "0.1.42"
    assert '"example/haifa"' in (package / "web/updates.py").read_text()
    assert stamp(43, "example/haifa", tmp_path) == "0.1.43"


def test_ci_rejects_invalid_release_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        stamp(0, "example/haifa", tmp_path)
    with pytest.raises(ValueError):
        stamp(1, "bad repository", tmp_path)
