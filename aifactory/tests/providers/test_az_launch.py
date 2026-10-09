"""Launch regression tests: no Azure installation or hosting operations needed."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from aifactory.providers import ProviderError, azure
from fake_exe import make_executable


@pytest.mark.skipif(not azure.WINDOWS, reason="Windows native fake MSI launcher")
def test_msi_native_child_receives_exact_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install = tmp_path / "CLI with spaces"
    shim = install / "wbin" / "az.cmd"
    shim.parent.mkdir(parents=True)
    shim.write_text("@echo must never run", encoding="utf-8")
    native = install / "python"
    native.write_text(
        "#!python\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n", encoding="utf-8"
    )
    make_executable(native)
    module = install / "Lib" / "site-packages" / "azure" / "cli" / "__main__.py"
    module.parent.mkdir(parents=True)
    module.touch()
    monkeypatch.setenv("AIFACTORY_AZ", str(shim))
    args = (
        "repos",
        "pr",
        "create",
        "--description",
        '{"text": "příliš \\"žlutý\\""}',
        "line one\nline two",
        "",
        "& %PATH% ! ^",
        "backslash\\\\",
    )
    # The fake native executable records the full argv it received across CreateProcess.
    assert azure.AzCli(tmp_path).json(*args) == ["-I", "-X", "utf8", "-B", "-m", "azure.cli", *args]


@pytest.mark.parametrize("suffix", ["CMD", "bat"])
@pytest.mark.parametrize("module_suffix", [".py", ".pyc"])
def test_windows_msi_preserves_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str, module_suffix: str
) -> None:
    install = tmp_path / "Program Files" / "CLI2"
    shim = install / "wbin" / f"az.{suffix}"
    shim.parent.mkdir(parents=True)
    shim.write_text("@echo unused", encoding="utf-8")
    python = install / "python.exe"
    python.touch()
    module = install / "Lib" / "site-packages" / "azure" / "cli" / f"__main__{module_suffix}"
    module.parent.mkdir(parents=True)
    module.touch()
    monkeypatch.setattr(azure, "WINDOWS", True)
    monkeypatch.setattr(shutil, "which", lambda _: str(shim))
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def launch(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, '{"text": "příliš"}', "")

    monkeypatch.setattr(subprocess, "run", launch)
    args = (
        "repos",
        "pr",
        "create",
        "--title",
        'Příliš "quotes" & %PATH% !',
        "--description",
        '{"a": "b\\\\c"}',
        "first\nsecond",
        "",
        "$(whoami)",
    )
    assert azure.AzCli(tmp_path).json(*args) == {"text": "příliš"}
    argv, options = calls[0]
    assert argv == [str(python), "-I", "-X", "utf8", "-B", "-m", "azure.cli", *args]
    assert options["timeout"] == azure.AZ_TIMEOUT
    assert options["creationflags"] == 0x08000000
    assert options.get("shell", False) is False
    assert options["encoding"] == "utf-8"


@pytest.mark.parametrize("windows", [True, False])
def test_explicit_native_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, windows: bool
) -> None:
    native = str(tmp_path / "fake.exe")
    monkeypatch.setenv("AIFACTORY_AZ", native)
    monkeypatch.setattr(azure, "WINDOWS", windows)
    monkeypatch.setattr(shutil, "which", lambda name: name)
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    calls: list[list[str]] = []

    def launch(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", launch)
    assert azure.AzCli(tmp_path).run('"json"\n&') == "ok"
    assert calls == [[native, '"json"\n&']]
    assert azure.AzCli(tmp_path, executable="override.exe").executable == "override.exe"


@pytest.mark.parametrize("broken_msi", [True, False])
def test_unknown_or_incomplete_shim_never_launches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, broken_msi: bool
) -> None:
    shim = tmp_path / ("wbin" if broken_msi else "unknown") / "az.cmd"
    monkeypatch.setattr(azure, "WINDOWS", True)
    monkeypatch.setattr(shutil, "which", lambda _: str(shim))

    def unexpected(*args: Any, **kwargs: Any) -> None:
        pytest.fail("a shim must not be executed through a shell")

    monkeypatch.setattr(subprocess, "run", unexpected)
    with pytest.raises(ProviderError, match="AIFACTORY_AZ.*native executable"):
        azure.AzCli(tmp_path).run('{"quote": "value"}')


def test_timeout_is_provider_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(azure, "WINDOWS", False)

    def timeout(argv: list[str], **kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(ProviderError) as info:
        azure.AzCli(tmp_path).run("account", "show")
    assert info.value.code == "az_timeout"


def test_windows_missing_installation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(azure, "WINDOWS", True)
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(ProviderError, match="install"):
        azure.AzCli(tmp_path).run("--version")
