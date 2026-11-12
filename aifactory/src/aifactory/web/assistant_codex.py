"""Guide-only Codex launch policy, separate from the factory task launch.

Audited against codex-cli 0.167.2. Configuration flags alone are insufficient:
the model catalog can register apply_patch, code-mode and model-specific tools.
We use an offline copy of the bundled catalog with those capabilities removed,
disable ambient integrations, and expose just the gate through stdio MCP.
Unknown CLI versions and unknown models fail closed. No operator config is edited.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from aifactory.engine.data_types import AgentRequest, AgentResult
from aifactory.engine.utils import operator_env
from aifactory.harness import codex

SUPPORTED_VERSION = "codex-cli 0.167.2"
DISABLED_FEATURES = (
    "shell_tool",
    "shell_snapshot",
    "view_image",
    "apps",
    "plugins",
    "remote_plugin",
    "hooks",
    "image_generation",
    "browser_use",
    "computer_use",
    "multi_agent",
    "memories",
    "code_mode",
    "goals",
    "skill_search",
    "skill_mcp_dependency_install",
)


def _inspect(args: list[str], cwd: str) -> str:
    # debug models has no --ignore-user-config switch. Inspect the bundled
    # catalog in a separate, unauthenticated home as well, so a user's custom
    # model_catalog_json cannot supply model instructions or extra capabilities.
    inspection_home = Path(cwd).parent / "codex-inspect"
    inspection_home.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        codex.launch_command([codex.CODEX_PATH, *args]),
        cwd=cwd,
        env={**operator_env(), "CODEX_HOME": str(inspection_home.resolve())},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=True,
    )
    return result.stdout


def restricted_catalog(catalog: dict[str, Any], model: str) -> dict[str, Any]:
    """Keep model behavior/limits, remove every model-owned execution capability."""
    models = catalog.get("models")
    if not isinstance(models, list):
        raise ValueError("Codex returned an invalid bundled model catalog")
    selected = next((entry for entry in models if entry.get("slug") == model), None)
    if selected is None:
        raise ValueError(f"model {model!r} is not in Codex's bundled catalog")
    return {
        "models": [
            {
                **selected,
                "shell_type": "disabled",
                "apply_patch_tool_type": None,
                "experimental_supported_tools": [],
                "supports_search_tool": False,
                "tool_mode": "direct",
                # The lite/code-mode transport does not expose direct MCP tools.
                "use_responses_lite": False,
                "node_repl_disabled": True,
                "multi_agent_version": None,
                "multi_agent_reasoning_effort": None,
                "model_messages": None,
            }
        ]
    }


def _toml(value: Any) -> str:
    if isinstance(value, dict):
        return "{" + ", ".join(f"{json.dumps(k)} = {_toml(v)}" for k, v in value.items()) + "}"
    return json.dumps(value)


def isolated_home(home: Path) -> Path:
    """Keep global instructions/skills out without cloning login/refresh tokens.

    Codex's file credential backend resolves auth.json symlinks before atomic
    refreshes, so the normal login remains the sole credential store. Windows
    needs symlink support (Developer Mode), or a separate login in this home.
    A failed link never falls back to the operator's instruction directory.
    """
    directory = home / "assistant" / "codex"
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("AGENTS.md", "AGENTS.override.md"):
        if (directory / name).exists() or (directory / name).is_symlink():
            raise ValueError(f"the isolated Codex guide home must not contain {name}: {directory}")
    original = Path(operator_env().get("CODEX_HOME") or Path.home() / ".codex").resolve()
    source = original / "auth.json"
    target = directory / "auth.json"
    if source.is_file() and not target.exists():
        try:
            target.symlink_to(source)
        except FileExistsError:
            # Another guide thread may have initialized the shared home.
            if not target.is_symlink() or target.resolve() != source.resolve():
                raise ValueError(
                    "the guide login link does not point to the current Codex login"
                ) from None
        except OSError as exc:
            raise ValueError(
                "cannot share the Codex login with the isolated guide home. "
                "On Windows enable Developer Mode for symlinks, or run codex login "
                f"with CODEX_HOME set to {directory}. Factory tasks are unaffected."
            ) from exc
    return directory.resolve()


def launch_args(request: AgentRequest, home: Path, repo_id: str | None) -> list[str]:
    """Build per-invocation restrictions for both new and resumed conversations."""
    version = _inspect(["--version"], request.cwd).strip()
    if version != SUPPORTED_VERSION:
        raise ValueError(
            f"the Codex guide requires {SUPPORTED_VERSION}; found {version!r}. "
            "Other versions have not been verified for guide isolation. "
            "Factory task execution is unaffected."
        )
    _, model = codex.resolve_model(request.model)
    # No network or account access: inspect only the catalog shipped in this binary.
    catalog = json.loads(_inspect(["debug", "models", "--bundled"], request.cwd))
    path = Path(request.session_dir) / "guide-models.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(restricted_catalog(catalog, model)), encoding="utf-8")
    server_args = ["-X", "utf8", "-m", "aifactory.web.assistant_mcp", "--home", str(home)]
    if repo_id is not None:
        server_args += ["--repo", repo_id]
    config: dict[str, Any] = {
        "model_catalog_json": str(path.resolve()),
        "project_doc_max_bytes": 0,
        "skills.include_instructions": False,
        "features.skip_host_skill_discovery": True,
        "tools.update_plan.enabled": False,
        "tools.experimental_request_user_input.enabled": False,
        "web_search": "disabled",
        # Replace the whole table rather than merging another server into ambient config.
        "mcp_servers": {
            "haifa_guide": {
                "command": sys.executable,
                "args": server_args,
                "required": True,
                "enabled_tools": ["guide"],
                "env": {
                    "HAIFA_HOME": str(home),
                    "HAIFA_GUIDE_REPO": repo_id or "",
                    "HAIFA_RUN_ID": operator_env().get("HAIFA_RUN_ID", "guide"),
                },
            }
        },
        **{f"features.{name}": False for name in DISABLED_FEATURES},
    }
    args = ["--strict-config", "--ignore-rules"]
    for name, value in config.items():
        args += ["-c", f"{name}={_toml(value)}"]
    return args


def run(request: AgentRequest, *, home: Path, repo_id: str | None, **callbacks: Any) -> AgentResult:
    """Use the ordinary adapter's sessions, streaming and usage with guide restrictions."""
    if request.allowed_commands != ["./guide", "./guide *"]:
        raise ValueError("the Codex guide requires the guide command allowlist")
    args = launch_args(request, home, repo_id)
    # The system template still describes the Claude shell transport; tell Codex
    # how to use the same gate without ever enabling a shell.
    request = request.model_copy(
        update={
            "system_prompt": request.system_prompt
            + "\nTransport: use the haifa_guide MCP guide tool for every ./guide command. "
            "Pass its arguments in argv without ./guide. No shell or file tools are available."
        }
    )
    return codex.run(
        request,
        extra_args=args,
        env_overrides={"CODEX_HOME": str(isolated_home(home))},
        **callbacks,
    )
