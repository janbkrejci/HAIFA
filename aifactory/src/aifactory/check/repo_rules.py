"""The ``repo`` rule group: problems fixed in the repository and committed to base.

Every rule reads only. Each finding is built as ``Finding("<code>", ...)`` with a
literal code, which ``tests/test_skill.py`` matches against ``ISSUE_CODES["check"]``.
"""

from __future__ import annotations

import fnmatch
import tempfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

import yaml

from aifactory import yamlload
from aifactory.backlog import Task, effective_workflow, iter_tasks
from aifactory.check.context import CheckContext
from aifactory.check.model import Finding, Rule, RuleGroup
from aifactory.config.errors import ConfigError
from aifactory.config.loader import write_prompts
from aifactory.config.settings import load_local
from aifactory.config.source import LOCAL_FILE, git_try
from aifactory.config.status import change_warnings
from aifactory.harness import unenforced_disallowed
from aifactory.harness.override import THINKING_LEVELS
from aifactory.harness.repo_skills import MIRROR, SOURCE, commit_snapshot, diff_snapshots
from aifactory.run.errors import TaskRunError
from aifactory.run.task import FACTORY_DATA_DIR, named_workflow
from aifactory.workflow import Issue, RoleStep, Workflow, WorkflowError, preflight, walk

DEFAULT_TRACE_DB = ".factory/trace.db"
_LIST_MAX = 5


def _ids(ids: list[str]) -> str:
    shown = ", ".join(ids[:_LIST_MAX])
    more = len(ids) - _LIST_MAX
    return f"{shown} (+{more} more)" if more > 0 else shown


# -- install --

UNSUPPORTED_FIX = "HAIFA will not convert it; install factory with factory init"


def install(ctx: CheckContext) -> Iterator[Finding]:
    """One finding per repo state (AR30), with the action that state calls for."""
    state = ctx.state
    if state.state == "none":
        yield Finding(
            "factory_missing",
            "repo",
            "error",
            f"{ctx.main} has no .factory/config.yaml, neither in {ctx.base} nor in the "
            "working tree",
            "install factory into the repository and commit .factory/ to base",
            "init",
        )
    elif state.state == "uncommitted" and ctx.commit is not None:
        yield Finding(
            "config_not_committed",
            "repo",
            "error",
            f".factory/ exists only in the working tree; runs read it from {ctx.base} "
            f"({ctx.commit[:7]}) and do not see it",
            f"commit .factory/ (without local.yaml) to {ctx.base}",
            "config_commit",
        )
    elif state.state == "unsupported":
        yield Finding(
            "repo_unsupported",
            "repo",
            "error",
            f"{ctx.base} has an sssf installation in adws/ and no .factory/config.yaml; "
            "HAIFA does not run or convert sssf",
            UNSUPPORTED_FIX,
        )
    elif state.state == "installed":
        cfg = ctx.base_config
        origin = "the seed" if cfg is None or cfg.library is None else f"library {cfg.library[:7]}"
        yield Finding(
            "repo_installed",
            "repo",
            "info",
            f"factory is installed in {ctx.base}; agents and workflows the repo lacks come "
            f"from {origin}",
        )


# -- base and checkout --


def base(ctx: CheckContext) -> Iterator[Finding]:
    if ctx.commit is None:
        yield Finding(
            "base_missing",
            "repo",
            "error",
            f"base '{ctx.base}' does not resolve to a commit in {ctx.main}",
            f"create the branch '{ctx.base}' with a first commit, or set 'base' in "
            ".factory/config.yaml",
        )


def checkout(ctx: CheckContext) -> Iterator[Finding]:
    head = git_try(ctx.main, "symbolic-ref", "-q", "HEAD")
    branch = head.strip() if head else None
    if branch == f"refs/heads/{ctx.base}":
        return
    where = f"on '{branch.removeprefix('refs/heads/')}'" if branch else "detached"
    yield Finding(
        "checkout_not_on_base",
        "repo",
        "warning",
        f"the main checkout {ctx.main} is {where}, not on base '{ctx.base}'",
        f"git switch {ctx.base} in {ctx.main} (backlog commits and the dashboard expect it)",
    )


