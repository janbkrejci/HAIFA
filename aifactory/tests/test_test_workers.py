"""Worker limits must survive the repository's custom xdist auto hook."""

import os
import platform
import sys
from unittest.mock import Mock

import pytest

import conftest

# This optional private backend is absent from older Python versions and type stubs.
WMI_QUERY = "_wmi_query"


def test_windows_platform_metadata_uses_fallback_and_restores_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    original = Mock(side_effect=AssertionError("must not invoke WMI"))
    monkeypatch.setattr(platform, "_wmi_query", original, raising=False)
    config = Mock(spec=pytest.Config)
    conftest.pytest_configure(config)
    with pytest.raises(OSError, match="WMI disabled"):
        getattr(platform, WMI_QUERY)("CPU", "Architecture")
    original.assert_not_called()
    config.add_cleanup.call_args.args[0]()
    assert getattr(platform, WMI_QUERY) is original


def test_platform_without_wmi_backend_needs_no_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delattr(platform, "_wmi_query", raising=False)
    config = Mock(spec=pytest.Config)
    conftest.pytest_configure(config)
    config.add_cleanup.assert_not_called()
    assert not hasattr(platform, "_wmi_query")


def test_non_windows_platform_keeps_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    original = Mock()
    monkeypatch.setattr(platform, "_wmi_query", original, raising=False)
    config = Mock(spec=pytest.Config)
    conftest.pytest_configure(config)
    assert getattr(platform, WMI_QUERY) is original
    config.add_cleanup.assert_not_called()


@pytest.mark.parametrize("workers", [0, 1, 8, 16])
def test_auto_workers_respect_environment_override(
    monkeypatch: pytest.MonkeyPatch, pytestconfig: pytest.Config, workers: int
) -> None:
    monkeypatch.setenv("PYTEST_XDIST_AUTO_NUM_WORKERS", str(workers))
    monkeypatch.setattr(os, "cpu_count", lambda: 64)
    assert conftest.pytest_xdist_auto_num_workers(pytestconfig) == workers


@pytest.mark.parametrize("value", ["invalid", "-1"])
def test_auto_workers_reject_invalid_override(
    monkeypatch: pytest.MonkeyPatch, pytestconfig: pytest.Config, value: str
) -> None:
    monkeypatch.setenv("PYTEST_XDIST_AUTO_NUM_WORKERS", value)
    with pytest.raises(pytest.UsageError, match="nonnegative integer"):
        conftest.pytest_xdist_auto_num_workers(pytestconfig)


@pytest.mark.parametrize("platform, expected", [("win32", 8), ("linux", 12)])
def test_auto_workers_default_caps_windows_subprocess_pressure(
    monkeypatch: pytest.MonkeyPatch, pytestconfig: pytest.Config, platform: str, expected: int
) -> None:
    monkeypatch.delenv("PYTEST_XDIST_AUTO_NUM_WORKERS", raising=False)
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    assert conftest.pytest_xdist_auto_num_workers(pytestconfig) == expected
