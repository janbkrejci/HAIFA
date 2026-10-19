"""The fake gh's native executable remains runnable when its cache is reused."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from gh_fake import write_fake_gh


@pytest.mark.parametrize("remove_executable", [False, True])
def test_cached_gh_is_runnable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remove_executable: bool
) -> None:
    monkeypatch.setattr("gh_fake._shared_bin", None)
    binary = write_fake_gh(tmp_path / "bin")
    assert binary.is_file()
    if remove_executable:
        binary.unlink()
    cached = write_fake_gh(tmp_path / "bin")
    assert cached == binary and cached.is_file()
    (tmp_path / "responses.json").write_text("{}", encoding="utf-8")

    result = subprocess.run(
        [str(cached), "--version"],
        env={**os.environ, "AIFACTORY_FAKE_GH_STATE": str(tmp_path)},
        capture_output=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    calls = (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(calls[0])["argv"] == ["--version"]
