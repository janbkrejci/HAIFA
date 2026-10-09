"""A bounded, isolated one-turn harness/model smoke test."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aifactory.engine.utils import operator_env
from aifactory.harness import canonical, load
from aifactory.harness.check import installed_path
from aifactory.harness.codex import launch_command
from aifactory.harness.settings import TEST_FILE, read_tests
from aifactory.harness.thinking import validate

_lock = threading.Lock()
PROMPT = "Reply with exactly OK. Do not use tools."


def run_probe(name: str, model: str, thinking: str | None = None) -> dict[str, Any]:
    name = canonical(name)
    validate(name, model, thinking)
    if not model.strip():
        raise ValueError("select a model to test")
    adapter = load(name)
    provider, identifier = adapter.resolve_model(model)
    binary = installed_path(name)
    if binary is None:
        return {"ok": False, "error": "Harness není nainstalovaný."}
    with tempfile.TemporaryDirectory(prefix="haifa-harness-test-") as folder:
        output = Path(folder) / "answer.txt"
        if name == "claude":
            command = [
                binary,
                "-p",
                "--model",
                identifier,
                "--output-format",
                "json",
                "--tools",
                "",
                "--strict-mcp-config",
                "--setting-sources",
                "",
                "--no-session-persistence",
                "--permission-prompts",
                "none",
                PROMPT,
            ]
        elif name == "codex":
            command = [
                binary,
                "exec",
                "--model",
                identifier,
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "-c",
                'approval_policy="never"',
                "-c",
                "mcp_servers={}",
                "--output-last-message",
                str(output),
                "--",
                PROMPT,
            ]
        else:
            command = [
                binary,
                "-p",
                "--provider",
                provider,
                "--model",
                identifier,
                "--no-session",
                "--no-tools",
                "--no-extensions",
                "--no-skills",
                "--no-prompt-templates",
                "--no-context-files",
                "--no-mcp",
                PROMPT,
            ]
        if thinking is not None:
            if name == "claude":
                command[-1:-1] = ["--effort", thinking]
            elif name == "codex":
                command[-2:-2] = ["-c", f'model_reasoning_effort="{thinking}"']
            else:
                command[-1:-1] = ["--thinking", thinking]
        try:
            result = subprocess.run(
                launch_command(command),
                cwd=folder,
                env=operator_env(),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
                check=False,
            )
            if result.returncode:
                return {
                    "ok": False,
                    "error": f"Harness skončil s chybou (exit {result.returncode}). "
                    "Zkontrolujte přihlášení a dostupnost modelu.",
                }
            answer = result.stdout.strip()
            if name == "claude":
                payload = json.loads(answer)
                if not isinstance(payload, dict):
                    return {"ok": False, "error": "Claude vrátil neplatnou odpověď."}
                if payload.get("is_error"):
                    return {
                        "ok": False,
                        "error": "Claude vrátil chybu. "
                        "Zkontrolujte přihlášení a dostupnost modelu.",
                    }
                answer = str(payload.get("result", "")).strip()
            elif name == "codex":
                answer = output.read_text(encoding="utf-8").strip()
            if answer != "OK":
                return {"ok": False, "error": "Harness nevrátil očekávanou odpověď OK."}
            return {"ok": True, "answer": "OK", "error": None}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Harness neodpověděl do 60 sekund."}
        except (OSError, ValueError):
            return {"ok": False, "error": "Odpověď harnessu se nepodařilo přečíst."}


def test_and_record(
    name: str, model: str, home: Path, thinking: str | None = None
) -> dict[str, Any]:
    name = canonical(name)
    checked = run_probe(name, model) if thinking is None else run_probe(name, model, thinking)
    result = {**checked, "thinking": thinking, "at": datetime.now(UTC).isoformat()}
    with _lock:
        data = read_tests(home)
        data.setdefault(name, {})[model] = result
        home.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".harness-test-", dir=home)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream)
            os.replace(temporary, home / TEST_FILE)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return result
