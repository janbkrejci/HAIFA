"""Local roster editing; runs continue to read the committed base."""

from __future__ import annotations

import copy
import difflib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

from aifactory.config.errors import ConfigError, ConfigIssue
from aifactory.config.loader import PROMPT_KINDS, prompt_path
from aifactory.config.source import repo_root
from aifactory.harness import canonical, load
from aifactory.harness.config import SSSFConfig, normalize_raw
from aifactory.harness.override import THINKING_LEVELS

PRESETS = {
    "codex": {"harness": "codex", "model": "gpt-6.1-sol", "thinking": "medium"},
    "claude": {"harness": "claude", "model": "claude-opus-5-5", "thinking": "medium"},
}
FIELDS = ("harness", "coding_agent", "model", "thinking")


def _effective(raw: dict[str, Any]) -> list[dict[str, str]]:
    if not isinstance(raw.get("agents"), list) or not all(
        isinstance(a, dict) for a in raw["agents"]
    ):
        raise ValueError("agents must be a list of mappings")
    if raw.get("defaults") is not None and not isinstance(raw["defaults"], dict):
        raise ValueError("defaults must be a mapping")
    data = normalize_raw(raw)
    for agent in data["agents"]:
        agent.setdefault(
            "prompt_engineering",
            {kind: prompt_path(str(agent.get("name") or ""), kind) for kind in PROMPT_KINDS},
        )
    cfg = SSSFConfig.model_validate(data)
    names = [a.name for a in cfg.agents]
    if len(names) != len(set(names)):
        raise ValueError("duplicate agent names")
    result = []
    for agent in cfg.agents:
        if agent.thinking not in THINKING_LEVELS:
            raise ValueError(f"agent {agent.name!r}: invalid thinking {agent.thinking!r}")
        adapter = load(agent.harness)
        adapter.resolve_model(agent.model)
        if agent.harness == "codex":
            adapter.reasoning_effort(agent.model, agent.thinking)
        result.append(
            {
                "name": agent.name,
                "harness": agent.harness,
                "model": agent.model,
                "thinking": agent.thinking,
            }
        )
    return result


def _render(text: str, raw: dict[str, Any], updated: dict[str, Any]) -> tuple[str, bool]:
    """Patch block mappings using PyYAML marks, retaining surrounding comments.

    Flow mappings/aliases fall back to the existing YAML serializer, with a warning.
    Always verify the patched document has exactly the intended data before using it.
    """
    root = yaml.compose(text)
    edits: list[tuple[int, int, str]] = []

    def patch(node: MappingNode, before: dict[str, Any], after: dict[str, Any]) -> None:
        if node.flow_style:
            raise ValueError("flow mapping")
        present = set()
        for key, value in node.value:
            name = str(key.value)
            present.add(name)
            if name not in FIELDS or before.get(name) == after.get(name):
                continue
            if not isinstance(value, ScalarNode) or value.start_mark.line != value.end_mark.line:
                raise ValueError("non-scalar setting")
            if name in after:
                edits.append(
                    (
                        value.start_mark.index,
                        value.end_mark.index,
                        json.dumps(after[name], ensure_ascii=False),
                    )
                )
            else:
                start = text.rfind("\n", 0, key.start_mark.index) + 1
                end = text.find("\n", value.end_mark.index)
                edits.append((start, len(text) if end < 0 else end + 1, ""))
        additions = [k for k in after if k in FIELDS and k not in present]
        if additions:
            # Insert before the first mapping key, retaining a sequence's '- name'.
            first = node.value[0][0]
            end = text.find("\n", node.value[0][1].end_mark.index)
            if end < 0:
                raise ValueError("unterminated mapping")
            indent = " " * first.start_mark.column
            content = "".join(f"{indent}{k}: {json.dumps(after[k])}\n" for k in additions)
            edits.append((end + 1, end + 1, content))

    try:
        if not isinstance(root, MappingNode):
            raise ValueError("root")
        nodes = {str(k.value): v for k, v in root.value}
        default = nodes.get("defaults")
        if isinstance(default, MappingNode):
            patch(default, raw.get("defaults") or {}, updated["defaults"])
        elif updated.get("defaults") != raw.get("defaults"):
            raise ValueError("missing defaults")
        agents = nodes.get("agents")
        if not isinstance(agents, SequenceNode):
            raise ValueError("agents")
        for node, before, after in zip(agents.value, raw["agents"], updated["agents"], strict=True):
            if not isinstance(node, MappingNode):
                raise ValueError("agent")
            patch(node, before, after)
        rendered = text
        for start, end, replacement in sorted(edits, reverse=True):
            rendered = rendered[:start] + replacement + rendered[end:]
        if yaml.safe_load(rendered) == updated:
            return rendered, True
    except (ValueError, IndexError, KeyError, yaml.YAMLError):
        pass
    return yaml.safe_dump(updated, sort_keys=False, allow_unicode=True), False


def roster(
    repo: Path,
    *,
    change: bool = False,
    preset: str | None = None,
    agent: str | None = None,
    harness: str | None = None,
    model: str | None = None,
    thinking: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = repo_root(repo)
    path = root / ".factory/agents.yaml"
    try:
        text = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text)
        if not isinstance(raw, dict):
            raise ValueError("roster must be a mapping")
        before = _effective(raw)
        result: dict[str, Any] = {"path": str(path), "agents": before}
        if not change:
            return result
        if preset is not None and preset not in PRESETS:
            raise ValueError(f"unknown preset {preset!r}")
        settings = dict(PRESETS[preset]) if preset else {}
        for key, value in (("harness", harness), ("model", model), ("thinking", thinking)):
            if value is not None:
                if not value.strip():
                    raise ValueError(f"{key} cannot be empty")
                settings[key] = canonical(value) if key == "harness" else value
        if not settings:
            raise ValueError("set needs a preset or --harness/--model/--thinking")
        if "thinking" in settings and settings["thinking"] not in THINKING_LEVELS:
            raise ValueError(f"invalid thinking {settings['thinking']!r}")
        updated = copy.deepcopy(raw)
        # YAML aliases may share mappings. Editing a role must not edit its siblings.
        updated["agents"] = [copy.deepcopy(role) for role in raw["agents"]]
        if isinstance(raw.get("defaults"), dict):
            updated["defaults"] = copy.deepcopy(raw["defaults"])
        if agent is not None:
            target = next((a for a in updated["agents"] if a.get("name") == agent), None)
            if target is None:
                raise ValueError(f"unknown agent {agent!r}")
        else:
            target = updated.setdefault("defaults", {})
            if target is None:
                target = updated["defaults"] = {}
            if preset:
                for role in updated["agents"]:
                    for key in FIELDS:
                        role.pop(key, None)
        if "harness" in settings:
            target.pop("coding_agent", None)
        target.update(settings)
        after = _effective(updated)
        rendered, preserved = _render(text, raw, updated)
        diff = "".join(
            difflib.unified_diff(
                text.splitlines(True),
                rendered.splitlines(True),
                fromfile="agents.yaml",
                tofile="agents.yaml",
            )
        )
        result.update(
            agents=after,
            before=before,
            diff=diff,
            changed=bool(diff),
            dry_run=dry_run,
            comments_preserved=preserved,
        )
        if diff and not dry_run:
            fd, temporary = tempfile.mkstemp(prefix=".agents-", suffix=".yaml", dir=path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                    stream.write(rendered)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return result
    except (OSError, ValueError, TypeError, AttributeError, yaml.YAMLError) as exc:
        raise ConfigError([ConfigIssue(str(path), str(exc))]) from exc
