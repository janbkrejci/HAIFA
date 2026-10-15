"""Local roster editing; runs continue to read the committed base.

The roster shown is the effective one: the repo's ``agents.yaml`` with the agents it
inherits from the library. Changing an inherited agent adds an entry to ``agents.yaml``
that overrides only its bindings; a missing ``agents.yaml`` is created.
"""

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

from aifactory import yamlload
from aifactory.config.errors import ConfigError, ConfigIssue
from aifactory.config.loader import AGENTS_FILE, load_config
from aifactory.config.source import OverlaySource, WorktreeSource, repo_root
from aifactory.harness import canonical, load
from aifactory.harness.override import THINKING_LEVELS

PRESETS = {
    "codex": {"harness": "codex", "model": "gpt-6.1-sol", "thinking": "medium"},
    "claude": {"harness": "claude", "model": "claude-opus-5-5", "thinking": "medium"},
}
FIELDS = ("harness", "coding_agent", "model", "thinking")


def _effective(root: Path, text: str) -> list[dict[str, Any]]:
    """The effective agents with ``agents.yaml`` as `text` (library agents included).

    A ``prompt_engineering`` key a roster may still carry is left out here; only the
    bindings matter.
    """
    raw = yamlload.safe_load(text) if text.strip() else None
    agents = raw.get("agents") if isinstance(raw, dict) else None
    if (
        isinstance(raw, dict)
        and isinstance(agents, list)
        and any(isinstance(a, dict) and "prompt_engineering" in a for a in agents)
    ):
        raw = {
            **raw,
            "agents": [
                {k: v for k, v in a.items() if k != "prompt_engineering"}
                if isinstance(a, dict)
                else a
                for a in agents
            ],
        }
        text = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True)
    source = OverlaySource(WorktreeSource(root), {AGENTS_FILE: text.encode("utf-8")})
    try:
        cfg = load_config(source)
    except ConfigError as exc:
        raise ValueError("; ".join(f"{i.path}: {i.message}" for i in exc.issues)) from exc
    names = [a.name for a in cfg.agents.agents]
    if len(names) != len(set(names)):
        raise ValueError("duplicate agent names")
    result = []
    for agent in cfg.agents.agents:
        if agent.thinking not in THINKING_LEVELS:
            raise ValueError(f"agent {agent.name!r}: invalid thinking {agent.thinking!r}")
        harness = canonical(str(agent.coding_agent))
        adapter = load(harness)
        adapter.resolve_model(agent.model)
        if harness == "codex":
            adapter.reasoning_effort(agent.model, agent.thinking)
        result.append(
            {
                "name": agent.name,
                "harness": harness,
                "model": agent.model,
                "thinking": agent.thinking,
                "origin": "library" if f"agent/{agent.name}" in cfg.inherited else "repo",
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
        if yamlload.safe_load(rendered) == updated:
            return rendered, True
    except (ValueError, IndexError, KeyError, yaml.YAMLError):
        pass
    return yaml.safe_dump(updated, sort_keys=False, allow_unicode=True), False


def _with_entry(text: str, agent: str) -> str:
    """`text` with an ``agents.yaml`` entry for `agent` (an override of a library agent)."""
    from aifactory.config.yamledit import edit_yaml, roster_add

    return edit_yaml(text, lambda doc: roster_add(doc, {"name": agent}))


RESETTABLE = ("harness", "model", "thinking")


def _finish(
    root: Path,
    path: Path,
    original: str,
    rendered: str,
    before: list[dict[str, Any]],
    result: dict[str, Any],
    dry_run: bool,
    preserved: bool,
) -> dict[str, Any]:
    """Validate `rendered`, add the diff to `result` and write it unless `dry_run`."""
    after = _effective(root, rendered)
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(True),
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
        path.parent.mkdir(parents=True, exist_ok=True)
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


def _reset(
    root: Path,
    path: Path,
    original: str,
    before: list[dict[str, Any]],
    result: dict[str, Any],
    agent: str | None,
    reset: tuple[str, ...],
    dry_run: bool,
    preset: str | None,
    values: tuple[str | None, ...],
) -> dict[str, Any]:
    """Remove the overrides `reset` of `agent` from ``agents.yaml``."""
    from aifactory.config.yamledit import edit_yaml, roster_remove, roster_set

    if agent is None:
        raise ValueError("reset needs an agent")
    if preset is not None or any(v is not None for v in values):
        raise ValueError("reset cannot be combined with a preset or --harness/--model/--thinking")
    unknown = [k for k in reset if k not in RESETTABLE]
    if unknown:
        raise ValueError(f"cannot reset {', '.join(map(repr, unknown))}")
    if agent not in {a["name"] for a in before}:
        raise ValueError(f"unknown agent {agent!r}")
    keys = {k for k in reset} | ({"coding_agent"} if "harness" in reset else set())
    raw = yamlload.safe_load(original) if original.strip() else {}
    listed = raw.get("agents") if isinstance(raw, dict) else None
    entry = next(
        (a for a in listed or [] if isinstance(a, dict) and a.get("name") == agent),
        None,
    )
    if entry is None or not keys & set(entry):
        return _finish(root, path, original, original, before, result, dry_run, True)
    library = any(a["name"] == agent and a["origin"] == "library" for a in before)

    def change(doc: Any) -> None:
        roster_set(doc, agent, dict.fromkeys(sorted(keys)))
        remaining = next(
            (a for a in doc.get("agents") or [] if isinstance(a, dict) and a.get("name") == agent),
            None,
        )
        if library and remaining is not None and set(remaining) <= {"name"}:
            roster_remove(doc, agent)

    rendered = edit_yaml(original, change)
    return _finish(root, path, original, rendered, before, result, dry_run, True)


def _bindings(root: Path, text: str) -> dict[str, dict[str, str]]:
    """Harness, model, thinking and origin per agent with ``agents.yaml`` as `text`.

    Unlike ``_effective`` the models are not checked against the harness.
    """
    source = OverlaySource(WorktreeSource(root), {AGENTS_FILE: text.encode("utf-8")})
    try:
        cfg = load_config(source)
    except ConfigError as exc:
        raise ValueError("; ".join(f"{i.path}: {i.message}" for i in exc.issues)) from exc
    return {
        agent.name: {
            "harness": canonical(str(agent.coding_agent)),
            "model": agent.model,
            "thinking": agent.thinking,
            "origin": "library" if f"agent/{agent.name}" in cfg.inherited else "repo",
        }
        for agent in cfg.agents.agents
    }


def inherited_bindings(root: Path) -> dict[str, dict[str, Any]]:
    """Per agent: which bindings ``agents.yaml`` overrides, and the values without them.

    ``overridden`` lists ``harness`` (also for a legacy ``coding_agent``), ``model`` and
    ``thinking`` set by the agent's entry in the working tree. ``inherited`` holds the
    values without those entries (the library and the roster defaults) for a library
    agent, None for the repo's own copy. A roster that does not load gives ``{}``.
    """
    path = repo_root(root) / AGENTS_FILE
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        raw = yamlload.safe_load(text) if text.strip() else {}
        if not isinstance(raw, dict):
            return {}
        overridden: dict[str, list[str]] = {}
        for entry in raw.get("agents") or []:
            if not isinstance(entry, dict):
                continue
            fields = overridden.setdefault(str(entry.get("name")), [])
            for key in RESETTABLE:
                legacy = key == "harness" and "coding_agent" in entry
                if (key in entry or legacy) and key not in fields:
                    fields.append(key)
        # a legacy ``prompt_engineering`` key does not load; only the bindings matter
        clean = {
            **raw,
            "agents": [
                {k: v for k, v in a.items() if k != "prompt_engineering"}
                if isinstance(a, dict)
                else a
                for a in raw.get("agents") or []
            ],
        }
        current = _bindings(
            root, yaml.safe_dump(clean, sort_keys=False, allow_unicode=True) if raw else ""
        )
        library = {name for name, a in current.items() if a["origin"] == "library"}
        stripped = {
            **clean,
            "agents": [
                {k: v for k, v in a.items() if k not in FIELDS}
                if isinstance(a, dict) and a.get("name") in library
                else a
                for a in clean["agents"]
            ],
        }
        base = _bindings(root, yaml.safe_dump(stripped, sort_keys=False, allow_unicode=True))
    except (OSError, ValueError, TypeError, AttributeError, KeyError, yaml.YAMLError):
        return {}
    return {
        name: {
            "overridden": overridden.get(name, []),
            "inherited": {k: base[name][k] for k in RESETTABLE}
            if name in library and name in base
            else None,
        }
        for name in current
    }


def roster(
    repo: Path,
    *,
    change: bool = False,
    preset: str | None = None,
    agent: str | None = None,
    harness: str | None = None,
    model: str | None = None,
    thinking: str | None = None,
    reset: tuple[str, ...] = (),
    dry_run: bool = False,
) -> dict[str, Any]:
    """The effective roster; with `change`, set bindings or `reset` an agent's overrides.

    `reset` names bindings (``harness``, ``model``, ``thinking``) of `agent` whose override
    in ``agents.yaml`` is removed, so the inherited value applies again. An entry of a
    library agent that keeps only its name is removed as well.
    """
    root = repo_root(repo)
    path = root / AGENTS_FILE
    try:
        original = path.read_text(encoding="utf-8") if path.is_file() else ""
        before = _effective(root, original)
        result: dict[str, Any] = {"path": str(path), "agents": before}
        if not change:
            return result
        if reset:
            return _reset(
                root,
                path,
                original,
                before,
                result,
                agent,
                reset,
                dry_run,
                preset,
                (harness, model, thinking),
            )
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
        text = original
        raw = yamlload.safe_load(text) if text.strip() else {}
        if not isinstance(raw, dict):
            raise ValueError("roster must be a mapping")
        listed = raw.get("agents") or []
        if agent is not None and not any(
            isinstance(a, dict) and a.get("name") == agent for a in listed
        ):
            if agent not in {a["name"] for a in before}:
                raise ValueError(f"unknown agent {agent!r}")
            text = _with_entry(text, agent)
            raw = yamlload.safe_load(text)
        raw.setdefault("agents", [])
        updated = copy.deepcopy(raw)
        # YAML aliases may share mappings. Editing a role must not edit its siblings.
        updated["agents"] = [copy.deepcopy(role) for role in raw["agents"]]
        if isinstance(raw.get("defaults"), dict):
            updated["defaults"] = copy.deepcopy(raw["defaults"])
        if agent is not None:
            target = next(a for a in updated["agents"] if a.get("name") == agent)
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
        rendered, preserved = (
            _render(text, raw, updated)
            if text.strip()
            else (
                yaml.safe_dump(updated, sort_keys=False, allow_unicode=True),
                True,
            )
        )
        return _finish(root, path, original, rendered, before, result, dry_run, preserved)
    except (OSError, ValueError, TypeError, AttributeError, KeyError, yaml.YAMLError) as exc:
        raise ConfigError([ConfigIssue(str(path), str(exc))]) from exc
