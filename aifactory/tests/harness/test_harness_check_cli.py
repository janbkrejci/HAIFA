"""`factory harness check`: CLI presence and versions, without running a real CLI."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from aifactory.cli import main
from aifactory.harness import check
from cli_json import read_envelope, run_json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "check"))

VERSIONS = {
    "/bin/claude": ("2.1.0 (Claude Code)\n", ""),
    "/bin/codex": ("codex-cli 0.139.0\n", ""),
    "/bin/pi": ("", "\n0.87.1\n"),
    "/opt/x/codex": ("codex-cli 0.140.0\n", ""),
}


def _fake(monkeypatch: pytest.MonkeyPatch, present: set[str]) -> list[list[str]]:
    calls: list[list[str]] = []

    def which(binary: str) -> str | None:
        if binary.startswith("/"):
            return binary if binary in VERSIONS else None
        return f"/bin/{binary}" if binary in present else None

    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        out, err = VERSIONS[cmd[0]]
        return subprocess.CompletedProcess(cmd, 0, out, err)

    for var in ("CLAUDE_CODE_PATH", "CODEX_PATH", "PI_PATH"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(shutil, "which", which)
    monkeypatch.setattr(subprocess, "run", run)
    return calls


def _config(tmp_path: Path, roster: dict[str, str | None]) -> Path:
    agents = []
    for name, harness in roster.items():
        entry: dict[str, Any] = {"name": name, "model": "x"}
        if harness:
            entry["harness"] = harness
        agents.append(entry)
    path = tmp_path / "factory.config.yaml"
    path.write_text(yaml.safe_dump({"agents": agents}), encoding="utf-8", newline="\n")
    return path


def test_harness_check_reports_missing_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _fake(monkeypatch, {"claude", "pi"})
    assert main(["harness", "check"]) == 1
    out = capsys.readouterr().out
    assert "claude" in out and "2.1.0 (Claude Code)" in out
    assert "codex" in out and "not on PATH" in out
    assert "pi" in out and "0.87.1" in out
    assert calls == [["/bin/claude", "--version"], ["/bin/pi", "--version"]]


def test_harness_check_json_all_present(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake(monkeypatch, {"claude", "codex", "pi"})
    assert main(["harness", "check", "--json"]) == 0
    env = read_envelope(capsys)
    assert env["ok"] is True
    data = env["data"]
    assert [h["name"] for h in data["harnesses"]] == ["claude", "codex", "pi"]
    assert data["harnesses"][1] == {
        "name": "codex",
        "binary": "codex",
        "path": "/bin/codex",
        "version": "codex-cli 0.139.0",
        "error": None,
        "agents": [],
    }


def test_harness_check_only_what_config_uses(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    calls = _fake(monkeypatch, {"claude", "codex", "pi"})
    path = _config(tmp_path, {"planner": "claude", "builder": "pi", "reviewer": "claude_code"})
    assert main(["harness", "check", "--json", "--config", str(path)]) == 0
    data = read_envelope(capsys)["data"]
    assert [(h["name"], h["agents"]) for h in data["harnesses"]] == [
        ("claude", ["planner", "reviewer", "tester", "test-reviewer"]),
        ("pi", ["builder"]),
    ]
    assert calls == [["/bin/claude", "--version"], ["/bin/pi", "--version"]]

    assert main(["harness", "check", "--config", str(path)]) == 0
    out = capsys.readouterr().out
    assert "codex" not in out
    assert "planner, reviewer" in out


def test_harness_check_env_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake(monkeypatch, set())
    monkeypatch.setenv("CODEX_PATH", "/opt/x/codex")
    status = check.check_harness("codex")
    assert status.binary == "/opt/x/codex"
    assert status.path == "/opt/x/codex"
    assert status.version == "codex-cli 0.140.0"
    assert calls == [["/opt/x/codex", "--version"]]


def test_harness_check_nonzero_version_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch, {"claude", "codex", "pi"})

    def failing(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 2, "", "bad flag")

    monkeypatch.setattr(subprocess, "run", failing)
    status = check.check_harness("codex")
    assert status.version is None
    assert not status.ok
    assert status.error is not None and "exited 2" in status.error


def test_harness_without_subcommand_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["harness"]) == 0
    assert "check" in capsys.readouterr().out


def test_harness_check_bad_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    calls = _fake(monkeypatch, {"claude", "codex", "pi"})
    path = _config(tmp_path, {"builder": None})
    assert main(["harness", "check", "--config", str(path)]) == 2
    assert "harness is not set" in capsys.readouterr().err
    assert main(["harness", "check", "--config", str(tmp_path / "missing.yaml")]) == 2
    assert "missing.yaml" in capsys.readouterr().err
    assert calls == []


def test_harness_check_haifa_roster_relative_path(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from factory_check_repo import make_check_repo

    repo = make_check_repo(tmp_path / "repo")
    monkeypatch.chdir(repo)
    calls = _fake(monkeypatch, {"claude"})
    rc, obj = run_json(capsys, ["harness", "check", "--config", ".factory/agents.yaml", "--json"])
    assert rc == 0
    assert [(h["name"], h["agents"]) for h in obj["data"]["harnesses"]] == [
        ("claude", ["planner", "builder", "tester", "test-reviewer"])  # the last two from the seed
    ]
    assert calls == [["/bin/claude", "--version"]]
    _fake(monkeypatch, set())
    rc, obj = run_json(capsys, ["harness", "check", "--config", ".factory/agents.yaml", "--json"])
    assert rc == 1 and obj["error"]["code"] == "harness_missing"


def test_harness_check_roster_with_prompt_engineering_is_an_envelope(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    calls = _fake(monkeypatch, {"claude"})
    path = tmp_path / "agents.yaml"
    path.write_text(
        "agents:\n  - name: builder\n    harness: claude\n"
        "    prompt_engineering: {system: s.md, user: u.md}\n",
        encoding="utf-8",
    )
    rc, obj = run_json(capsys, ["harness", "check", "--config", str(path), "--json"])
    assert rc == 2
    assert obj["error"]["code"] == "invalid_config"
    assert "prompt_engineering" in obj["error"]["message"]
    rc, obj = run_json(
        capsys, ["harness", "check", "--config", str(tmp_path / "missing.yaml"), "--json"]
    )
    assert rc == 2
    assert obj["error"]["code"] == "invalid_config"
    assert "missing.yaml" in obj["error"]["message"]
    assert calls == []