def remote(ctx: CheckContext) -> Iterator[Finding]:
    settings = ctx.settings
    name = settings.remote
    if name not in ctx.remotes:
        if settings.git_provider != "local":
            yield Finding(
                "remote_missing",
                "repo",
                "warning",
                f"git_provider is '{settings.git_provider}' but the remote '{name}' does not exist",
                f"git remote add {name} URL, or set 'remote' in .factory/config.yaml",
            )
        return
    if ctx.commit is None:
        return
    ref = f"refs/remotes/{name}/{ctx.base}"
    if ctx.remote_ref is None:
        yield Finding(
            "remote_base_missing",
            "repo",
            "info",
            f"{ref} does not exist locally; ahead/behind were not compared",
            f"git fetch {name}",
        )
        return
    counts = ctx.ahead_behind
    if counts is None:
        return
    ahead, behind = counts
    if behind:
        yield Finding(
            "base_behind_remote",
            "repo",
            "warning",
            f"{ctx.base} is {behind} commit(s) behind {ref} (as of the last fetch)",
            f"git pull {name} {ctx.base}",
            "config_pull",
        )
    if ahead:
        yield Finding(
            "base_ahead_of_remote",
            "repo",
            "warning",
            f"{ctx.base} is {ahead} commit(s) ahead of {ref} (as of the last fetch)",
            f"git push {name} {ctx.base}",
        )


# -- configuration --


def config(ctx: CheckContext) -> Iterator[Finding]:
    changes = ctx.changes if ctx.committed else ()
    commit_fixes = ctx.worktree_config is not None and bool(changes)
    for issue in ctx.base_issues:
        yield Finding(
            "base_config_invalid",
            "repo",
            "error",
            f"{issue.path}: {issue.message}",
            f"fix .factory/ and commit it to {ctx.base}",
            "config_commit" if commit_fixes else None,
        )
    if ctx.state.state == "uncommitted" or changes:
        for issue in ctx.worktree_issues:
            yield Finding(
                "worktree_config_invalid",
                "repo",
                "warning",
                f"{issue.path}: {issue.message}",
                "fix .factory/ in the working tree before committing it",
            )
    if ctx.commit is not None:
        for warning in change_warnings(list(changes), ctx.base, ctx.commit):
            yield Finding(
                "config_uncommitted",
                "repo",
                "warning",
                warning,
                f"commit the change to {ctx.base}, or discard it",
                "config_commit",
            )
    cfg = ctx.base_config
    if cfg is not None and cfg.settings.base != ctx.base:
        yield Finding(
            "base_setting_mismatch",
            "repo",
            "warning",
            f"config.yaml in {ctx.base} says base '{cfg.settings.base}', but the working "
            f"tree says '{ctx.base}'",
            "make 'base' in .factory/config.yaml the same in the working tree and in base",
        )


def disallowed_commands(ctx: CheckContext) -> Iterator[Finding]:
    """An agent forbids commands on a harness that cannot forbid them."""
    if ctx.roster is None:
        return
    for agent in ctx.roster.agents:
        problem = unenforced_disallowed(agent)
        if problem is None:
            continue
        yield Finding(
            "disallowed_commands_unenforced",
            "repo",
            "warning",
            problem,
            "run the agent on the claude harness, or drop its disallowed_commands "
            "in .factory/agents.yaml",
        )


# -- backlog and workflows --


def backlog(ctx: CheckContext) -> Iterator[Finding]:
    issues = ctx.backlog_issues
    missing = [i for i in issues if i.code == "missing_backlog_dir"]
    if missing:
        assert ctx.base_backlog is not None
        yield Finding(
            "backlog_missing",
            "repo",
            "warning",
            f"{'; '.join(i.message for i in missing)} in {ctx.base}",
            "create the backlog and commit it (factory backlog commit)",
        )
    by_code: dict[str, list[str]] = {}
    examples: dict[str, str] = {}
    for issue in issues:
        if issue.code == "missing_backlog_dir":
            continue
        by_code.setdefault(issue.code, []).append(issue.path)
        examples.setdefault(issue.code, f"{issue.path}: {issue.message}")
    for code, paths in by_code.items():
        yield Finding(
            "backlog_invalid",
            "repo",
            "error",
            f"{len(paths)}× {code} in {ctx.base}, e.g. {examples[code]}",
            "run factory backlog check, fix the files, then factory backlog commit",
        )


