"""The ``machine`` rule group: problems fixed on this machine, nothing to commit.

Every query goes through ``ctx.machine``. ``--offline`` skips the calls to the hosting
(``gh auth status``, ``az account show``) and to the harness logins (``claude auth
status``, ``codex login status``, ``pi auth check``, ``pi --list-models``). Outside a
git repository only the rules with ``needs_repo=False`` run.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from aifactory.check.context import CheckContext
from aifactory.check.machine import Probe
from aifactory.check.model import Finding, Rule, RuleGroup, Severity
from aifactory.config.errors import ConfigError
from aifactory.config.settings import LOCAL_PORT_IGNORED, load_local_checked
from aifactory.config.source import LOCAL_FILE
from aifactory.engine.utils import flag_value
from aifactory.harness import CLI_BINARIES, HARNESSES
from aifactory.harness.check import harnesses_in_config
from aifactory.home import env_file
from aifactory.providers.azure import PAT_ENV

PLATFORMS = ("darwin", "linux", "wsl")
OVERRIDES = (
    "CLAUDE_SAFE_MODE",
    "CLAUDE_MCP_CONFIG",
    "CLAUDE_PERMISSION_MODE",
    "CODEX_SAFE_MODE",
    "CODEX_SANDBOX",
    "PI_SAFE_MODE",
)
LOGIN_FIX = {
    "claude": "claude auth login",
    "codex": "codex login",
    "pi": "pi auth login",
}
PiMatch = Literal["ok", "missing", "ambiguous"]


def _outside(ctx: CheckContext) -> bool:
    return not ctx.in_repo


# -- platform and tools --


def platform(ctx: CheckContext) -> Iterator[Finding]:
    name = ctx.machine.platform()
    if name in PLATFORMS:
        return
    yield Finding(
        "unsupported_platform",
        "machine",
        "error",
        f"the platform '{name}' is not supported",
        "HAIFA runs on macOS, Linux and WSL; on Windows use WSL",
    )


def _git_value(ctx: CheckContext, key: str, env_suffix: str) -> bool:
    env = ctx.machine.env
    if (env(f"GIT_AUTHOR_{env_suffix}") or "").strip() and (
        env(f"GIT_COMMITTER_{env_suffix}") or ""
    ).strip():
        return True
    cwd = ctx.main if ctx.in_repo else None
    probe = ctx.machine.run(["git", "config", "--get", key], cwd=cwd)
    return probe is not None and probe.returncode == 0 and bool(probe.stdout.strip())


def tools(ctx: CheckContext) -> Iterator[Finding]:
    if ctx.machine.which("git") is None:
        yield Finding(
            "git_missing",
            "machine",
            "error",
            "git is not on PATH",
            "install git (https://git-scm.com)",
        )
    else:
        missing = [
            key
            for key, suffix in (("user.name", "NAME"), ("user.email", "EMAIL"))
            if not _git_value(ctx, key, suffix)
        ]
        if missing:
            yield Finding(
                "git_identity_missing",
                "machine",
                "error",
                f"git has no {' and no '.join(missing)}; factory cannot commit",
                " and ".join(f'git config --global {key} "..."' for key in missing),
            )
    if ctx.machine.which("uv") is None:
        yield Finding(
            "uv_missing",
            "machine",
            "warning",
            "uv is not on PATH; it installs and upgrades HAIFA (factory upgrade)",
            "install uv (https://docs.astral.sh/uv/)",
        )


# -- harnesses --


def harnesses(ctx: CheckContext) -> Iterator[Finding]:
    if _outside(ctx):
        for name in HARNESSES:
            status = ctx.machine.harness(name, [])
            if status.ok:
                continue
            env_var = CLI_BINARIES[name][0]
            yield Finding(
                "harness_missing",
                "machine",
                "info",
                f"harness {name} ({status.binary}) is not installed (optional; needed by "
                "repos whose roster uses it)",
                f"install {status.binary} or point {env_var} at it",
            )
        return
    if ctx.roster is None:
        return
    for name, agents in harnesses_in_config(ctx.roster).items():
        status = ctx.machine.harness(name, agents)
        if status.ok:
            continue
        env_var = CLI_BINARIES[name][0]
        yield Finding(
            "harness_missing",
            "machine",
            "error",
            f"harness {name} ({status.binary}): {status.error or 'not usable'}; "
            f"used by {', '.join(agents)}",
            f"install {status.binary} or point {env_var} at it",
        )


def node(ctx: CheckContext) -> Iterator[Finding]:
    if ctx.roster is None:
        return
    agents = harnesses_in_config(ctx.roster).get("pi")
    if not agents or ctx.machine.which("node") is not None:
        return
    yield Finding(
        "node_missing",
        "machine",
        "error",
        f"node is not on PATH; the pi harness needs it (agents: {', '.join(agents)})",
        "install Node.js (https://nodejs.org)",
    )


def _binary(ctx: CheckContext, name: str) -> str:
    env_var, default = CLI_BINARIES[name]
    return ctx.machine.env(env_var) or default


def _pi_models(ctx: CheckContext) -> dict[str, list[str]]:
    """Model -> pi agents using it, in roster order."""
    models: dict[str, list[str]] = {}
    if ctx.roster is None:
        return models
    for agent in ctx.roster.agents:
        if str(agent.coding_agent) == "pi" and agent.model:
            models.setdefault(agent.model, []).append(agent.name)
    return models


def _pi_login_failed(probe: Probe | None) -> bool:
    if probe is None or probe.returncode != 0:
        return True
    try:
        data = json.loads(probe.stdout)
    except ValueError:
        return False
    if not isinstance(data, dict):
        return False
    return data.get("ok") is False or data.get("authenticated") is False


def pi_catalog(text: str) -> list[tuple[str, str]]:
    """(provider, model id) rows of ``pi --list-models`` (the header line is skipped)."""
    rows: list[tuple[str, str]] = []
    for line in text.splitlines()[1:]:
        columns = line.split()
        if len(columns) >= 2:
            rows.append((columns[0], columns[1]))
    return rows


def match_pi_model(catalog: list[tuple[str, str]], pattern: str) -> PiMatch:
    """How pi resolves ``pattern`` against its catalog, as ``agent_pi.resolve_model``."""
    if "/" in pattern:
        provider, model_id = pattern.split("/", 1)
        if (provider, model_id) in catalog:
            return "ok"
    matches = [(p, m) for p, m in catalog if pattern == m or pattern in m]
    exact = [match for match in matches if match[1] == pattern or match[1].endswith("/" + pattern)]
    if len(exact) == 1 or len(matches) == 1:
        return "ok"
    return "missing" if not matches else "ambiguous"


def logins(ctx: CheckContext) -> Iterator[Finding]:
    """Is every harness logged in? Skipped with ``--offline``."""
    if ctx.offline:
        return
    severity: Severity
    if _outside(ctx):
        wanted: dict[str, list[str]] = {name: [] for name in HARNESSES}
        severity = "warning"
    else:
        if ctx.roster is None:
            return
        wanted = harnesses_in_config(ctx.roster)
        severity = "error"
    pi_models = _pi_models(ctx)
    for name, agents in wanted.items():
        binary = _binary(ctx, name)
        if ctx.machine.which(binary) is None:
            continue
        who = f" (agents: {', '.join(agents)})" if agents else ""
        if name == "pi":
            yield from _pi_logins(ctx, binary, pi_models, severity)
            continue
        argv = [binary, "auth", "status"] if name == "claude" else [binary, "login", "status"]
        probe = ctx.machine.run(argv)
        if probe is None or probe.returncode != 0:
            yield Finding(
                "harness_login",
                "machine",
                severity,
                f"{name} is not logged in{who}",
                LOGIN_FIX[name],
            )


def _pi_logins(
    ctx: CheckContext, binary: str, models: dict[str, list[str]], severity: Severity
) -> Iterator[Finding]:
    for model, agents in models.items():
        probe = ctx.machine.run(
            [binary, "auth", "check", "--model", model, "--json", "--no-refresh"]
        )
        if _pi_login_failed(probe):
            yield Finding(
                "harness_login",
                "machine",
                severity,
                f"pi is not logged in for model {model} (agents: {', '.join(agents)})",
                f"{LOGIN_FIX['pi']}: log in to the provider of {model}",
            )
    if not models or _outside(ctx):
        return
    listed = ctx.machine.run([binary, "--list-models"], timeout=30)
    if listed is None or listed.returncode != 0:
        return
    catalog = pi_catalog(listed.stdout)
    for model, agents in models.items():
        result = match_pi_model(catalog, model)
        if result == "ok":
            continue
        what = "is not in" if result == "missing" else "matches several models of"
        yield Finding(
            "pi_model_unknown",
            "machine",
            "error",
            f"model {model} {what} pi --list-models (agents: {', '.join(agents)})",
            "register/authenticate it in pi, or fix model in .factory/agents.yaml",
        )


# -- repo-specific machine rules --


def just(ctx: CheckContext) -> Iterator[Finding]:
    if ctx.machine.which("just") is not None:
        return
    needed = ctx.test_argv[0] == "just"
    yield Finding(
        "just_missing",
        "machine",
        "error" if needed else "warning",
        "just is not on PATH"
        + (f" (the test command is '{' '.join(ctx.test_argv)}')" if needed else ""),
        "install just (https://just.systems)",
    )


def test_program(ctx: CheckContext) -> Iterator[Finding]:
    program = ctx.test_argv[0]
    if program == "just" or ("/" in program and not program.startswith("/")):
        return
    if ctx.machine.which(program) is not None:
        return
    yield Finding(
        "test_command_missing",
        "machine",
        "error",
        f"the test command '{' '.join(ctx.test_argv)}' runs {program}, which is not on PATH",
        f"install {program}, or fix test_command in .factory/config.yaml",
    )


def local(ctx: CheckContext) -> Iterator[Finding]:
    try:
        _settings, warnings = load_local_checked(ctx.main)
    except ConfigError as exc:
        for issue in exc.issues:
            yield Finding(
                "local_config_invalid",
                "machine",
                "warning",
                f"{issue.path}: {issue.message}",
                "fix .factory/local.yaml (trace_db)",
            )
        return
    if any(warning.startswith(LOCAL_PORT_IGNORED) for warning in warnings):
        yield Finding(
            "local_port_ignored",
            "machine",
            "warning",
            f"{LOCAL_FILE}: port is ignored; the dashboard port is in the registry "
            "(dashboard.yaml)",
            "smaž řádek port z .factory/local.yaml",
        )


def _failed(ctx: CheckContext, argv: list[str]) -> bool:
    probe = ctx.machine.run(argv)
    return probe is None or probe.returncode != 0


def hosting(ctx: CheckContext) -> Iterator[Finding]:
    provider = ctx.settings.git_provider
    if provider == "local":
        return
    if provider == "github":
        if ctx.machine.which("gh") is None:
            yield Finding(
                "gh_missing",
                "machine",
                "error",
                "git_provider is github but gh is not on PATH",
                "install the GitHub CLI (https://cli.github.com)",
            )
        elif not ctx.offline and _failed(ctx, ["gh", "auth", "status", "--hostname", "github.com"]):
            yield Finding(
                "gh_login",
                "machine",
                "error",
                "gh is not logged in to github.com",
                "gh auth login",
            )
    else:
        if ctx.machine.which("az") is None:
            yield Finding(
                "az_missing",
                "machine",
                "error",
                "git_provider is azure but az is not on PATH",
                "install the Azure CLI",
            )
        else:
            if _failed(
                ctx, ["az", "extension", "show", "--name", "azure-devops", "--output", "json"]
            ):
                yield Finding(
                    "az_devops_missing",
                    "machine",
                    "error",
                    "the az devops extension is not installed",
                    "az extension add --name azure-devops",
                )
            if (
                not ctx.offline
                and not (ctx.machine.env(PAT_ENV) or "").strip()
                and _failed(ctx, ["az", "account", "show", "--output", "json"])
            ):
                yield Finding(
                    "az_login",
                    "machine",
                    "error",
                    f"az is not logged in and {PAT_ENV} is not set",
                    f"az login, or set {PAT_ENV}",
                )
    if ctx.offline:
        yield Finding(
            "hosting_skipped",
            "machine",
            "info",
            f"--offline: logins to {provider} and the harnesses were not checked",
            "run factory check without --offline",
        )


def _present(paths: list[Path]) -> list[str]:
    """The files, and non-empty directories, of ``paths`` that exist."""
    found = []
    for path in paths:
        try:
            if path.is_file() or (path.is_dir() and any(path.iterdir())):
                found.append(str(path))
        except OSError:
            continue
    return found


def isolation(ctx: CheckContext) -> Iterator[Finding]:
    """Global files of the operator a harness loads and has no switch to leave out."""
    if ctx.roster is None:
        return
    home = ctx.machine.home()
    for name, agents in harnesses_in_config(ctx.roster).items():
        if name == "codex" and not flag_value(ctx.machine.env("CODEX_SAFE_MODE")):
            codex_home = Path(ctx.machine.env("CODEX_HOME") or home / ".codex")
            found = _present(
                [
                    codex_home / "AGENTS.md",
                    codex_home / "AGENTS.override.md",
                    codex_home / "skills",
                    home / ".agents" / "skills",
                ]
            )
            if found:
                yield Finding(
                    "codex_not_isolated",
                    "machine",
                    "warning",
                    f"codex loads the operator's global {', '.join(found)} into every run "
                    f"(agents: {', '.join(agents)}); it has no switch to leave them out",
                    "move them out of the way, or set CODEX_SAFE_MODE=1 for full isolation",
                )
        elif name == "pi" and not flag_value(ctx.machine.env("PI_SAFE_MODE")):
            agent_dir = Path(ctx.machine.env("PI_CODING_AGENT_DIR") or home / ".pi" / "agent")
            found = _present(
                [
                    agent_dir / "AGENTS.md",
                    agent_dir / "AGENTS.override.md",
                    agent_dir / "CLAUDE.md",
                    agent_dir / "APPEND_SYSTEM.md",
                ]
            )
            if found:
                yield Finding(
                    "pi_not_isolated",
                    "machine",
                    "warning",
                    f"pi loads the operator's global {', '.join(found)} into every run "
                    f"(agents: {', '.join(agents)}); it cannot leave them out without "
                    "dropping the repo's AGENTS.md and CLAUDE.md too",
                    "move them out of the way, or set PI_SAFE_MODE=1 for full isolation",
                )


def environment(ctx: CheckContext) -> Iterator[Finding]:
    path = env_file(ctx.environ)
    mode = ctx.machine.file_mode(path)
    if mode is not None and mode != 0o600 and ctx.machine.platform() != "win32":
        yield Finding(
            "env_file_mode",
            "machine",
            "warning",
            f"{path} has mode {mode:04o}; it holds secrets and should be readable only by you",
            f"chmod 600 {path}",
        )
    for name in OVERRIDES:
        value = (ctx.machine.env(name) or "").strip()
        if not value:
            continue
        yield Finding(
            "env_override",
            "machine",
            "info",
            f"{name}={value} is set on this machine; it changes how every run of this "
            "harness behaves",
            "unset it unless you want it (in the shell or $HAIFA_HOME/env)",
        )


MACHINE_GROUP = RuleGroup(
    "machine",
    (
        Rule("platform", platform, needs_install=False, needs_repo=False),
        Rule("tools", tools, needs_install=False, needs_repo=False),
        Rule("harnesses", harnesses, needs_install=False, needs_repo=False),
        Rule("node", node),
        Rule("just", just, needs_install=False),
        Rule("test program", test_program),
        Rule("local", local),
        Rule("logins", logins, needs_install=False, needs_repo=False),
        Rule("hosting", hosting),
        Rule("environment", environment, needs_install=False, needs_repo=False),
        Rule("harness isolation", isolation),
    ),
    scope="machine",
)
