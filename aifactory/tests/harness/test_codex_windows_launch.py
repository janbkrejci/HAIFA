"""npm launch on Windows keeps argv out of cmd's quote/metacharacter processing."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from aifactory.harness import codex


@pytest.mark.parametrize("nested", [False, True])
def test_native_npm_launch_preserves_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    nested: bool,
) -> None:
    shim = tmp_path / "npm with spaces" / "codex.cmd"
    packages = shim.parent / "node_modules/@openai"
    if nested:
        packages = packages / "codex/node_modules/@openai"
    native = packages / "codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe"
    native.parent.mkdir(parents=True)
    native.touch()
    monkeypatch.setattr(codex, "os", SimpleNamespace(name="nt", environ={}))
    monkeypatch.setattr("aifactory.harness.codex.shutil.which", lambda name: str(shim))
    command = [
        "codex",
        "exec",
        "-c",
        'model_reasoning_effort="medium"',
        "--",
        'a "quoted" prompt\n& | %VALUE% $(test)',
    ]
    assert codex.launch_command(command) == [str(native), *command[1:]]


def test_direct_executable_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codex, "os", SimpleNamespace(name="nt", environ={}))
    monkeypatch.setattr("aifactory.harness.codex.shutil.which", lambda name: "C:/Codex/codex.exe")
    assert codex.launch_command(["codex", "app-server"]) == ["C:/Codex/codex.exe", "app-server"]


def test_missing_native_binary_has_actionable_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codex, "os", SimpleNamespace(name="nt", environ={}))
    monkeypatch.setattr(
        "aifactory.harness.codex.shutil.which", lambda name: str(tmp_path / "codex.cmd")
    )
    with pytest.raises(OSError, match="CODEX_PATH"):
        codex.launch_command(["codex", "exec"])