def _todo(ctx: CheckContext) -> list[Task]:
    if ctx.base_backlog is None:
        return []
    return [t for t in iter_tasks(ctx.base_backlog) if t.status == "todo"]


def workflows(ctx: CheckContext) -> Iterator[Finding]:
    cfg = ctx.base_config
    if cfg is None or ctx.base_backlog is None:
        return
    unset: list[str] = []
    used: dict[str, list[str]] = {}
    for task in _todo(ctx):
        name = effective_workflow(task)
        if isinstance(name, str) and name.strip():
            used.setdefault(name.strip(), []).append(task.id)
        else:
            unset.append(task.id)
    if unset:
        yield Finding(
            "workflow_unset",
            "repo",
            "warning",
            f"{len(unset)} todo task(s) have no workflow: {_ids(unset)}",
            "set 'workflow' on the tasks or in a project/step index.md",
        )
    for name, ids in used.items():
        try:
            workflow = named_workflow(name, cfg, ids[0])
        except TaskRunError as exc:
            if exc.code == "unknown_workflow":
                yield Finding(
                    "workflow_unknown",
                    "repo",
                    "error",
                    f"workflow '{name}' (tasks {_ids(ids)}) is neither in .factory/workflows/ "
                    f"in {ctx.base} nor in the library",
                    f"add .factory/workflows/{name}.yaml or put it in the library, or change "
                    "the tasks",
                )
            else:
                yield Finding(
                    "workflow_invalid",
                    "repo",
                    "error",
                    f"{exc} (tasks {_ids(ids)})",
                    "fix the workflow (factory workflow check) and commit it",
                )
            continue
        with tempfile.TemporaryDirectory(prefix="factory-check-") as tmp:
            roster = write_prompts(cfg, Path(tmp))
            try:
                if ctx.offline:
                    # resolving models asks pi --list-models; offline checks the roster only
                    _roster_only(workflow, {agent.name for agent in roster.agents})
                else:
                    preflight(workflow, roster)
            except WorkflowError as exc:
                yield Finding(
                    "workflow_invalid",
                    "repo",
                    "error",
                    f"workflow {name} (tasks {_ids(ids)}): {exc}",
                    "fix the workflow or .factory/agents.yaml and commit it",
                )


def _roster_only(workflow: Workflow, names: set[str]) -> None:
    """Every agent of the workflow is in the roster (no model is resolved)."""
    issues = [
        Issue(
            "unknown_agent",
            f"step {step.name!r} needs agent {step.role.agent!r}, which is not in the roster",
            step.path,
        )
        for step in walk(workflow.steps)
        if isinstance(step, RoleStep) and step.role.agent not in names
    ]
    if issues:
        raise WorkflowError(issues)


# -- .gitignore --


def _covers(line: str, sample: str) -> bool:
    if line.endswith("/") and sample.startswith(line):
        return True
    if fnmatch.fnmatchcase(sample, line) or sample.startswith(line.rstrip("/") + "/"):
        return True
    if "/" not in line.rstrip("/"):
        parts = PurePosixPath(sample).parts
        dirs = parts[:-1] if line.endswith("/") else parts
        name = line.rstrip("/")
        return any(fnmatch.fnmatchcase(part, name) for part in dirs)
    return False


def _gitignore_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "!")):
            continue
        lines.append(line.removeprefix("/"))
    return lines


