"""Computer-local defaults, independent of repository configuration."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from aifactory.harness import settings, thinking
from aifactory.web import create_multi_app


def choices() -> dict[str, Any]:
    return {
        "version": 1,
        "default_harness": "codex",
        "harnesses": {
            "claude": {"enabled": True, "model": "sonnet"},
            "codex": {"enabled": True, "model": "gpt-5.5"},
            "pi": {"enabled": False, "model": ""},
        },
    }


def test_defaults_project_task_and_explicit_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAIFA_HOME", str(tmp_path))
    monkeypatch.setattr(thinking, "codex_models", lambda: [])
    assert settings.effective_override({}, None) == {}
    settings.write(choices(), tmp_path)
    assert settings.effective_override({}, None) == {
        "harness": "codex",
        "model": "gpt-5.5",
        "thinking": "medium",
    }
    assert settings.effective_override({"harness": "claude"}, None) == {
        "harness": "claude",
        "model": "sonnet",
        "thinking": "high",
    }
    assert (
        settings.effective_override({"harness": "claude", "model": "opus"}, None)["model"] == "opus"
    )
    assert settings.effective_override(
        {"harness": "claude", "model": "opus"}, {"harness": "codex"}
    ) == {"harness": "codex", "model": "gpt-5.5", "thinking": "medium"}
    assert settings.effective_override({}, {"model": "gpt-5"})["model"] == "gpt-5"
    with pytest.raises(ValueError, match="disabled"):
        settings.effective_override({"harness": "pi"}, None)
    with pytest.raises(ValueError, match="disabled"):
        settings.ensure_enabled("pi")


def test_invalid_settings_leave_previous_choices_intact(tmp_path: Path) -> None:
    settings.write(choices(), tmp_path)
    bad = choices()
    bad["harnesses"]["codex"]["enabled"] = False
    with pytest.raises(ValueError, match="default harness"):
        settings.write(bad, tmp_path)
    saved = settings.read(tmp_path)
    assert saved is not None and saved.default_harness == "codex"


def test_machine_api_reads_and_saves_outside_repositories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with TestClient(create_multi_app(home=tmp_path), base_url="http://127.0.0.1:4700") as client:
        initial = client.get("/api/machine/harnesses")
        assert initial.status_code == 200
        assert initial.json()["data"]["configured"] is False
        assert not settings.path(tmp_path).exists()
        response = client.post("/api/machine/harnesses", json=choices())
        assert response.status_code == 200
        saved = settings.read(tmp_path)
        assert saved is not None
        assert response.json()["data"]["settings"] == saved.model_dump()
        assert client.post("/api/machine/harnesses", json={"unknown": True}).status_code == 400
        assert (
            client.post(
                "/api/machine/harnesses",
                content="invalid",
                headers={"Content-Type": "application/json"},
            ).status_code
            == 400
        )
        saved = settings.read(tmp_path)
        assert saved is not None and saved.default_harness == "codex"


def test_computer_thinking_inherits_and_respects_model_capabilities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory.harness import thinking

    monkeypatch.setenv("HAIFA_HOME", str(tmp_path))
    monkeypatch.setattr(thinking, "codex_models", lambda: [])
    value = choices()
    value["harnesses"]["codex"]["thinking"] = "high"
    value["harnesses"]["claude"]["thinking"] = "max"
    settings.write(value, tmp_path)
    assert settings.effective_override({}, None)["thinking"] == "high"
    assert settings.effective_override({"harness": "claude"}, None)["thinking"] == "max"
    assert settings.effective_override({"thinking": "low"}, None)["thinking"] == "low"
    assert settings.effective_override({}, {"thinking": "medium"})["thinking"] == "medium"
    assert "thinking" not in settings.effective_override({"model": "unknown"}, None)
    value["harnesses"]["codex"]["thinking"] = "max"
    with pytest.raises(ValueError, match="not supported"):
        settings.write(value, tmp_path)
    saved = settings.read(tmp_path)
    assert saved is not None and saved.harnesses["codex"].thinking == "high"


def test_settings_remain_readable_when_saved_model_disappears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory.harness import load

    value = choices()
    value["harnesses"]["pi"] = {"enabled": True, "model": "custom/gone"}
    tmp_path.joinpath(settings.FILE).write_text(json.dumps(value))
    monkeypatch.setattr(shutil, "which", lambda _: None)

    def unavailable(_: str) -> tuple[str, str]:
        raise ValueError("model no longer available")

    monkeypatch.setattr(load("pi"), "resolve_model", unavailable)
    assert settings.catalog(tmp_path)["settings"]["harnesses"]["pi"]["model"] == "custom/gone"
    with pytest.raises(ValueError, match="no longer available"):
        settings.write(value, tmp_path)
    value["harnesses"]["pi"]["enabled"] = False
    settings.write(value, tmp_path)


def test_legacy_null_uses_computer_model_default_without_writing_on_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAIFA_HOME", str(tmp_path))
    monkeypatch.setattr(thinking, "codex_models", lambda: [])
    monkeypatch.setattr(shutil, "which", lambda _: None)
    original = json.dumps(choices())
    settings.path(tmp_path).write_text(original)
    data = settings.catalog(tmp_path)
    assert data["settings"]["harnesses"]["claude"]["thinking"] == "high"
    assert data["settings"]["harnesses"]["codex"]["thinking"] == "medium"
    assert settings.effective_override({}, None)["thinking"] == "medium"
    assert settings.effective_override({"thinking": "low"}, None)["thinking"] == "low"
    assert settings.effective_override({}, {"thinking": "high"})["thinking"] == "high"
    assert settings.path(tmp_path).read_text() == original
