"""The test-home guard detects writes without taking a new baseline for each test."""

import inspect
import os
import sys
from pathlib import Path

import pytest

import conftest as environment


@pytest.mark.parametrize(
    ("platform", "cpus", "expected"),
    [
        ("win32", 1, 1),
        ("win32", 4, 4),
        ("win32", 16, 8),
        ("win32", None, 2),
        ("linux", 1, 2),
        ("linux", 4, 6),
        ("linux", None, 3),
    ],
)
def test_worker_budget(
    monkeypatch: pytest.MonkeyPatch,
    pytestconfig: pytest.Config,
    platform: str,
    cpus: int | None,
    expected: int,
) -> None:
    with monkeypatch.context() as patch:
        patch.delenv("PYTEST_XDIST_AUTO_NUM_WORKERS", raising=False)
        patch.setattr(sys, "platform", platform)
        patch.setattr(os, "cpu_count", lambda: cpus)
        assert environment.pytest_xdist_auto_num_workers(pytestconfig) == expected


@pytest.mark.parametrize("override", [0, 2, 12])
def test_explicit_worker_budget(
    monkeypatch: pytest.MonkeyPatch,
    pytestconfig: pytest.Config,
    override: int,
) -> None:
    monkeypatch.setenv("PYTEST_XDIST_AUTO_NUM_WORKERS", str(override))
    assert environment.pytest_xdist_auto_num_workers(pytestconfig) == override


@pytest.mark.parametrize("override", ["-1", "invalid"])
def test_invalid_worker_budget(
    monkeypatch: pytest.MonkeyPatch,
    pytestconfig: pytest.Config,
    override: str,
) -> None:
    monkeypatch.setenv("PYTEST_XDIST_AUTO_NUM_WORKERS", override)
    with pytest.raises(pytest.UsageError, match="nonnegative integer"):
        environment.pytest_xdist_auto_num_workers(pytestconfig)


@pytest.mark.parametrize("write_at", [None, "before", "during"])
def test_home_guard_retains_the_session_baseline(
    tmp_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    write_at: str | None,
) -> None:
    real_home = tmp_path / "real-home"
    real_home.mkdir()
    baseline = environment._snapshot(real_home)
    guard = inspect.unwrap(environment._haifa_home)(
        real_home, baseline, tmp_path_factory, monkeypatch
    )
    if write_at == "before":
        (real_home / "leaked").write_text("changed")
    next(guard)
    if write_at == "during":
        (real_home / "leaked").write_text("changed")
    if write_at is None:
        with pytest.raises(StopIteration):
            next(guard)
    else:
        with pytest.raises(AssertionError, match="the real HAIFA home"):
            next(guard)