def runtime_entries(ctx: CheckContext) -> list[tuple[str, tuple[str, ...]]]:
    """(entry to add, sample paths it must ignore) of the factory runtime."""
    try:
        trace_db = load_local(ctx.main).trace_db
    except ConfigError:
        trace_db = DEFAULT_TRACE_DB
    entries: list[tuple[str, tuple[str, ...]]] = [(LOCAL_FILE, (LOCAL_FILE,))]
    trace = PurePosixPath(trace_db)
    if not trace.is_absolute() and ".." not in trace.parts and not trace_db.startswith("~"):
        rel = trace.as_posix()
        entries.append((f"{rel}*", (rel, f"{rel}-wal")))
    worktrees = ctx.settings.worktrees_dir.strip("/").removeprefix("./")
    entries.append((f"{worktrees}/", (f"{worktrees}/x",)))
    entries.append((f"{FACTORY_DATA_DIR}/", (f"{FACTORY_DATA_DIR}/x",)))
    return entries


def gitignore(ctx: CheckContext) -> Iterator[Finding]:
    if ctx.commit is None:
        return
    text = ctx.base_file(".gitignore") or ""
    lines = _gitignore_lines(text)
    for entry, samples in runtime_entries(ctx):
        if all(any(_covers(line, s) for line in lines) for s in samples):
            continue
        yield Finding(
            "gitignore_missing",
            "repo",
            "warning",
            f".gitignore in {ctx.base} does not ignore {entry} (factory runtime)",
            f"add '{entry}' to .gitignore and commit it",
        )


def skills_mirror(ctx: CheckContext) -> Iterator[Finding]:
    """.agents/skills must be an exact copy of .claude/skills in the base commit."""
    if ctx.commit is None:
        return
    diff = diff_snapshots(
        commit_snapshot(ctx.main, ctx.commit, SOURCE),
        commit_snapshot(ctx.main, ctx.commit, MIRROR),
    )
    fix = f"run factory skills sync and commit {MIRROR}"
    for name in diff.missing:
        yield Finding(
            "skill_mirror_missing",
            "repo",
            "warning",
            f"skill '{name}' is in {SOURCE} but not in {MIRROR} of {ctx.base}; "
            "codex and pi do not see it",
            fix,
        )
    for name in diff.changed:
        yield Finding(
            "skill_mirror_differs",
            "repo",
            "warning",
            f"skill '{name}' in {MIRROR} of {ctx.base} differs from {SOURCE}; "
            "codex and pi read a stale copy",
            fix,
        )
    for name in diff.extra:
        yield Finding(
            "skill_mirror_extra",
            "repo",
            "warning",
            f"skill '{name}' is in {MIRROR} of {ctx.base} but no longer in {SOURCE}; "
            "codex and pi still see it",
            fix,
        )


# -- roles and thinking --


def roles(ctx: CheckContext) -> Iterator[Finding]:
    text = ctx.base_file(".factory/roles.yaml")
    if text is None:
        return
    try:
        raw = yamlload.safe_load(text)
    except yaml.YAMLError:
        return
    if isinstance(raw, dict) and "code_steps" in raw:
        yield Finding(
            "roles_full_copy",
            "repo",
            "info",
            f".factory/roles.yaml in {ctx.base} is a full copy of the role registry "
            "(code_steps); it hides every later change of the packaged roles",
            "keep only the roles you change (no code_steps) so the file overlays the "
            "packaged registry",
        )


def thinking(ctx: CheckContext) -> Iterator[Finding]:
    if ctx.roster is None:
        return
    for agent in ctx.roster.agents:
        if agent.thinking in THINKING_LEVELS:
            continue
        yield Finding(
            "unknown_thinking",
            "repo",
            "warning",
            f"agent {agent.name}: thinking {agent.thinking!r} is not a known level",
            f"set thinking to one of {'|'.join(THINKING_LEVELS)} in .factory/agents.yaml",
        )


REPO_GROUP = RuleGroup(
    "repo",
    (
        Rule("install", install, needs_install=False),
        Rule("base", base),
        Rule("checkout", checkout),
        Rule("remote", remote),
        Rule("config", config),
        Rule("disallowed commands", disallowed_commands),
        Rule("backlog", backlog),
        Rule("workflows", workflows),
        Rule("gitignore", gitignore),
        Rule("skills mirror", skills_mirror),
        Rule("roles", roles),
        Rule("thinking", thinking),
    ),
    scope="repo",
)
