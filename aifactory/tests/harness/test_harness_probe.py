"""Harness smoke tests never invoke real models in the suite."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from test_harness_settings import choices

from aifactory.harness import load, probe, settings
from aifactory.web import create_multi_app


@pytest.mark.parametrize(
    "name,model", [("claude", "sonnet"), ("codex", "gpt-5.5"), ("pi", "openai/gpt-5.5")]
)
def test_trivial_turn_uses_selected_model_without_repo_tools(
    name: str, model: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(probe, "installed_path", lambda _: "fake")
    monkeypatch.setattr(probe, "launch_command", lambda cmd: cmd)
    if name == "pi":
        monkeypatch.setattr(load("pi"), "resolve_model", lambda _: ("openai", "gpt-5.5"))

    def run(command: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        assert command[command.index("--model") + 1] == model.split("/")[-1]
        assert command[-1] == probe.PROMPT
        assert kw["timeout"] == 60 and kw["stdin"] == subprocess.DEVNULL
        assert not (Path(kw["cwd"]) / ".git").exists()
        if name == "codex":
            assert command[command.index("--sandbox") + 1] == "read-only"
            Path(command[command.index("--output-last-message") + 1]).write_text("OK")
        elif name == "claude":
            assert command[command.index("--tools") + 1] == ""
        else:
            assert "--no-tools" in command and "--no-session" in command
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"result": "OK"}) if name == "claude" else "OK", ""
        )

    monkeypatch.setattr(subprocess, "run", run)
    assert probe.run_probe(name, model)["ok"] is True


@pytest.mark.parametrize("failure", ["exit", "answer", "timeout"])
def test_failed_turn_is_reported(failure: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probe, "installed_path", lambda _: "fake")
    monkeypatch.setattr(probe, "launch_command", lambda cmd: cmd)

    def run(command: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 60)
        return subprocess.CompletedProcess(
            command, 1 if failure == "exit" else 0, '{"result":"Wrong"}', ""
        )

    monkeypatch.setattr(subprocess, "run", run)
    assert probe.run_probe("claude", "sonnet")["ok"] is False


@pytest.mark.parametrize("name,flag", [("claude", "--effort"), ("codex", "model_reasoning_effort")])
def test_probe_uses_selected_thinking(
    name: str, flag: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(probe, "installed_path", lambda _: "fake")
    monkeypatch.setattr(probe, "launch_command", lambda cmd: cmd)

    def run(command: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        assert flag in " ".join(command)
        assert "high" in " ".join(command)
        if name == "codex":
            Path(command[command.index("--output-last-message") + 1]).write_text("OK")
        return subprocess.CompletedProcess(command, 0, '{"result":"OK"}', "")

    monkeypatch.setattr(subprocess, "run", run)
    assert probe.run_probe(name, "sonnet" if name == "claude" else "gpt-5.5", "high")["ok"]


def test_failed_model_cannot_be_default_or_shown_and_retest_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAIFA_HOME", str(tmp_path))
    settings.write(choices(), tmp_path)
    monkeypatch.setattr(probe, "run_probe", lambda *_: {"ok": False, "error": "Login failed"})
    app = create_multi_app(home=tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        response = client.post(
            "/api/machine/harnesses/test", json={"harness": "codex", "model": "gpt-5.5"}
        )
        assert response.status_code == 200 and response.json()["data"]["ok"] is False
        assert not app.state.limits.enabled("codex")
        assert app.state.limits.enabled("claude")
        assert client.post("/api/machine/harnesses", json=choices()).status_code == 400
        with pytest.raises(ValueError, match="failed its test"):
            settings.effective_override({}, None)
        monkeypatch.setattr(probe, "run_probe", lambda *_: {"ok": True, "answer": "OK"})
        assert (
            client.post(
                "/api/machine/harnesses/test", json={"harness": "codex", "model": "gpt-5.5"}
            ).json()["data"]["ok"]
            is True
        )
        assert app.state.limits.enabled("codex")
        assert client.post("/api/machine/harnesses", json=choices()).status_code == 200


def test_failed_models_never_fall_back_to_repository_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAIFA_HOME", str(tmp_path))
    monkeypatch.setattr(probe, "run_probe", lambda *_: {"ok": False, "error": "Failed"})
    probe.test_and_record("codex", "gpt-5.5", tmp_path)
    value = choices()
    value["default_harness"] = "claude"
    settings.write(value, tmp_path)
    with pytest.raises(ValueError, match="failed its test"):
        settings.effective_override({"harness": "codex"}, None)
    value["harnesses"]["claude"]["enabled"] = False
    value["default_harness"] = None
    settings.write(value, tmp_path)
    with pytest.raises(ValueError, match="no default harness"):
        settings.effective_override({}, None)
