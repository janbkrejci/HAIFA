"""Model-specific thinking choices, read locally without model requests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

from aifactory.harness import canonical


def codex_models() -> list[dict[str, Any]]:
    home = Path(os.environ.get("CODEX_HOME") or str(Path.home() / ".codex"))
    try:
        data = json.loads((home / "models_cache.json").read_text(encoding="utf-8"))
        return [m for m in data.get("models", []) if isinstance(m, dict)]
    except (OSError, ValueError, AttributeError, TypeError):
        return []


def codex_levels(model: str) -> list[str]:
    identifier = model.removeprefix("openai/")
    for item in codex_models():
        if item.get("slug") == identifier:
            return [
                "off" if level["effort"] == "none" else level["effort"]
                for level in item.get("supported_reasoning_levels", [])
                if isinstance(level, dict)
                and level.get("effort")
                in ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
            ]
    if identifier.startswith(("gpt-6", "gpt-5.6")):
        return ["low", "medium", "high", "xhigh", "max"]
    if identifier.startswith("gpt-5"):
        return ["low", "medium", "high", "xhigh"]
    return []


def claude_levels(model: str) -> list[str]:
    # https://platform.claude.com/docs/en/build-with-claude/effort
    identifier = {
        "opus": "claude-opus-5-5",
        "default": "claude-opus-5-5",
        "opusplan": "claude-opus-5-5",
        "sonnet": "claude-sonnet-5-5",
        "haiku": "claude-haiku-5-5",
        "fable": "claude-fable-5-1",
    }.get(model, model)
    all_levels = ["low", "medium", "high", "xhigh", "max"]
    if identifier.startswith(
        (
            "claude-opus-5",
            "claude-opus-4-7",
            "claude-opus-4-8",
            "claude-sonnet-5",
            "claude-haiku-5-5",
            "claude-fable-5",
            "claude-mythos-5",
            "claude-mythos-preview",
        )
    ):
        return all_levels
    if identifier.startswith(("claude-opus-4-6", "claude-sonnet-4-6")):
        return ["low", "medium", "high", "max"]
    if identifier.startswith("claude-opus-4-5"):
        return ["low", "medium", "high"]
    return []


@lru_cache(maxsize=8)
def pi_reasoning(binary: str) -> dict[str, bool]:
    try:
        result = subprocess.run(
            [binary, "--list-models"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        if result.returncode:
            return {}
        rows = [line.split() for line in result.stdout.splitlines()[1:]]
        return {f"{r[0]}/{r[1]}": r[4] == "yes" for r in rows if len(r) >= 5}
    except (OSError, subprocess.TimeoutExpired):
        return {}


def levels(harness: str, model: str) -> list[str]:
    name = canonical(harness)
    if name == "codex":
        return codex_levels(model)
    if name == "claude":
        return claude_levels(model)
    binary = os.environ.get("PI_PATH") or "pi"
    known = pi_levels(binary).get(model)
    if known is not None:
        return known
    reasoning = pi_reasoning(binary).get(model)
    # Custom models absent from the installed SDK retain verified baseline levels.
    return ["off", "minimal", "low", "medium", "high"] if reasoning else ["off"]


@lru_cache(maxsize=8)
def pi_levels(binary: str) -> dict[str, list[str]]:
    entry = shutil.which(binary)
    if not entry or not shutil.which("node"):
        return {}
    script = """
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const require = createRequire(process.argv[1]);
let sdk;
for (const name of ['@earendil-works/pi-ai/compat', '@mariozechner/pi-ai']) {
  try { sdk = await import(pathToFileURL(require.resolve(name))); break; } catch {}
}
if (!sdk?.getSupportedThinkingLevels) process.exit(1);
const result = {};
for (const provider of sdk.getProviders()) {
  for (const model of sdk.getModels(provider)) {
    result[`${provider}/${model.id}`] = sdk.getSupportedThinkingLevels(model);
  }
}
console.log(JSON.stringify(result));
"""
    try:
        result = subprocess.run(
            [
                "node",
                "--conditions=import",
                "--input-type=module",
                "-e",
                script,
                str(Path(entry).resolve()),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
        data = json.loads(result.stdout) if result.returncode == 0 else {}
        return {
            name: value
            for name, value in data.items()
            if isinstance(name, str)
            and isinstance(value, list)
            and all(isinstance(v, str) for v in value)
        }
    except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
        return {}


def validate(harness: str, model: str, thinking: str | None) -> None:
    if thinking is not None and thinking not in levels(harness, model):
        raise ValueError(f"thinking {thinking!r} is not supported by {harness}/{model}")


def default_level(harness: str, model: str) -> str | None:
    """A concrete computer baseline, never inherited from the roster agent."""
    supported = levels(harness, model)
    if not supported:
        return None
    name = canonical(harness)
    candidate = "medium"
    if name == "codex":
        for item in codex_models():
            if item.get("slug") == model.removeprefix("openai/"):
                candidate = item.get("default_reasoning_level") or candidate
                if candidate == "none":
                    candidate = "off"
                break
    elif name == "claude" or (name == "pi" and model.startswith("anthropic/claude-")):
        identifier = model.removeprefix("anthropic/")
        candidate = (
            "medium"
            if identifier in ("opus", "default", "opusplan", "haiku")
            or identifier.startswith(("claude-opus-5-5", "claude-haiku-5-5"))
            else "high"
        )
    return candidate if candidate in supported else supported[0]
