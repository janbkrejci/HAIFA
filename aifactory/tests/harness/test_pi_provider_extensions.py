"""A provider registered by a pi package reaches a run despite ``--no-extensions``."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from aifactory.engine import agent_pi
from aifactory.harness import probe

PACKAGE_EXTENSIONS = agent_pi._package_extensions  # before the autouse stub replaces it
HEADER = "provider  model  context  max-out  thinking  images\n"


def _package(root: Path, name: str, entry: str) -> Path:
    folder = root / name
    (folder / "src").mkdir(parents=True)
    (folder / "src" / "index.ts").write_text("export default () => {}\n")
    (folder / "package.json").write_text(json.dumps({"pi": {"extensions": [entry]}}))
    return folder


def test_package_registering_the_provider_is_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nous = _package(tmp_path, "pi-nousresearch-extension", "./src/index.ts")
    search = _package(tmp_path, "pi-web-search", "./src/index.ts")
    nous_entry = str((nous / "src" / "index.ts").resolve())
    providers = {
        None: "openrouter  poolside/laguna-s-2.1:free  262.1K  32.8K  yes  no\n",
        nous_entry: "nousresearch  poolside/laguna-s-2.1:free  262.1K  131.1K  yes  no\n"
        "openrouter  poolside/laguna-s-2.1:free  262.1K  32.8K  yes  no\n",
    }

    def run(command: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        if command[1:] == ["list"]:
            out = f"User packages:\n  git:nous\n    {nous}\n  npm:search\n    {search}\n"
            return subprocess.CompletedProcess(command, 0, out, "")
        assert "--no-extensions" in command and command[-1] == "--list-models"
        entry = command[command.index("-e") + 1] if "-e" in command else None
        return subprocess.CompletedProcess(command, 0, HEADER + providers.get(entry, ""), "")

    monkeypatch.setattr("aifactory.engine.agent_pi.subprocess.run", run)
    monkeypatch.setattr(agent_pi, "_package_extensions", PACKAGE_EXTENSIONS)
    PACKAGE_EXTENSIONS.cache_clear()
    try:
        assert agent_pi.provider_extensions("nousresearch") == ["-e", nous_entry]
        assert agent_pi.provider_extensions("openrouter") == []
    finally:
        PACKAGE_EXTENSIONS.cache_clear()


def test_probe_passes_the_provider_package_and_accepts_a_full_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(probe, "installed_path", lambda _: "pi")
    monkeypatch.setattr(probe, "launch_command", lambda cmd: cmd)
    monkeypatch.setattr(agent_pi, "_package_extensions", lambda: {"nous": ["/pkg/index.ts"]})
    monkeypatch.setattr(agent_pi, "resolve_model", lambda _: ("nous", "laguna:free"))
    seen: list[list[str]] = []

    def run(command: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, "OK.\n", "")

    monkeypatch.setattr(subprocess, "run", run)
    assert probe.run_probe("pi", "nous/laguna:free")["ok"] is True
    [command] = seen
    assert "--no-extensions" in command
    assert command[command.index("-e") + 1] == "/pkg/index.ts"
