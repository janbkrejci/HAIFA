"""The ``repo`` rule group: problems fixed in the repository and committed to base.

Every rule reads only. Each finding is built as ``Finding("<code>", ...)`` with a
literal code, which ``tests/test_skill.py`` matches against ``ISSUE_CODES["check"]``.
"""

from __future__ import annotations

import fnmatch
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

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

JUSTFILES = ("justfile", "Justfile", ".justfile")
DEFAULT_TRACE_DB = ".factory/trace.db"
_RECIPE = re.compile(r"^@?(?P<name>[A-Za-z_][A-Za-z0-9_-]*)\b[^:]*:(?!=)")
_ALIAS = re.compile(r"^alias\s+(?P<name>[A-Za-z_][\w-]*)\s*:=")
_IMPORT = re.compile(r"^(import|mod)\b")
_LIST_MAX = 5


def _ids(ids: list[str]) -> str:
    shown = ", ".join(ids[:_LIST_MAX])
    more = len(ids) - _LIST_MAX
    return f"{shown} (+{more} more)" if more > 0 else shown


# -- install --


def install(ctx: CheckContext) -> Iterator[Finding]:
    """One finding per onboarding state (AR30), with the action that state calls for."""
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
    elif state.state == "working_tree" and ctx.commit is not None:
        yield Finding(
            "config_not_committed",
            "repo",
            "error",
            f".factory/ exists only in the working tree; runs read it from {ctx.base} "
            f"({ctx.commit[:7]}) and do not see it",
            f"commit .factory/ (without local.yaml) to {ctx.base}",
            "config_commit",
        )
    elif state.state == "sssf":
        yield Finding(
            "sssf_not_onboarded",
            "repo",
            "error",
            f"{ctx.base} has an sssf roster ({', '.join(state.rosters)}) and no .factory/; "
            "factory does not run sssf configuration",
            "extract it once with factory onboard (on the engineer's machine)",
            "onboard",
        )
    elif state.state == "pre_library":
        yield Finding(
            "pre_library_config",
            "repo",
            "info",
            f".factory/ in {ctx.base} has no manifest.yaml; it runs, but its items are not "
            "linked to the library",
            "extract it once with factory onboard (on the engineer's machine)",
            "onboard",
        )
    elif state.state == "onboarded":
        yield Finding(
            "repo_onboarded",
            "repo",
            "info" if state.manifest_error is None else "error",
            _onboarded_message(ctx),
            "never onboard it again; on another machine run factory adopt to fill the "
            "library from the committed configuration",
            "adopt",
        )
    if state.sssf_leftover:
        yield Finding(
            "sssf_leftover",
            "repo",
            "info",
            f"adws/ is still committed next to .factory/ in {ctx.base}; runs ignore it",
            "delete adws/ in a separate commit once nobody runs sssf in this repo",
        )
    if state.alternate_rosters:
        yield Finding(
            "alternate_rosters",
            "repo",
            "info",
            f"{ctx.base} has {len(state.rosters)} sssf rosters: {', '.join(state.rosters)}",
            "choose the roster to extract when you run factory onboard",
        )


def _onboarded_message(ctx: CheckContext) -> str:
    state = ctx.state
    if state.manifest_error is not None:
        return f"the manifest in {ctx.base} cannot be read: {state.manifest_error}"
    block = state.onboarding
    library = state.library
    if block is None:
        what = f"{ctx.base} has .factory/manifest.yaml without an onboarding block"
    else:
        who = f" by {block['by']}" if block.get("by") else ""
        what = (
            f"onboarded from {block['source']} at {block['at']}{who} (factory {block['factory']})"
        )
    if library is not None:
        what += f", library {library['name']} ({library['id']})"
    return what


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
    if ctx.state.state == "working_tree" or changes:
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
            if exc.code == "unknown_workflow" and cfg.manifest is not None:
                yield Finding(
                    "workflow_not_in_repo",
                    "repo",
                    "error",
                    f"backlog in {ctx.base} names workflow '{name}' (tasks {_ids(ids)}), which "
                    "this repo with a manifest does not have in .factory/workflows/",
                    f"factory config add workflow {name}, or change the tasks",
                )
            elif exc.code == "unknown_workflow":
                yield Finding(
                    "workflow_unknown",
                    "repo",
                    "error",
                    f"workflow '{name}' (tasks {_ids(ids)}) is neither in .factory/workflows/ "
                    f"in {ctx.base} nor packaged",
                    f"add .factory/workflows/{name}.yaml and commit it, or change the tasks",
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


# -- test command --


def justfile_recipes(text: str) -> set[str]:
    """Names of the recipes (and aliases) a justfile defines."""
    names: set[str] = set()
    for line in text.splitlines():
        if not line or line[0] in " \t#[":
            continue
        alias = _ALIAS.match(line)
        if alias:
            names.add(alias.group("name"))
            continue
        if line.startswith(("set ", "export ", "import ", "mod ")):
            continue
        recipe = _RECIPE.match(line)
        if recipe:
            names.add(recipe.group("name"))
    return names


def test_rule(ctx: CheckContext) -> Iterator[Finding]:
    if ctx.commit is None:
        return
    argv = ctx.test_argv
    program = argv[0]
    shown = " ".join(argv)
    if program == "just":
        found: tuple[str, str] | None = None
        for candidate in JUSTFILES:
            content = ctx.base_file(candidate)
            if content is not None:
                found = (candidate, content)
                break
        if found is None:
            yield Finding(
                "justfile_missing",
                "repo",
                "error",
                f"the test command '{shown}' needs a justfile, but {ctx.base} has none",
                "add a justfile with a 'test' recipe and commit it, or set test_command",
            )
            return
        name, text = found
        recipes = justfile_recipes(text)
        wanted = next((a for a in argv[1:] if not a.startswith("-")), None)
        if (wanted is None and recipes) or wanted in recipes:
            return
        imports = any(_IMPORT.match(line) for line in text.splitlines())
        what = f"recipe '{wanted}'" if wanted else "any recipe"
        yield Finding(
            "test_recipe_missing",
            "repo",
            "warning" if imports else "error",
            f"the test command '{shown}' needs {what}, but {name} in {ctx.base} has none"
            + (" (it imports other files, which were not read)" if imports else ""),
            f"add the recipe to {name} and commit it, or set test_command",
        )
    elif "/" in program and not PurePosixPath(program).is_absolute():
        rel = program.removeprefix("./")
        if not ctx.base_has(rel):
            yield Finding(
                "test_script_missing",
                "repo",
                "error",
                f"the test command '{shown}' runs {program}, which is not in {ctx.base}",
                "commit the script, or fix test_command",
            )


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
            "update",
        )


