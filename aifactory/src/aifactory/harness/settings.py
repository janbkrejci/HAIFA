"""Computer-local harness choices; no repository files are changed."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aifactory.harness import CLI_BINARIES, HARNESSES, canonical, load
from aifactory.harness import thinking as model_thinking
from aifactory.home import haifa_home

DEFAULT_MODELS = {"claude": "claude-opus-5-5", "codex": "gpt-6.1-sol", "pi": ""}
FILE = "harnesses.json"
TEST_FILE = "harness-tests.json"


class HarnessChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool = True
    model: str = ""
    thinking: str | None = None


class HarnessSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: int = 1
    default_harness: str | None = None
    harnesses: dict[str, HarnessChoice] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_choices(self) -> HarnessSettings:
        if self.version != 1 or set(self.harnesses) != set(HARNESSES):
            raise ValueError("settings must include claude, codex and pi (version 1)")
        if self.default_harness is not None:
            name = canonical(self.default_harness)
            choice = self.harnesses[name]
            if not choice.enabled or not choice.model:
                raise ValueError("default harness must be enabled and have a model")
            self.default_harness = name
        return self


def path(home: Path | None = None) -> Path:
    return (haifa_home() if home is None else home) / FILE


def read(home: Path | None = None) -> HarnessSettings | None:
    file = path(home)
    if not file.exists():
        return None
    return HarnessSettings.model_validate_json(file.read_text(encoding="utf-8"))


def write(value: dict[str, Any], home: Path) -> HarnessSettings:
    settings = HarnessSettings.model_validate(value)
    for name, choice in settings.harnesses.items():
        if choice.thinking is None:
            choice.thinking = model_thinking.default_level(name, choice.model)
        if choice.enabled:
            if choice.model:
                load(name).resolve_model(choice.model)
            model_thinking.validate(name, choice.model, choice.thinking)
    if settings.default_harness:
        name = settings.default_harness
        if test_failed(name, settings.harnesses[name].model, home):
            raise ValueError("default harness/model failed its test; test it successfully first")
    elif any(
        c.enabled and c.model and not test_failed(n, c.model, home)
        for n, c in settings.harnesses.items()
    ):
        raise ValueError("choose a default harness")
    home.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".harnesses-", dir=home)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(settings.model_dump_json(indent=2) + "\n")
        os.replace(temporary, path(home))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return settings


def catalog(home: Path) -> dict[str, Any]:
    settings = read(home)
    found = {
        name: bool(shutil.which(os.environ.get(env) or binary))
        for name, (env, binary) in CLI_BINARIES.items()
    }
    models: dict[str, list[str]] = {
        "claude": [DEFAULT_MODELS["claude"], *load("claude").MODEL_ALIASES],
        "codex": list(load("codex").CONTEXT_WINDOWS),
        "pi": [],
    }
    codex_home = Path(os.environ.get("CODEX_HOME") or str(Path.home() / ".codex"))
    try:
        cached = json.loads((codex_home / "models_cache.json").read_text(encoding="utf-8"))
        models["codex"] = list(
            dict.fromkeys(
                [
                    m["slug"]
                    for m in cached.get("models", [])
                    if isinstance(m, dict) and isinstance(m.get("slug"), str)
                ]
                + models["codex"]
            )
        )
    except (OSError, ValueError, AttributeError):
        pass
    if found["pi"]:
        models["pi"] = [f"{provider}/{model}" for provider, model, _ in load("pi")._pi_catalog()]
    choices = {
        name: {
            "enabled": found[name],
            "model": DEFAULT_MODELS[name] or next(iter(models[name]), ""),
        }
        for name in HARNESSES
    }
    default = next(
        (n for n in ("codex", "claude", "pi") if choices[n]["enabled"] and choices[n]["model"]),
        None,
    )
    data: dict[str, Any] = (
        settings.model_dump()
        if settings
        else {"version": 1, "default_harness": default, "harnesses": choices}
    )
    for name, choice in data["harnesses"].items():
        if choice["model"] and choice["model"] not in models[name]:
            models[name].append(choice["model"])
        if choice.get("thinking") is None:
            choice["thinking"] = model_thinking.default_level(name, choice["model"])
    return {
        "settings": data,
        "available": found,
        "models": models,
        "thinking_levels": {
            name: {model: model_thinking.levels(name, model) for model in available_models}
            for name, available_models in models.items()
        },
        "thinking_defaults": {
            name: {model: model_thinking.default_level(name, model) for model in available_models}
            for name, available_models in models.items()
        },
        "configured": settings is not None,
        "tests": read_tests(home),
    }


def read_tests(home: Path | None = None) -> dict[str, Any]:
    try:
        data = json.loads(((home or haifa_home()) / TEST_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def test_failed(name: str, model: str, home: Path | None = None) -> bool:
    return read_tests(home).get(name, {}).get(model, {}).get("ok") is False


def effective_override(
    values: dict[str, object], explicit: dict[str, str] | None
) -> dict[str, str]:
    settings = read()
    result: dict[str, str] = {}
    if settings and settings.default_harness:
        result["harness"] = settings.default_harness
    for key in ("harness", "model", "thinking"):
        value = values.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value.strip()
    supplied = {k: v.strip() for k, v in (explicit or {}).items() if v and v.strip()}
    if supplied.get("harness") and supplied["harness"] != result.get("harness"):
        result.pop("model", None)
    result.update(supplied)
    harness = result.get("harness")
    if settings and not harness:
        raise ValueError("no default harness enabled; fix computer harness settings")
    if harness:
        harness = result["harness"] = canonical(harness)
        if settings:
            choice = settings.harnesses[harness]
            if not choice.enabled:
                raise ValueError(f"harness {harness} is disabled on this computer")
            if "model" not in result and choice.model:
                if test_failed(harness, choice.model):
                    raise ValueError(
                        "default harness/model failed its test; fix computer harness settings"
                    )
                result["model"] = choice.model
            if "thinking" not in result:
                model = result.get("model", "")
                thinking = choice.thinking
                if thinking not in model_thinking.levels(harness, model):
                    thinking = model_thinking.default_level(harness, model)
                if thinking is not None:
                    result["thinking"] = thinking
    return result


def ensure_enabled(harness: str) -> None:
    settings = read()
    if settings and not settings.harnesses[canonical(harness)].enabled:
        raise ValueError(f"harness {harness} is disabled on this computer")