def update(ctx: CheckContext) -> Iterator[Finding]:
    """Items of an onboarded repo that ``factory update`` can bring, and its migrations.

    Reads only: base is unpacked into a temporary directory, the library heads are read
    without fetching and without the history cache.
    """
    from aifactory.config.manifest import read_manifest
    from aifactory.library import migrations
    from aifactory.library.model import ITEM_TYPES
    from aifactory.library.state import extract_factory, library_side, repo_version

    state = ctx.state
    if state.state != "onboarded" or state.manifest_error is not None or ctx.commit is None:
        return
    with tempfile.TemporaryDirectory(prefix="factory-check-update-") as tmp:
        copy = Path(tmp)
        try:
            extract_factory(ctx.main, ctx.commit, copy)
            manifest = read_manifest(copy)
        except Exception:  # noqa: BLE001 - the config rules report a broken base
            return
        if manifest is None:
            return
        side = library_side()
        entries = [
            (kind, name, entry)
            for kind in ITEM_TYPES
            for name, entry in sorted(manifest.items.of(kind).items())
        ]
        try:
            heads = side.heads({(kind, e.item) for kind, _, e in entries})
        except Exception:  # noqa: BLE001 - an unreadable library is not this rule's problem
            return
        names: list[str] = []
        for kind, name, entry in entries:
            r = repo_version(copy, kind, name)
            lib = heads.get((kind, entry.item))
            if r is None or (lib is not None and lib != entry.version and r != lib):
                names.append(f"{kind}/{name}")
        config = copy / ".factory" / "config.yaml"
        files = {".factory/config.yaml": config.read_bytes()} if config.is_file() else {}
        found = [m.id for m in migrations.detected(files)]
    if not names and not found:
        return
    origin = "the seed" if side.root is None else "the library"
    parts = []
    if names:
        parts.append(f"{len(names)} item(s) can be updated from {origin}: {_ids(names)}")
    if found:
        parts.append(f"migrations: {', '.join(found)}")
    yield Finding(
        "update_available",
        "repo",
        "info",
        "; ".join(parts),
        "review factory update --dry-run, then factory update --commit",
        "update",
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


# -- items, roles and thinking --


def _item_message(row: dict[str, Any]) -> str:
    short = row.get("short") or {}
    return (
        f"{row['type']} {row['name']} is {row['state']} (repo {short.get('repo') or '-'}, "
        f"manifest {short.get('manifest') or '-'}, library {short.get('library') or '-'})"
    )


def items(ctx: CheckContext) -> Iterator[Finding]:
    """One finding per item of base that is not ``synced`` with the library (AR23)."""
    for row in ctx.items:
        state = row["state"]
        what = f"{row['type']} {row['name']}"
        message = _item_message(row)
        if state == "local":
            yield Finding(
                "item_local",
                "repo",
                "info",
                message,
                f"export {what} to the library (factory config export)",
                "export",
            )
        elif state == "missing":
            yield Finding(
                "item_missing",
                "repo",
                "warning",
                message,
                f"restore the files of {what} from the library (factory config update)",
                "update",
            )
        elif state == "unknown":
            yield Finding(
                "item_unknown",
                "repo",
                "warning",
                message,
                f"the library does not know the version of {what}; fill it with factory adopt",
                "adopt",
            )
        elif state == "outdated":
            yield Finding(
                "item_outdated",
                "repo",
                "info",
                message,
                f"take the library version of {what} (factory config update)",
                "update",
            )
        elif state == "modified":
            yield Finding(
                "item_modified",
                "repo",
                "info",
                message,
                f"export the change of {what} to the library (factory config export)",
                "export",
            )
        elif state == "diverged":
            yield Finding(
                "item_diverged",
                "repo",
                "warning",
                message,
                f"{what} changed both in the repo and in the library; merge them "
                "(factory config update)",
                "update",
            )


def roles(ctx: CheckContext) -> Iterator[Finding]:
    text = ctx.base_file(".factory/roles.yaml")
    if text is None:
        return
    try:
        raw = yaml.safe_load(text)
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
        Rule("test", test_rule),
        Rule("gitignore", gitignore),
        Rule("update", update),
        Rule("skills mirror", skills_mirror),
        Rule("items", items),
        Rule("roles", roles),
        Rule("thinking", thinking),
    ),
    scope="repo",
)
