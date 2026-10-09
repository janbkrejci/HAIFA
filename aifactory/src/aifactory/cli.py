"""The `factory` command line.

Implemented: `check`, `harness check`, `config status`, `config show`,
`config commit`, `config pull`, `config items`, `backlog check`,
`backlog list`, `backlog sync`, `backlog auto-continue`, `backlog auto-merge`, `backlog add`,
`backlog edit`, `task add`,
`task edit`, `task link`, `task show`, `task list`, `task run`, `task approve`, `task return`,
`task resolve`, `task publish`, `task clean`, `init`, `onboard`, `adopt`, `workflow check`,
`skills sync`, `library init`, `library list`, `library show`, `library import`,
`library clone`, `library status`, `library pull`, `library push`, `library seed`, `upgrade`,
`obs` (the local dashboard of every registered repository, ``aifactory.web``), and
`factory --skill` (the agent skill generated from this code, see ``aifactory.skill``).

With `--json` every command prints one envelope ``{ok, data, error, warnings}`` with a stable
``error.code`` (``aifactory.skill.envelope``, codes in ``aifactory.skill.codes``).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import traceback
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

from aifactory import __version__, oscompat
from aifactory.home import load_env_file
from aifactory.skill.envelope import envelope_fail, envelope_ok, strip_payload

if TYPE_CHECKING:
    from aifactory.backlog import Backlog, ContainerWriteResult
    from aifactory.config.commit import ConfigCommitError
    from aifactory.engine.role_registry import RoleRegistry
    from aifactory.harness.config import SSSFConfig
    from aifactory.run import ChainResult, TaskRunResult
    from aifactory.workflow import CodeRunner

SUBCOMMANDS: tuple[tuple[str, str], ...] = (
    ("check", "check that factory will run in this repo and on this machine"),
    ("init", "install factory into this repository from the library (or the seed)"),
    (
        "onboard",
        "extract this repo's own factory configuration once into the library and a committed "
        ".factory/ with a manifest",
    ),
    (
        "adopt",
        "take over an onboarded repo on this machine: fill the library, never write the repo",
    ),
    (
        "update",
        "update the repo's items from the library (or the seed) file by file; repo changes "
        "stay without --take or --merge",
    ),
    ("task", "run and inspect backlog tasks"),
    ("backlog", "load and validate the backlog"),
    ("workflow", "validate and inspect workflows"),
    ("config", "show and validate factory configuration"),
    ("harness", "inspect the coding-agent harnesses"),
    ("skills", "keep the repo's skills mirror for codex and pi in sync"),
    (
        "library",
        "the HAIFA library in the home directory: init, list, show, import, clone, status, "
        "pull, push, seed",
    ),
    ("upgrade", "install a newer HAIFA from a haifa-<version>.zip bundle"),
    ("obs", "serve the local dashboard (127.0.0.1 unless --host) and open it"),
)


class _UsageError(Exception):
    """argparse rejected the arguments; raised instead of exiting so --json can report it."""

    def __init__(self, parser: argparse.ArgumentParser, message: str) -> None:
        super().__init__(message)
        self.parser = parser
        self.message = message


class _Parser(argparse.ArgumentParser):
    """An ArgumentParser whose usage errors raise ``_UsageError`` (subparsers inherit it)."""

    def error(self, message: str) -> NoReturn:
        raise _UsageError(self, message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="factory",
        description="HAIFA (Helios AI Factory): run backlog tasks through coding-agent workflows.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--skill",
        action="store_true",
        help="print the agent skill for this version and exit (with --json: as an envelope)",
    )
    parser.add_argument(
        "--json",
        dest="root_json",
        action="store_true",
        help="with --skill: print the skill as a JSON envelope",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for name, help_text in SUBCOMMANDS:
        child = sub.add_parser(name, help=help_text, description=help_text)
        if name == "check":
            _add_check_command(child)
        elif name == "init":
            _add_init_command(child)
        elif name == "onboard":
            _add_onboard_command(child)
        elif name == "adopt":
            _add_adopt_command(child)
        elif name == "update":
            _add_update_command(child)
        elif name == "harness":
            _add_harness_commands(child)
        elif name == "skills":
            _add_skills_commands(child)
        elif name == "library":
            _add_library_commands(child)
        elif name == "config":
            _add_config_commands(child)
        elif name == "backlog":
            _add_backlog_commands(child)
        elif name == "task":
            _add_task_commands(child)
        elif name == "workflow":
            _add_workflow_commands(child)
        elif name == "upgrade":
            _add_upgrade_command(child)
        elif name == "obs":
            _add_obs_command(child)
    return parser


def _add_check_command(parser: argparse.ArgumentParser) -> None:
    parser.description = (
        "Check, only by reading, whether factory will run in this repository and on this "
        "machine, and what to fix. Reports the onboarding state of the repo read from base "
        "(onboarded, pre_library, sssf, working_tree or none) with its action (adopt, "
        "onboard, config_commit or init), the flags sssf_leftover and alternate_rosters, the "
        "onboarding block of the manifest, and findings {code, scope, severity, message, "
        "fix, action}: scope 'repo' is fixed and committed to base, 'machine' is fixed "
        "locally, 'library' is fixed in the library in $HAIFA_HOME; severity is error, "
        "warning or info; action names the fix (init, update, export, config_commit, "
        "config_pull, onboard, adopt) or is null. Items of base that are not synced with "
        "the library get item_* findings. "
        "Outside a git repository (without --repo) only the machine and the library are "
        "checked (in_repo false). "
        "Ahead/behind compare base and the library with local remote-tracking refs (no "
        "fetch). Exits 0 without errors, 1 with an error (checks_failed), 2 when --repo is "
        "not a git repository."
    )
    parser.add_argument(
        "--repo", metavar="PATH", help="repository to check (default: the current git repo)"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "skip calls to the hosting and the harness logins (gh auth status, az account "
            "show, claude auth status, codex login status, pi auth check, pi --list-models)"
        ),
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")


def _check(args: argparse.Namespace) -> int:
    from aifactory import check

    start = Path(args.repo) if args.repo else Path.cwd()
    try:
        report = check.run_check(start, offline=args.offline, require_repo=args.repo is not None)
    except check.NotARepositoryError as exc:
        if args.json:
            return _emit_fail("not_a_repository", str(exc), exit_code=2, path=str(start))
        print(f"factory check: {exc}", file=sys.stderr)
        return 2
    errors = report.errors()
    if args.json:
        data = report.to_json()
        if report.ok:
            return _emit_ok(data)
        codes = ", ".join(dict.fromkeys(f.code for f in errors))
        return _emit_fail(
            "checks_failed", f"{len(errors)} error(s): {codes}", exit_code=1, data=data
        )
    if not report.in_repo:
        print("state:   outside a git repository (machine and library only)")
    else:
        where = (
            f"{report.base} @ {report.commit[:7]}" if report.commit else f"{report.base}, no commit"
        )
        print(f"state:   {report.state} ({where})  {report.repo}  next: {report.action}")
    if report.ahead is not None and report.behind is not None:
        print(f"remote:  {report.remote}  ahead {report.ahead}, behind {report.behind}")
    for finding in report.findings:
        print(f"{finding.severity:<7} {finding.scope:<7} {finding.code}: {finding.message}")
        if finding.fix or finding.action:
            action = f" [{finding.action}]" if finding.action else ""
            print(f"        fix: {finding.fix or ''}{action}")
    counts = report.counts()
    print(f"{counts['error']} error(s), {counts['warning']} warning(s), {counts['info']} info")
    return 0 if report.ok else 1


def _add_harness_commands(parser: argparse.ArgumentParser) -> None:
    parser.set_defaults(harness_parser=parser)
    sub = parser.add_subparsers(dest="harness_command", metavar="<subcommand>")
    check = sub.add_parser(
        "check",
        help="verify each harness CLI is on PATH and print its version",
        description="Verify each harness CLI used by the config is on PATH and print versions.",
    )
    check.add_argument("--json", action="store_true", help="print machine-readable JSON")
    check.add_argument(
        "--config",
        metavar="PATH",
        help="HAIFA roster (.factory/agents.yaml); only the harnesses it uses are checked",
    )


def _add_skills_commands(parser: argparse.ArgumentParser) -> None:
    parser.set_defaults(skills_parser=parser)
    sub = parser.add_subparsers(dest="skills_command", metavar="<subcommand>")
    sync = sub.add_parser(
        "sync",
        help="write .agents/skills as an exact copy of .claude/skills",
        description=(
            "Write .agents/skills/ as an exact copy of .claude/skills/ (new, changed and "
            "deleted skills), so codex and pi read the same skills as claude. Edit skills "
            "in .claude/skills/ only. Writes the working tree only; commit the result. "
            "No symlinks. Exits 0 on success, 2 when the folder is not a git repository "
            "or the mirror cannot be written (skills_sync_failed)."
        ),
    )
    sync.add_argument(
        "--repo", metavar="PATH", help="repository to sync (default: the current git repo)"
    )
    sync.add_argument("--json", action="store_true", help="print machine-readable JSON")


def _skills(args: argparse.Namespace) -> int:
    if args.skills_command is None:
        args.skills_parser.print_help()
        return 0
    from aifactory.config import ConfigError, repo_root
    from aifactory.harness import repo_skills

    label = "factory skills sync"
    try:
        root = repo_root(Path(args.repo) if args.repo else Path.cwd())
    except ConfigError as exc:
        return _fail_from_exception(exc, args.json, label)
    try:
        result = repo_skills.sync(root)
    except OSError as exc:
        if args.json:
            return _emit_fail("skills_sync_failed", str(exc), exit_code=2)
        print(f"{label}: {exc}", file=sys.stderr)
        return 2
    if args.json:
        return _emit_ok(
            {
                "repo": str(root),
                "source": repo_skills.SOURCE,
                "mirror": repo_skills.MIRROR,
                "added": list(result.added),
                "updated": list(result.updated),
                "removed": list(result.removed),
            }
        )
    for verb, names in (
        ("added", result.added),
        ("updated", result.updated),
        ("removed", result.removed),
    ):
        for name in names:
            print(f"{verb} {name}")
    if result.added or result.updated or result.removed:
        print(
            f"{repo_skills.MIRROR}: {len(result.added)} added, {len(result.updated)} updated, "
            f"{len(result.removed)} removed; commit {repo_skills.MIRROR}"
        )
    else:
        print(f"{repo_skills.MIRROR} is up to date")
    return 0


ITEM_TYPES: tuple[str, ...] = ("agent", "workflow", "skill", "extension")  # library.model


def _add_library_commands(parser: argparse.ArgumentParser) -> None:
    parser.set_defaults(library_parser=parser)
    sub = parser.add_subparsers(dest="library_command", metavar="<subcommand>")
    where = sub.add_parser(
        "where", help="show registered repos using an item, with slot, state and versions"
    )
    where.add_argument("type", choices=("agent", "workflow", "skill", "extension"))
    where.add_argument("name")
    where.add_argument("--json", action="store_true")
    init = sub.add_parser(
        "init",
        help="create the library from the seed in one commit",
        description=(
            "Create the library ($HAIFA_HOME/library, overridden by HAIFA_LIBRARY) as a git "
            "repository from the packaged seed in one commit: library.yaml (format, id, name, "
            "min_factory_version, seed) and the seed agents and workflows. An existing library "
            "is refused (library_exists); git needs user.name and user.email "
            "(git_identity_missing). With --remote URL the commit is pushed to the empty remote "
            "before the library exists locally; a remote with any ref is refused "
            "(remote_not_empty) and a failed push (push_failed) leaves no library. The remote "
            "is stored as origin without user and password."
        ),
    )
    init.add_argument("--name", metavar="N", help="name of the library (default: library)")
    init.add_argument("--remote", metavar="URL", help="share the library through this empty remote")
    list_ = sub.add_parser(
        "list",
        help="list the items of the library with their versions",
        description=(
            "List the items in HEAD of the library: type, name, version, short_version "
            "(8 characters), and commit, date and author of the last change."
        ),
    )
    list_.add_argument("--type", choices=ITEM_TYPES, help="list only items of this type")
    show = sub.add_parser(
        "show",
        help="show the files and version history of an item",
        description=(
            "Show an item in HEAD of the library (or at --version, a full version or a prefix "
            "of at least 4 hex digits): files {path, executable, size, content} and history "
            "{n, version, short_version, commit, date, author}, oldest first. unknown_item, "
            "unknown_version."
        ),
    )
    show.add_argument("type", metavar="TYP", choices=ITEM_TYPES, help="item type")
    show.add_argument("name", metavar="JMENO", help="item name")
    show.add_argument("--version", metavar="V", help="show this version of the item")
    import_ = sub.add_parser(
        "import",
        help="import a folder or file under the home directory into the library",
        description=(
            "Import a folder (agent, skill, extension) or file (workflow) from under the "
            "user's home directory (else outside_home, also for a symlink that leaves it) "
            "into the library. The item is validated (invalid_item with error.issues) and the "
            "plan {items, files with diffs, digest} is returned. Equal content is a no-op "
            "(committed false); other content under an existing name is a new version. "
            "Without --dry-run the write holds $HAIFA_HOME/library.lock, refuses a library "
            "with uncommitted changes (library_dirty), commits on HEAD without a checkout "
            "and fast-forwards the branch and working tree."
        ),
    )
    import_.add_argument("path", metavar="CESTA", help="folder or file to import")
    import_.add_argument("--type", required=True, choices=ITEM_TYPES, help="type of the item")
    import_.add_argument(
        "--name", metavar="N", help="item name (default: folder name or file stem)"
    )
    import_.add_argument("--dry-run", action="store_true", help="only print the plan")
    clone = sub.add_parser(
        "clone",
        help="clone a shared library from a git remote",
        description=(
            "Clone the library from URL into the library path and return its status. An "
            "existing library is refused (library_exists), a failed clone is clone_failed and "
            "a remote without a valid library.yaml (format, id, name) is invalid_library; "
            "nothing is left behind. The remote is stored as origin without user and password."
        ),
    )
    clone.add_argument("url", metavar="URL", help="git remote of the library")
    clone.add_argument("--branch", metavar="B", help="branch to clone (default: the remote HEAD)")
    status = sub.add_parser(
        "status",
        help="show the library's remote, branch, ahead/behind and uncommitted changes",
        description=(
            "Show path, id, name, remote (without credentials), branch, ahead and behind "
            "against origin (from the last fetched refs; --fetch fetches first), last_fetch, "
            "uncommitted changes and min_factory_version against the installed factory "
            "(compatible). Without a remote, ahead and behind are null."
        ),
    )
    status.add_argument("--fetch", action="store_true", help="fetch the remote first")
    pull = sub.add_parser(
        "pull",
        help="fast-forward the library to its remote",
        description=(
            "Fetch origin and fast-forward the library. A library with uncommitted changes "
            "(library_dirty) or diverged from the remote (library_diverged) is refused and "
            "nothing changes; without a remote it is no_remote."
        ),
    )
    push = sub.add_parser(
        "push",
        help="push local library commits to its remote, never forced",
        description=(
            "Fetch origin and push the local commits without force. A library behind the "
            "remote (library_behind: run factory library pull) or diverged from it "
            "(library_diverged) is refused; a rejected push is push_failed."
        ),
    )
    seed = sub.add_parser(
        "seed",
        help="take the new seed versions into the library after a HAIFA upgrade",
        description=(
            "Compare every item of the installed seed with HEAD of the library and the seed "
            "version recorded in library.yaml (seed). Missing in the library: create. Library "
            "head equal to the recorded version: update to the new seed version. Library head "
            "changed by the team: kept, the plan shows the diff (items[].diff); --take "
            "TYP/JMENO takes the seed version anyway (take). Then seed in library.yaml is set "
            "to the installed seed. Items the seed no longer has are not touched. The write "
            "goes like import: library.lock, library_dirty, fetch (library_behind, "
            "library_diverged), commit, push, fast-forward. A second run without a new seed "
            "commits nothing (committed false). A --take item the seed lacks is not_in_seed."
        ),
    )
    seed.add_argument(
        "--take",
        action="append",
        default=[],
        metavar="TYP/JMENO",
        help="take the seed version of this team-changed item (repeatable)",
    )
    seed.add_argument("--dry-run", action="store_true", help="only print the plan")
    for child in (init, list_, show, import_, clone, status, pull, push, seed):
        child.add_argument("--json", action="store_true", help="print machine-readable JSON")


def _add_init_command(parser: argparse.ArgumentParser) -> None:
    parser.description = (
        "Install factory into a git repository that has none: .factory/config.yaml, "
        ".factory/agents.yaml, .factory/prompts/<agent>/{system,user}.md, "
        ".factory/workflows/<name>.yaml and .factory/manifest.yaml (origin and version of "
        "every item), the backlog directory and the .gitignore lines. Items come from the "
        "library in the home directory, or from the seed in the package when there is no "
        "library. Workflows add the agents of their steps; --bind sets harness, model and "
        "thinking per agent. Three modes. Without --dry-run and --commit the files are "
        "written to the working tree, existing files are skipped unless --force and nothing "
        "is committed; test_command in .factory/config.yaml is suggested from the files in "
        "the repo root (justfile, pyproject.toml/pytest.ini, package.json, *.sln/*.csproj, "
        "Cargo.toml, go.mod, Makefile): the first candidate is written, the others are "
        "listed; --test-command overrides it, with no candidate the default just test stays "
        "and a warning is printed. --dry-run returns the plan: files with content, blockers, "
        "warnings, digest, the detected remote, base, provider and harness CLIs (detected) "
        "and the agents and workflows on offer (available); it writes nothing. --commit makes "
        "the same plan one commit on base (pushed before base moves; --pr opens a pull "
        "request from factory-init/<n> instead); --expect DIGEST refuses a plan that changed "
        "(plan_changed). Blockers: already_installed (run factory update), existing_config "
        "(run factory onboard), config_not_committed (run factory config commit), "
        "dirty_paths, invalid_plan, not_on_base, run_in_progress, base_behind, "
        "base_diverged. Nothing is written to the library."
    )
    parser.add_argument(
        "--repo", metavar="PATH", help="repository to install into (default: the current git repo)"
    )
    parser.add_argument(
        "--base",
        metavar="BRANCH",
        help="base branch of the runs (default: the remote HEAD with --dry-run/--commit, "
        "else the current branch)",
    )
    parser.add_argument(
        "--provider",
        choices=("local", "github", "azure"),
        default=None,
        help="git provider (default: from the remote URL with --dry-run/--commit, else local)",
    )
    parser.add_argument("--azure-org", metavar="ORG", help="Azure DevOps organization")
    parser.add_argument("--azure-project", metavar="PROJECT", help="Azure DevOps project")
    parser.add_argument("--azure-repo", metavar="REPO", help="Azure DevOps repository")
    parser.add_argument(
        "--agents",
        metavar="LIST",
        help="comma-separated agents (default: planner,builder,reviewer,documenter)",
    )
    parser.add_argument(
        "--bind",
        action="append",
        default=[],
        metavar="AGENT=HARNESS[:MODEL[:THINKING]]",
        help="bind an agent to a harness, model and thinking level (repeatable)",
    )
    parser.add_argument(
        "--workflows", metavar="LIST", help="comma-separated workflows (default: simple-sdlc)"
    )
    parser.add_argument(
        "--test-command",
        metavar="CMD",
        help="test_command for .factory/config.yaml (default: suggested from the repo root)",
    )
    parser.add_argument("--backlog-dir", metavar="DIR", help="backlog directory (default: backlog)")
    parser.add_argument(
        "--specs-dir", metavar="DIR", help="directory for specs, $specs_dir/ (default: specs)"
    )
    parser.add_argument(
        "--docs-dir", metavar="DIR", help="directory for docs, $docs_dir/ (default: app_docs)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="only return the plan; write nothing"
    )
    parser.add_argument(
        "--commit", action="store_true", help="commit the plan to base in one commit"
    )
    parser.add_argument(
        "--pr", action="store_true", help="with --commit: open a pull request instead"
    )
    parser.add_argument(
        "--expect", metavar="DIGEST", help="with --commit: refuse unless the plan has this digest"
    )
    parser.add_argument("-m", "--message", metavar="TEXT", help="with --commit: commit message")
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")


def _add_onboard_command(parser: argparse.ArgumentParser) -> None:
    parser.description = (
        "Extract the repo's own configuration once (decision 8): a .factory/ from before the "
        "library (state pre_library) or an sssf installation in adws/ (state sssf) goes into "
        "the library and into a committed .factory/ with .factory/manifest.yaml and its "
        "onboarding block (source pre_library or sssf). Without --commit it only returns the "
        "plan and changes nothing but remote-tracking refs. Procedure: --dry-run, show "
        "data.report (with detail), data.files, data.library_plan and data.digest to the "
        "user, then --commit --expect DIGEST. The remote check is the only network step (git "
        "fetch <remote> <base>, git ls-remote --heads <remote> factory-config/onboarding). "
        "pre_library: every agent and workflow of .factory/ is hashed: content the library "
        "has (a version in the history of the item of the same name, or the head of another "
        "item) is linked; other content becomes a new library item named after the slot when "
        "free, else <slot>-<slug of the repo folder>. --keep-local TYP/JMENO connects the slot "
        "to the library item of the same name and keeps the difference in the repo; --name "
        "TYP/JMENO=NOVE names the new item. Workflows the backlog in base names and the repo "
        "lacks are added from the library. Existing files of .factory/ stay byte for byte; "
        "the plan only adds the manifest, missing workflows and .gitignore lines. sssf (only "
        "adws/adw_sssf_config/sssf.config.yaml is converted, read from base): roster "
        "bindings (coding_agent -> harness, claude_code -> claude; model, tools, color, "
        "writes; thinking auto -> medium), prompts merged with the stock sssf text "
        "(git merge-file; a changed system.md is merged into the library's, user.md is the "
        "library's), pi extensions from harness_engineering (.ts with its relative imports), "
        "stock chains by blob id -> library workflows (simple-sdlc always, the others with "
        "--workflows), quality.py -> test_command and test_timeout (read with ast), "
        "defaults.protected_files -> protected_files; adws/ stays byte for byte. Report "
        "codes (data.report[].code): linked, converted, carried_over, changed_meaning, "
        "not_converted, manual, left_in_place. Blockers: already_onboarded, not_installed, "
        "config_not_committed, sssf_roster_invalid, source_not_committed, library_missing, "
        "library_dirty, library_behind, library_diverged, onboarded_in_remote, "
        "onboarding_pending, remote_unchecked, base_behind, base_diverged, not_on_base, "
        "run_in_progress, dirty_paths, invalid_plan. --commit recomputes the plan "
        "(plan_changed), writes and pushes the library first (a refusal stops before the "
        "repo is touched), then commits to base without a checkout, or with --pr to the "
        "branch factory-config/onboarding with a pull request. A failure after the library "
        "push carries data.library_commit; run factory onboard again, it connects the items."
    )
    parser.add_argument(
        "--repo", metavar="PATH", help="repository to onboard (default: the current git repo)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="only print the plan (the default without --commit)"
    )
    parser.add_argument(
        "--commit", action="store_true", help="write the library, then commit the repo plan"
    )
    parser.add_argument(
        "--pr",
        action="store_true",
        help="commit to the branch factory-config/onboarding with a PR instead of base",
    )
    parser.add_argument(
        "--expect",
        metavar="DIGEST",
        help="with --commit: refuse when the plan's digest differs (plan_changed)",
    )
    parser.add_argument("-m", "--message", metavar="TEXT", help="with --commit: commit subject")
    parser.add_argument(
        "--keep-local",
        metavar="TYP/JMÉNO",
        action="append",
        default=[],
        help="connect the slot to the library item of the same name; the difference stays "
        "in the repo (repeatable)",
    )
    parser.add_argument(
        "--name",
        metavar="TYP/JMÉNO=NOVÉ",
        action="append",
        default=[],
        help="the name of the new library item of a slot (repeatable)",
    )
    parser.add_argument(
        "--workflows",
        action="store_true",
        help="sssf: also add the library workflows of every other recognised stock chain",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")


def _onboard_conflict(args: argparse.Namespace) -> str | None:
    if args.dry_run and args.commit:
        return "--dry-run and --commit exclude each other"
    if args.expect is not None and not args.commit:
        return "--expect needs --commit"
    if args.message is not None and not args.commit:
        return "-m needs --commit"
    return None


def _onboard_key(text: str, option: str) -> tuple[Any, str]:
    from aifactory.library.model import check_name
    from aifactory.library.store import LibraryStoreError

    kind, sep, name = text.strip().partition("/")
    if not sep or kind not in ("agent", "workflow") or not check_name(name):
        raise LibraryStoreError(
            "invalid_value", f"{option} {text!r}: expected agent/NAME or workflow/NAME"
        )
    return kind, name


def _onboard(args: argparse.Namespace) -> int:
    from aifactory.library.store import LibraryStoreError
    from aifactory.onboard import run_onboard
    from aifactory.providers.base import ProviderError

    conflict = _onboard_conflict(args)
    if conflict is not None:
        error = LibraryStoreError("conflicting_options", conflict)
        return _library_fail(error, args.json, "factory onboard")
    try:
        keep = [_onboard_key(text, "--keep-local") for text in args.keep_local]
        names: list[tuple[Any, str, str]] = []
        for text in args.name:
            key, sep, new = text.partition("=")
            if not sep or not new.strip():
                raise LibraryStoreError(
                    "invalid_value", f"--name {text!r}: expected TYP/JMÉNO=NOVÉ"
                )
            kind, name = _onboard_key(key, "--name")
            names.append((kind, name, new.strip()))
        result = run_onboard(
            Path(args.repo) if args.repo else Path.cwd(),
            commit=args.commit,
            pr=args.pr,
            expect=args.expect,
            message=args.message,
            keep_local=keep,
            names=names,
            workflows=args.workflows,
        )
    except (LibraryStoreError, ProviderError) as exc:
        return _library_fail(exc, args.json, "factory onboard")
    if args.json:
        return _emit_ok(result.to_json(), result.warnings)
    plan = result.plan
    publish = plan.publish
    if result.dry_run:
        for row in plan.report:
            item = f" -> {row.item}" if row.item and row.item != row.subject.split("/")[-1] else ""
            print(f"{row.code:<14} {row.subject}{item}  {row.message}")
            for line in (row.detail or "").splitlines():
                print(f"    {line}")
        if plan.library_plan is not None:
            for i in plan.library_plan.items:
                print(f"{'library':<14} {i.action} {i.type}/{i.name}")
        for f in publish.files:
            print(f"{f.action:<14} {f.path}")
        if plan.exclude is not None:
            for line in plan.exclude["lines"]:
                print(f"{'exclude':<14} {line}")
        for b in publish.blockers:
            print(f"blocked: {b.code}: {b.message}")
        print(f"digest  {publish.digest}")
        if not publish.blockers:
            pr = " --pr" if args.pr else ""
            print(f"next: factory onboard --commit{pr} --expect {publish.digest}")
    else:
        if result.library_commit and plan.library and result.library_commit != plan.library["head"]:
            print(f"library commit {result.library_commit[:12]}")
        if result.pr is not None:
            print(f"opened {result.pr.url} from {result.branch}")
        else:
            pushed = "pushed" if result.pushed else "not pushed"
            moved = "base advanced" if result.advanced else "base not advanced"
            short = (result.commit or "")[:12]
            print(
                f"committed {len(publish.files)} file(s) to {publish.base} "
                f"({short}, {pushed}, {moved})"
            )
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _add_adopt_command(parser: argparse.ArgumentParser) -> None:
    parser.description = (
        "Take over a repo that was onboarded on another machine (decision 8): it is never "
        "extracted again. Reads .factory/ from base (no fetch, no checkout) and fills the "
        "library on this machine to match the committed manifest. Only an onboarded repo is "
        "accepted (not_onboarded, data.state and data.action). Without a library it is "
        "library_missing with data.command 'factory library clone <remote of the manifest>'. "
        "A library with another id gives the warning library_mismatch. An item the library "
        "does not have at all is imported from its copy in base, all in one library commit "
        "(library.lock, library_dirty, library_behind, library_diverged, push_failed). A "
        "version of the manifest missing in an existing item stays unknown with the fix "
        "factory config export TYP JMENO --as NOVE. Returns items[] with type, name, item, "
        "state, versions and adopt (present, imported, import, invalid, unknown). Nothing "
        "is written to the repository."
    )
    parser.add_argument(
        "--repo", metavar="PATH", help="repository to adopt (default: the current git repo)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="only print the plan; write nothing to the library"
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")


def _adopt(args: argparse.Namespace) -> int:
    from aifactory.library.store import LibraryStoreError
    from aifactory.onboard import adopt_repo
    from aifactory.providers.base import ProviderError

    try:
        result = adopt_repo(Path(args.repo) if args.repo else Path.cwd(), dry_run=args.dry_run)
    except (LibraryStoreError, ProviderError) as exc:
        return _library_fail(exc, args.json, "factory adopt")
    if args.json:
        return _emit_ok(result.to_json(), result.warnings)
    library = result.library
    print(f"repo     {result.repo.repo} ({result.repo.base} @ {(result.repo.commit or '')[:7]})")
    print(f"library  {library['path']} ({library['name']}, {library['id']})")
    for item in result.items:
        state = item.state
        print(f"{item.adopt:<9} {state.type}/{state.name} -> {state.item}  {state.state}")
        if item.fix:
            print(f"          fix: {item.fix}")
    if result.dry_run and result.plan is not None:
        print(f"digest   {result.plan['digest']}")
    elif result.committed:
        print(f"library commit {(result.library_commit or '')[:12]}")
    print("the repository was not changed")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _split_list(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def _init_conflict(args: argparse.Namespace) -> str | None:
    plan = args.dry_run or args.commit
    azure = [args.azure_org, args.azure_project, args.azure_repo]
    if args.force and plan:
        return "--force only writes the working tree; not with --dry-run or --commit"
    if args.test_command is not None and plan:
        return "--test-command only writes the working tree; not with --dry-run or --commit"
    if args.pr and not plan:
        return "--pr needs --commit or --dry-run"
    if args.expect is not None and (args.dry_run or not args.commit):
        return "--expect needs --commit without --dry-run"
    if args.message is not None and not args.commit:
        return "-m needs --commit"
    if any(v is not None for v in azure) and args.provider not in (None, "azure"):
        return f"--azure-* need --provider azure, not {args.provider}"
    return None


def _init(args: argparse.Namespace) -> int:
    from aifactory.library.install import init_repo, parse_binding
    from aifactory.library.store import LibraryStoreError
    from aifactory.providers.base import ProviderError

    conflict = _init_conflict(args)
    if conflict is not None:
        error = LibraryStoreError("conflicting_options", conflict)
        return _library_fail(error, args.json, "factory init")
    azure_given = {
        "organization": args.azure_org,
        "project": args.azure_project,
        "repository": args.azure_repo,
    }
    provider = args.provider
    if provider is None and any(azure_given.values()):
        provider = "azure"
    options: dict[str, Any] = {
        "base": args.base,
        "agents": _split_list(args.agents),
        "workflows": _split_list(args.workflows),
        "backlog_dir": args.backlog_dir,
        "specs_dir": args.specs_dir,
        "docs_dir": args.docs_dir,
    }
    repo = Path(args.repo) if args.repo else Path.cwd()
    if args.dry_run or args.commit:
        return _init_plan(args, repo, provider, azure_given, options)
    try:
        bindings = [parse_binding(text) for text in args.bind]
        azure = None
        if provider == "azure":
            if not all(azure_given.values()):
                raise LibraryStoreError(
                    "invalid_value",
                    "--provider azure needs --azure-org, --azure-project and --azure-repo",
                )
            azure = {k: str(v) for k, v in azure_given.items()}
        result = init_repo(
            repo,
            provider=provider or "local",
            azure=azure,
            bindings=bindings,
            force=args.force,
            test_command=args.test_command,
            **options,
        )
    except (LibraryStoreError, ProviderError) as exc:
        return _library_fail(exc, args.json, "factory init")
    if args.json:
        return _emit_ok(result.to_json(), result.warnings)
    for f in result.files:
        print(f"{f.action:<11} {f.path}")
    for line in result.gitignore_added:
        print(f"{'gitignore':<11} {line}")
    library = result.library
    print(f"source      {'seed' if library is None else f'library {library.name}'}")
    choice = result.test_command
    print(f"{'test':<11} {choice.command} ({choice.source})")
    for candidate in choice.candidates:
        if candidate.command != choice.command:
            print(f"{'candidate':<11} {candidate.command} ({candidate.reason})")
    print(f"next: review, commit .factory/ {result.backlog_dir}/ .gitignore to {result.base}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _init_plan(
    args: argparse.Namespace,
    repo: Path,
    provider: str | None,
    azure: dict[str, str | None],
    options: dict[str, Any],
) -> int:
    """``factory init --dry-run`` and ``factory init --commit``."""
    from aifactory.library.install import parse_binding
    from aifactory.library.install_commit import commit_init
    from aifactory.library.store import LibraryStoreError
    from aifactory.providers.base import ProviderError

    try:
        result = commit_init(
            repo,
            expect=args.expect,
            message=args.message,
            pr=args.pr,
            dry_run=args.dry_run,
            provider=provider,
            azure=azure,
            bindings=[parse_binding(text) for text in args.bind],
            **options,
        )
    except (LibraryStoreError, ProviderError) as exc:
        return _library_fail(exc, args.json, "factory init")
    if args.json:
        return _emit_ok(result.to_json(), result.warnings)
    plan = result.plan.publish
    if result.dry_run:
        for f in plan.files:
            print(f"{f.action:<7} {f.path}")
        if result.plan.exclude is not None:
            for line in result.plan.exclude["lines"]:
                print(f"{'exclude':<7} {line}")
        for b in plan.blockers:
            print(f"blocked: {b.code}: {b.message}")
        print(f"digest  {plan.digest}")
        if not plan.blockers:
            pr = " --pr" if args.pr else ""
            print(f"next: factory init --commit{pr} --expect {plan.digest}")
    elif result.pr is not None:
        print(f"opened {result.pr.url} from {result.branch}")
    else:
        pushed = "pushed" if result.pushed else "not pushed"
        moved = "base advanced" if result.advanced else "base not advanced"
        short = (result.commit or "")[:12]
        print(f"committed {len(plan.files)} file(s) to {plan.base} ({short}, {pushed}, {moved})")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _library_fail(exc: Exception, as_json: bool, label: str) -> int:
    from aifactory.library.store import LibraryStoreError

    code = getattr(exc, "code", "internal_error")
    message = getattr(exc, "message", str(exc))
    issues = [i.to_dict() for i in exc.issues] if isinstance(exc, LibraryStoreError) else []
    data = exc.data if isinstance(exc, LibraryStoreError) else None
    if as_json:
        return _emit_fail(code, message, exit_code=2, data=data, issues=issues)
    print(f"{label}: {code}: {message}", file=sys.stderr)
    for issue in issues:
        print(f"  {issue['path']}: {issue['code']}: {issue['message']}", file=sys.stderr)
    return 2


def _library(args: argparse.Namespace) -> int:
    if args.library_command is None:
        args.library_parser.print_help()
        return 0
    from aifactory.library import store
    from aifactory.providers.base import ProviderError

    label = f"factory library {args.library_command}"
    try:
        if args.library_command == "where":
            from aifactory.library.multi_repo import where

            data = where(args.type, args.name)
            if args.json:
                return _emit_ok(data)
            for row in data["repos"]:
                print(f"{row['repo']['id']} {row['slot']} {row['state']} {row['version']}")
            return 0
        if args.library_command in ("clone", "status", "pull", "push"):
            return _library_remote(args)
        if args.library_command == "init":
            result = store.init_library(args.name, remote=args.remote)
            if args.json:
                return _emit_ok(result.to_json(), result.warnings)
            print(f"created {result.plan.library} ({(result.commit or '')[:12]})")
            for item in result.plan.items:
                print(f"  {item.type}/{item.name} {item.version}")
            return 0
        if args.library_command == "list":
            data = store.list_items(args.type)
            if args.json:
                return _emit_ok(data)
            for entry in data["items"]:
                version = entry["short_version"] or "invalid"
                print(f"{entry['type']:<9} {entry['name']:<24} {version}  {entry['date']}")
            return 0
        if args.library_command == "show":
            data = store.show_item(args.type, args.name, args.version)
            if args.json:
                return _emit_ok(data)
            print(f"{data['type']}/{data['name']} {data['version']} ({data['commit'][:12]})")
            for f in data["files"]:
                print(f"  {f['path']}{' (x)' if f['executable'] else ''}")
            for rev in data["history"]:
                print(f"  v{rev['n']} {rev['short_version']} {rev['date']} {rev['author']}")
            return 0
        if args.library_command == "seed":
            return _library_seed(args)
        result = store.import_item(Path(args.path), args.type, args.name, dry_run=args.dry_run)
    except (store.LibraryStoreError, ProviderError) as exc:
        return _library_fail(exc, args.json, label)
    if args.json:
        return _emit_ok(result.to_json(), result.warnings)
    for f in result.plan.files:
        print(f"{f.action:<7} {f.path}")
    item = result.plan.items[0]
    if result.dry_run:
        print(f"digest  {result.plan.digest}")
    elif result.committed:
        print(f"imported {item.type}/{item.name} {item.version} ({(result.commit or '')[:12]})")
    else:
        print(f"{item.type}/{item.name} is unchanged")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _library_seed(args: argparse.Namespace) -> int:
    """`library seed`; errors propagate to `_library`."""
    from aifactory.library.reseed import seed_library

    result = seed_library(args.take, dry_run=args.dry_run)
    if args.json:
        return _emit_ok(result.to_json(), result.warnings)
    for item in result.plan.items:
        if item.action != "unchanged":
            print(f"{item.action:<9} {item.type}/{item.name} {item.version}")
        for f in item.diff:
            print(f.diff(), end="")
    for f in result.plan.files:
        print(f"{f.action:<7} {f.path}")
    if result.dry_run:
        print(f"digest  {result.plan.digest}")
    elif result.committed:
        print(f"took the seed into the library ({(result.commit or '')[:12]})")
    else:
        print("the library already has the seed")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _library_remote(args: argparse.Namespace) -> int:
    """`library clone|status|pull|push`; errors propagate to `_library`."""
    from aifactory.library import remote

    command = args.library_command
    if command == "clone":
        data = remote.clone_library(args.url, args.branch)
    elif command == "status":
        data = remote.library_status(args.fetch)
    elif command == "pull":
        data = remote.pull_library()
    else:
        data = remote.push_library()
    warnings: list[str] = []
    if command in ("clone", "status") and data["compatible"] is False:
        warnings.append(
            f"the library needs factory {data['min_factory_version']}, "
            f"installed is {data['factory_version']}"
        )
    if command in ("clone", "status") and data["seed_update_available"]:
        warnings.append(
            f"seed_update_available: the installed seed has new versions of "
            f"{', '.join(data['seed_updates'])}; run factory library seed"
        )
    if args.json:
        return _emit_ok(data, warnings)
    if command in ("clone", "status"):
        print(f"library  {data['library']} ({data['name']}, {data['id']})")
        print(f"remote   {data['remote'] or '-'}")
        print(f"branch   {data['branch']}")
        if data["remote"] is not None:
            print(f"ahead    {data['ahead']}, behind {data['behind']}")
            print(f"fetched  {data['last_fetch'] or 'never'}")
        print(f"changes  {len(data['uncommitted'])} uncommitted")
        print(f"factory  {data['factory_version']} (needs {data['min_factory_version'] or '-'})")
    elif command == "pull":
        print(f"pulled {data['pulled']} commit(s) from {data['remote']} {data['branch']}")
    else:
        print(f"pushed {data['pushed']} commit(s) to {data['remote']} {data['branch']}")
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _harness(args: argparse.Namespace) -> int:
    if args.harness_command is None:
        args.harness_parser.print_help()
        return 0
    from aifactory.config import ConfigError
    from aifactory.config.loader import load_roster_file
    from aifactory.harness import check

    cfg = None
    if args.config:
        try:
            cfg = load_roster_file(args.config)
        except (OSError, ConfigError) as exc:
            return _fail_from_exception(exc, args.json, "factory harness check")
    statuses = check.check_all(cfg)
    ok = all(status.ok for status in statuses)
    if args.json:
        data = {"harnesses": [s.to_json() for s in statuses]}
        if ok:
            return _emit_ok(data)
        missing = ", ".join(s.name for s in statuses if not s.ok)
        return _emit_fail("harness_missing", f"missing: {missing}", exit_code=1, data=data)
    else:
        for status in statuses:
            where = status.path or "not on PATH"
            detail = status.version if status.ok else status.error
            line = f"{status.name:<7} {where}  {detail}"
            if status.agents:
                line += f"  (agents: {', '.join(status.agents)})"
            print(line)
    return 0 if ok else 1


def _add_config_commands(parser: argparse.ArgumentParser) -> None:
    parser.set_defaults(config_parser=parser)
    sub = parser.add_subparsers(dest="config_command", metavar="<subcommand>")
    roster = sub.add_parser("roster", help="show or edit local agent harness/model/thinking")
    roster.set_defaults(roster_parser=roster)
    commands = roster.add_subparsers(dest="roster_command", metavar="<subcommand>")
    roster_show = commands.add_parser("show", help="show effective local agent settings")
    roster_set = commands.add_parser(
        "set",
        help="change local roster defaults or one named agent",
        description="Switch presets: codex (gpt-6.1-sol, medium) or claude "
        "(claude-opus-5-5, medium). Explicit flags override the preset. A whole-roster "
        "preset clears per-agent harness/model/thinking overrides. Other settings stay. "
        "Changes remain local until factory config commit; workflow step overrides win.",
    )
    roster_set.add_argument("preset", nargs="?", choices=("codex", "claude"))
    roster_set.add_argument("--agent", metavar="NAME", help="change only this agent")
    roster_set.add_argument("--harness", metavar="NAME", help="explicit harness override")
    roster_set.add_argument("--model", metavar="ID", help="explicit model override")
    roster_set.add_argument("--thinking", metavar="LEVEL", help="explicit thinking override")
    roster_set.add_argument("--dry-run", action="store_true", help="validate and show diff only")
    for child in (roster_show, roster_set):
        child.add_argument("--repo", metavar="PATH", help="repository (default: current git repo)")
        child.add_argument("--json", action="store_true", help="print machine-readable JSON")
    status = sub.add_parser(
        "status",
        help="list uncommitted .factory/ changes that runs will not see",
        description="List uncommitted changes in .factory/ against the base commit. "
        "Runs read the committed configuration, so these changes are ignored by them.",
    )
    show = sub.add_parser(
        "show",
        help="show the configuration a run would use",
        description="Load the configuration from the base commit, as a run does, and show it.",
    )
    for child in (status, show):
        child.add_argument("--json", action="store_true", help="print machine-readable JSON")
        child.add_argument(
            "--base", metavar="REF", help="base ref (default: `base` in .factory/config.yaml)"
        )
    commit = sub.add_parser(
        "commit",
        help="commit uncommitted shared .factory/ config to base (push first, then move base)",
        description="Commit the uncommitted shared configuration (the paths of config status: "
        "config.yaml, agents.yaml, roles.yaml, manifest.yaml, prompts/, workflows/, "
        "extensions/ and the repo skills in .claude/skills/ and .agents/skills/; never "
        "local.yaml) to base "
        "in one commit, built on base without a checkout; other staged and unstaged work stays. "
        "--dry-run returns the plan: files {path, action, diff, content}, blockers and digest. "
        "--expect DIGEST refuses a plan that changed since (plan_changed). -m/--message TEXT "
        "sets the commit message. The direct target needs the main checkout on base "
        "(not_on_base) and no run in progress (run_in_progress); with a remote, base is fetched "
        "first (base_behind, base_diverged), the commit is pushed without force (push_failed "
        "changes nothing) and only then the local base is fast-forwarded. --pr pushes the "
        "commit to a branch factory-config/<n> and opens a pull request; base and the checkout "
        "stay. Without changes: committed false.",
    )
    commit.add_argument("--dry-run", action="store_true", help="only print the plan")
    commit.add_argument(
        "--pr", action="store_true", help="open a pull request instead of committing to base"
    )
    commit.add_argument(
        "--expect", metavar="DIGEST", help="commit only if the plan still has this digest"
    )
    commit.add_argument("-m", "--message", metavar="TEXT", help="commit message")
    pull = sub.add_parser(
        "pull",
        help="fast-forward local base to the remote base",
        description="Fetch the remote base and fast-forward the local base to it when no run "
        "is in progress (run_in_progress). A diverged base (base_diverged), uncommitted "
        "changes in the checkout on base (dirty_base) or no remote (no_remote) are refused "
        "and nothing changes.",
    )
    items = sub.add_parser(
        "items",
        help="states of the .factory/ items against the library (local, synced, modified, ...)",
        description="List every agent, workflow, skill and extension of the repo and of "
        ".factory/manifest.yaml with its state against the library: local (not in the "
        "manifest), missing (in the manifest, no files), synced (repo = library head), "
        "unknown (manifest version not in the item's library history), outdated (repo = "
        "manifest, library moved on), modified (repo changed, library did not) and diverged "
        "(both changed), checked in this order. Versions: repo_version (R), manifest_version "
        "(M) and library_version (L, the seed when there is no library). Without --base the "
        "working tree is compared; --base [REF] compares the tree of base (default: `base` in "
        ".factory/config.yaml).",
    )
    items.add_argument(
        "--base",
        nargs="?",
        const="",
        default=None,
        metavar="REF",
        help="compare the committed tree of base instead of the working tree",
    )
    _add_config_edit_commands(sub)
    for child in (commit, pull, items):
        child.add_argument("--json", action="store_true", help="print machine-readable JSON")
        child.add_argument(
            "--repo",
            metavar="PATH",
            help="repository root with .factory/config.yaml (default: the current git repo)",
        )


_CONFIG_MODES = (
    "Modes: --dry-run returns the plan (files {path, action, diff, content}, added, kept, "
    "removed, bindings, blockers, validation, digest) and writes nothing; without an option "
    "the plan is written to the working tree (nothing committed; factory config commit "
    "commits it later; --expect DIGEST of a --dry-run refuses a changed plan with "
    "plan_changed; a run in progress blocks with run_in_progress); --commit [--pr] [--expect "
    "DIGEST] [-m TEXT] commits the plan of the tree of base in one commit (pushed before base "
    "moves; --pr opens a pull request from factory-config/<n>), --commit --dry-run shows that "
    "plan. The planned configuration must load and every workflow of the repo must pass its "
    "preflight (invalid_plan). Blockers: run_in_progress, invalid_plan (working tree); "
    "dirty_paths, invalid_plan, not_on_base, run_in_progress, base_behind, base_diverged "
    "(--commit); dirty_paths, invalid_plan (--pr). A repo without .factory/manifest.yaml is "
    "not_onboarded (fix: factory onboard). Nothing to change: changed false, exit 0."
)


def _add_config_edit_commands(sub: Any) -> None:
    """``factory config add``, ``set`` and ``remove``."""
    add = sub.add_parser(
        "add",
        help="add an item from the library (or the seed) to the repo, with its dependencies",
        description="Copy an agent, workflow, skill or extension from the library HEAD (the "
        "seed when there is no library) into the repo and record it in "
        ".factory/manifest.yaml. Closure: a workflow brings the agents of its steps (roles "
        "from the repo registry or agent: of a step), an agent the skills and extensions of "
        "its defaults; dependencies already in the repo are kept (kept, reason present). "
        "Skills go to .claude/skills/<name>/ with a copy in .agents/skills/<name>/. The "
        "roster entry of a new agent slot takes the item defaults ($specs_dir/ and "
        "$docs_dir/ from config.yaml) overridden by --harness, --model and --thinking. "
        "--as SLOT (agents and workflows) installs under another name; a slot with other "
        "content is slot_taken (fix: --as NEW), with the same content a no-op. " + _CONFIG_MODES,
    )
    add.add_argument("type", choices=("agent", "workflow", "skill", "extension"))
    add.add_argument("name", help="item name in the library")
    add.add_argument("--as", dest="slot", metavar="SLOT", help="name in the repo (agent, workflow)")
    add.add_argument("--agent", metavar="A", help="bind the skill or extension to this agent")
    add.add_argument(
        "--repos", metavar="all|ID,ID", help="operate sequentially on registered repos"
    )
    add.add_argument("--harness", metavar="NAME", help="harness of the new agent slot")
    add.add_argument("--model", metavar="ID", help="model of the new agent slot")
    add.add_argument("--thinking", metavar="LEVEL", help="thinking level of the new agent slot")
    set_ = sub.add_parser(
        "set",
        help="change the bindings of one agent slot in .factory/agents.yaml",
        description="Change only the bindings of an agent slot (harness, model, thinking, "
        "tools, writes, color) by a round trip that keeps comments and key order; the "
        "manifest and the prompts stay. --tools and --writes take a comma list ('' = empty "
        "list, '-' removes the key; writes expand $specs_dir/ and $docs_dir/); --color "
        "#rrggbb ('-' removes it). An unknown thinking level or harness is invalid_value, an "
        "unknown slot unknown_item. " + _CONFIG_MODES,
    )
    set_.add_argument("type", choices=("agent",))
    set_.add_argument("name", metavar="slot", help="agent slot in .factory/agents.yaml")
    set_.add_argument("--harness", metavar="NAME", help="harness (claude, codex, pi)")
    set_.add_argument("--model", metavar="ID", help="model id")
    set_.add_argument("--thinking", metavar="LEVEL", help="thinking level")
    set_.add_argument("--tools", metavar="LIST", help="comma list of tools")
    set_.add_argument("--writes", metavar="LIST", help="comma list of writable paths")
    set_.add_argument("--color", metavar="HEX", help="dashboard color #rrggbb")
    remove = sub.add_parser(
        "remove",
        help="remove an item from the repo (refused while it is in use)",
        description="Remove an agent (roster entry, prompts), workflow, skill (both "
        ".claude/skills/ and .agents/skills/) or extension and its manifest entry. Refused "
        "with in_use (data.used_by) while a workflow of the repo or roles.yaml names the "
        "agent, a backlog task in base names the workflow, or another agent of the manifest "
        "binds the skill or extension. --prune also removes the dependencies recorded in "
        "the manifest that nothing else uses (removed, reason pruned; kept, reason in_use); "
        "local items are never pruned. " + _CONFIG_MODES,
    )
    remove.add_argument("type", choices=("agent", "workflow", "skill", "extension"))
    remove.add_argument("name", help="item name in the repo")
    remove.add_argument("--prune", action="store_true", help="also remove unused dependencies")
    export = sub.add_parser(
        "export",
        help="write the copy of an item in the repo into the library, then connect it",
        description="Write the repo copy of an agent (roster purpose and prompts), workflow, "
        "skill or extension into the library and then record it in .factory/manifest.yaml "
        "(the library item and its version). An item of the manifest becomes the next "
        "version of its library item; with --as NEW (agents and workflows) or for a local "
        "item (no manifest entry) it becomes a new library item, and a library item of that "
        "name with other content is item_exists (fix: --as NEW). When the library head moved "
        "on since the manifest version and the repo copy differs from it, the export is "
        "library_changed_since (fix: factory update, or --as NEW). An exported agent keeps "
        "the agent.yaml of its library item with the roster purpose; a new one gets its "
        "defaults from the roster entry. Order: the library is written first (library.lock, "
        "fetch, library_behind, library_diverged, library_dirty, push without force: a "
        "rejected push is push_failed and the repo is not touched), then the repo. When the "
        "repo write fails after the library push, the library holds an unused version "
        "(data.library_commit) and the same export run again connects it. data.export has "
        "item, action (create, update, connect), version and the repo, manifest and library "
        "versions; data.library_plan the library files; data.library_commit the library "
        "commit. Moving an agent to another repo: export it here, then factory config add "
        "agent NAME in the other repo. The digest covers the library and the repo plan. "
        + _CONFIG_MODES,
    )
    export.add_argument("type", choices=("agent", "workflow", "skill", "extension"))
    export.add_argument("name", help="item name in the repo")
    export.add_argument(
        "--as",
        dest="slot",
        metavar="NEW",
        help="export as a new library item NEW (agent, workflow)",
    )
    revert = sub.add_parser(
        "revert",
        help="put the copy of an item in the repo back to the manifest version or the head",
        description="Replace the repo copy of an item with a library version: --to manifest "
        "(default) the version recorded in .factory/manifest.yaml, found in the history of "
        "the library item (unknown_version, state unknown, when it is not there; fix: --to "
        "head), --to head the library head (the seed without a library), which also moves the "
        "manifest version. Files the version does not have are removed; the bindings in "
        "agents.yaml stay, only an agent's purpose follows the version. A local item (no "
        "manifest entry) is unknown_item. data.revert has to, item, version, commit and the "
        "repo version before. " + _CONFIG_MODES,
    )
    revert.add_argument("type", choices=("agent", "workflow", "skill", "extension"))
    revert.add_argument("name", help="item name in the repo")
    revert.add_argument(
        "--to",
        choices=("manifest", "head"),
        default="manifest",
        help="the version to go back to (default: manifest)",
    )
    for child in (add, set_, remove, export, revert):
        child.add_argument("--dry-run", action="store_true", help="only print the plan")
        child.add_argument(
            "--commit", action="store_true", help="commit to base in one commit (default: write)"
        )
        child.add_argument(
            "--pr", action="store_true", help="with --commit: open a pull request instead"
        )
        child.add_argument(
            "--expect",
            action="append",
            metavar="DIGEST",
            help="digest (repeat ID=DIGEST with --repos)",
        )
        child.add_argument("-m", "--message", metavar="TEXT", help="commit message (--commit)")
        child.add_argument("--json", action="store_true", help="print machine-readable JSON")
        child.add_argument(
            "--repo", metavar="PATH", help="repository (default: the current git repo)"
        )
    diff = sub.add_parser(
        "diff",
        help="diff the repo copy of an item against the manifest version and the library head",
        description="Read only. Compare the working-tree copy of an item with the version in "
        ".factory/manifest.yaml (from the library history) and with the library head (the "
        "seed without a library). data.manifest and data.head each have available (false "
        "with reason local, unknown or unknown_item), version, commit, same and files[] "
        "{path, status (added: only in the repo, removed: only in the library version, "
        "modified, mode), binary, diff (unified, library version first)}; an agent's purpose "
        "is the entry .factory/agents.yaml#NAME.purpose. data.state is the item state of "
        "config items; data.repo_version, manifest_version and library_version are R, M, L.",
    )
    diff.add_argument("type", choices=("agent", "workflow", "skill", "extension"))
    diff.add_argument("name", help="item name in the repo")
    diff.add_argument("--json", action="store_true", help="print machine-readable JSON")
    diff.add_argument("--repo", metavar="PATH", help="repository (default: the current git repo)")


def _config_edit_conflict(args: argparse.Namespace) -> str | None:
    if args.pr and not args.commit:
        return "--pr needs --commit"
    if args.message is not None and not args.commit:
        return "-m needs --commit"
    if args.expect is not None and args.dry_run:
        return "--expect is not for --dry-run"
    return None


def _config_edit(args: argparse.Namespace) -> int:
    """``factory config add|set|remove|export|revert``."""
    from aifactory.library.config_edit import run_config
    from aifactory.library.store import LibraryStoreError
    from aifactory.providers.base import ProviderError

    command = args.config_command
    label = f"factory config {command}"
    conflict = _config_edit_conflict(args)
    if conflict is not None:
        return _library_fail(LibraryStoreError("conflicting_options", conflict), args.json, label)
    options: dict[str, Any]
    if command == "add":
        options = {k: getattr(args, k) for k in ("slot", "harness", "model", "thinking", "agent")}
    elif command == "set":
        keys = ("harness", "model", "thinking", "tools", "writes", "color")
        options = {k: getattr(args, k) for k in keys}
    elif command == "export":
        options = {"slot": args.slot}
    elif command == "revert":
        options = {"to": args.to}
    else:
        options = {"prune": args.prune}
    if getattr(args, "repos", None) is not None:
        return _multi_repo(args, "add", options)
    if args.expect and len(args.expect) != 1:
        return _library_fail(
            LibraryStoreError("invalid_value", "use one --expect for a single repo"),
            args.json,
            label,
        )
    try:
        result = run_config(
            command,
            Path(args.repo) if args.repo else Path.cwd(),
            type=args.type,
            name=args.name,
            dry_run=args.dry_run,
            commit=args.commit,
            pr=args.pr,
            expect=args.expect[0] if args.expect else None,
            message=args.message,
            **options,
        )
    except (LibraryStoreError, ProviderError) as exc:
        return _library_fail(exc, args.json, label)
    if args.json:
        return _emit_ok(result.to_json(), result.warnings)
    plan = result.plan
    publish = plan.publish
    if plan.library_plan is not None:
        for f in plan.library_plan.files:
            print(f"{f.action:<7} library:{f.path}")
    for f in publish.files:
        print(f"{f.action:<7} {f.path}")
    for key in ("export", "revert"):
        info = plan.change.detail.get(key)
        if info:
            how = info.get("action", info.get("to"))
            print(f"{key:<7} {info['item']} {info['short_version']} ({how})")
    for what, rows in (
        ("added", plan.change.added),
        ("kept", plan.change.kept),
        ("removed", plan.change.removed),
    ):
        for row in rows:
            print(f"{what:<7} {row['type']} {row['name']} ({row['reason']})")
    if result.dry_run:
        for b in publish.blockers:
            print(f"blocked: {b.code}: {b.message}")
        print(f"digest  {publish.digest}")
        if plan.changed and not publish.blockers:
            argv = [a for a in sys.argv[1:] if a not in ("--dry-run", "--json")]
            print(f"next: factory {' '.join(argv)} --expect {publish.digest}")
    elif not plan.changed:
        print("nothing to change")
    elif result.written:
        print("next: factory config commit")
    elif result.pr is not None:
        print(f"opened {result.pr.url} from {result.branch}")
    else:
        pushed = "pushed" if result.pushed else "not pushed"
        moved = "base advanced" if result.advanced else "base not advanced"
        short = (result.commit or "")[:12]
        print(
            f"committed {len(publish.files)} file(s) to {publish.base} ({short}, {pushed}, {moved})"
        )
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _multi_repo(args: argparse.Namespace, command: str, options: dict[str, Any]) -> int:
    from aifactory.library.multi_repo import run_repos
    from aifactory.library.store import LibraryStoreError

    if args.repo:
        return _library_fail(
            LibraryStoreError("conflicting_options", "--repo and --repos conflict"),
            args.json,
            "factory " + command,
        )
    if command == "add":
        options = {"type": args.type, "name": args.name, **options}
    try:
        data = run_repos(
            command,
            args.repos,
            dry_run=args.dry_run,
            commit=args.commit,
            pr=args.pr,
            expect=args.expect or (),
            message=args.message,
            **options,
        )
    except LibraryStoreError as exc:
        return _library_fail(exc, args.json, "factory " + command)
    if args.json:
        return _emit_ok(data)
    for row in data["repos"]:
        print(f"{row['repo']['id']} {row['status']}")
        if row["plan"] is not None:
            print(f"  digest {row['plan']['digest']}")
    return 0


def _add_update_command(parser: argparse.ArgumentParser) -> None:
    parser.description = (
        "Bring new versions of the repo's items (.factory/manifest.yaml) from the library "
        "HEAD, or the seed when there is no library, file by file. Units: an agent's purpose, "
        "system.md and user.md; a workflow's file; every file of a skill or extension "
        "(added and deleted ones too). Per unit, base is the manifest version (from the "
        "library history), ours the repo copy, theirs the library head: ours = base takes "
        "theirs (take), theirs = base keeps ours (keep), ours = theirs is same, else a "
        "conflict: ours stays and data.update.items[].files[] shows ours_diff and "
        "theirs_diff. --take TYPE/NAME[:FILE] takes theirs (taken); --merge TYPE/NAME "
        "takes the result of git merge-file (merged) only without conflicts and when the "
        "merged item is valid, else merge_conflict and nothing is written. An item whose "
        "manifest version is not in the history (state unknown) has no base: diff shows ours "
        "against theirs, ours stays unless --take. A missing item gets its files back "
        "(restore). The manifest moves to the head and written_by to this HAIFA; missing "
        "prompts of declared agents and the runtime lines of .gitignore are added. "
        "Migrations are listed with their diff (data.update.migrations) and run only with "
        "--migrate ID (m001: levels module -> project, comments kept). data.update has "
        "items, conflicts, gitignore, migrations and manifest. Refused: not_onboarded (no "
        "manifest in base; data.fix factory onboard or factory init), config_not_committed "
        "(the manifest only in the working tree), format_unsupported. " + _CONFIG_MODES
    )
    parser.add_argument(
        "--take",
        action="append",
        default=[],
        metavar="TYPE/NAME[:FILE]",
        help="take the library version of an item or of one file of it (repeatable)",
    )
    parser.add_argument(
        "--merge",
        action="append",
        default=[],
        metavar="TYPE/NAME",
        help="merge the conflicting files of an item with git merge-file (repeatable)",
    )
    parser.add_argument(
        "--migrate",
        action="append",
        default=[],
        metavar="ID",
        help="run a migration listed by the plan, e.g. m001 (repeatable)",
    )
    parser.add_argument(
        "--repos", metavar="all|ID,ID", help="operate sequentially on registered repos"
    )
    parser.add_argument(
        "--item",
        action="append",
        default=[],
        metavar="TYPE/NAME",
        help="update only selected items (repeatable)",
    )
    parser.add_argument("--dry-run", action="store_true", help="only print the plan")
    parser.add_argument(
        "--commit", action="store_true", help="commit to base in one commit (default: write)"
    )
    parser.add_argument(
        "--pr", action="store_true", help="with --commit: open a pull request instead"
    )
    parser.add_argument(
        "--expect", action="append", metavar="DIGEST", help="digest (repeat ID=DIGEST with --repos)"
    )
    parser.add_argument("-m", "--message", metavar="TEXT", help="commit message (--commit)")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--repo", metavar="PATH", help="repository (default: the current git repo)")


def _update(args: argparse.Namespace) -> int:
    """``factory update``."""
    from aifactory.library.config_edit import hist_short
    from aifactory.library.store import LibraryStoreError
    from aifactory.library.update import run_update
    from aifactory.providers.base import ProviderError

    label = "factory update"
    conflict = _config_edit_conflict(args)
    if conflict is not None:
        return _library_fail(LibraryStoreError("conflicting_options", conflict), args.json, label)
    if args.repos is not None:
        return _multi_repo(
            args,
            "update",
            {"item": args.item, "take": args.take, "merge": args.merge, "migrate": args.migrate},
        )
    if args.expect and len(args.expect) != 1:
        return _library_fail(
            LibraryStoreError("invalid_value", "use one --expect for a single repo"),
            args.json,
            label,
        )
    try:
        result = run_update(
            Path(args.repo) if args.repo else Path.cwd(),
            item=args.item,
            take=args.take,
            merge=args.merge,
            migrate=args.migrate,
            dry_run=args.dry_run,
            commit=args.commit,
            pr=args.pr,
            expect=args.expect[0] if args.expect else None,
            message=args.message,
        )
    except (LibraryStoreError, ProviderError) as exc:
        return _library_fail(exc, args.json, label)
    if args.json:
        return _emit_ok(result.to_json(), result.warnings)
    plan = result.plan
    publish = plan.publish
    info = plan.change.detail.get("update", {})
    for item in info.get("items", []):
        versions = (
            f"{hist_short(item['manifest_version'])} -> {hist_short(item['library_version'])}"
        )
        print(f"{item['action']:<8} {item['type']}/{item['name']} {versions}")
        for f in item["files"]:
            if f["status"] == "same":
                continue
            print(f"  {f['status']:<8} {f['file']}")
            for key in ("ours_diff", "theirs_diff", "diff"):
                text = f.get(key)
                if text and (f["status"] in ("conflict", "unknown") or result.dry_run):
                    print(text, end="" if text.endswith("\n") else "\n")
    for row in info.get("restored", []):
        print(f"restore  agent/{row['name']} {', '.join(row['files'])}")
    for line in info.get("gitignore", {}).get("added", []):
        print(f"add      .gitignore {line}")
    for migration in info.get("migrations", []):
        how = "applied" if migration["applied"] else f"run with --migrate {migration['id']}"
        print(f"migrate  {migration['id']} {migration['title']} ({how})")
        if migration["diff"]:
            text = migration["diff"]
            print(text, end="" if text.endswith("\n") else "\n")
    for f in publish.files:
        print(f"{f.action:<7} {f.path}")
    if result.dry_run:
        for b in publish.blockers:
            print(f"blocked: {b.code}: {b.message}")
        print(f"digest  {publish.digest}")
        if plan.changed and not publish.blockers:
            argv = [a for a in sys.argv[1:] if a not in ("--dry-run", "--json")]
            print(f"next: factory {' '.join(argv)} --expect {publish.digest}")
    elif not plan.changed:
        print("nothing to change")
    elif result.written:
        print("next: factory config commit")
    elif result.pr is not None:
        print(f"opened {result.pr.url} from {result.branch}")
    else:
        pushed = "pushed" if result.pushed else "not pushed"
        moved = "base advanced" if result.advanced else "base not advanced"
        short = (result.commit or "")[:12]
        print(
            f"committed {len(publish.files)} file(s) to {publish.base} ({short}, {pushed}, {moved})"
        )
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _config_diff(args: argparse.Namespace) -> int:
    """``factory config diff``: read only."""
    from aifactory.library.config_transfer import diff_item
    from aifactory.library.store import LibraryStoreError
    from aifactory.providers.base import ProviderError

    try:
        data = diff_item(Path(args.repo) if args.repo else Path.cwd(), args.type, args.name)
    except (LibraryStoreError, ProviderError) as exc:
        return _library_fail(exc, args.json, "factory config diff")
    if args.json:
        return _emit_ok(data)
    print(f"{data['type']} {data['name']}: {data['state']}")
    for label in ("manifest", "head"):
        side = data[label]
        if not side["available"]:
            print(f"-- {label}: not available ({side['reason']})")
            continue
        state = "same" if side["same"] else f"{len(side['files'])} file(s) differ"
        print(f"-- {label} {side['short_version']}: {state}")
        for f in side["files"]:
            if f["diff"]:
                print(f["diff"], end="" if f["diff"].endswith("\n") else "\n")
            else:
                print(f"{f['status']} {f['path']}")
    return 0


def _config_status(args: argparse.Namespace) -> int:
    from aifactory.config import (
        ConfigError,
        change_warnings,
        config_changes,
        repo_root,
        resolve_commit,
        worktree_base,
    )

    try:
        root = repo_root(Path.cwd())
        base = args.base.strip() if args.base else worktree_base(root)
        sha = resolve_commit(root, base)
        changes = config_changes(root, sha)
    except ConfigError as exc:
        return _fail_from_exception(exc, args.json, "factory config status")
    warnings = change_warnings(changes, base, sha)
    if args.json:
        data: dict[str, Any] = {
            "base": base,
            "commit": sha,
            "clean": not changes,
            "changes": [c.to_dict() for c in changes],
        }
        return _emit_ok(data, warnings)
    if not changes:
        print(f"config in sync with {base} ({sha[:7]})")
    else:
        for change in changes:
            print(f"{change.status:<9} {change.path}")
        print(f"runs use {base} ({sha[:7]}); commit these changes to include them")
    return 0


def _config_show(args: argparse.Namespace) -> int:
    from aifactory.config import ConfigError, load_run_config

    try:
        run = load_run_config(Path.cwd(), args.base)
    except ConfigError as exc:
        return _fail_from_exception(exc, args.json, "factory config show")
    if args.json:
        data, warnings = strip_payload(run.to_json())
        return _emit_ok(data, warnings)
    data = run.to_json()
    print(f"base      {run.base} ({run.commit[:7]})")
    print(f"agents    {', '.join(data['agents']) or '-'}")
    print(f"workflows {', '.join(data['workflows']) or '-'}")
    print(f"prompts   {', '.join(data['prompts']) or '-'}")
    print(f"trace db  {run.local.trace_db}")
    for warning in run.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _config(args: argparse.Namespace) -> int:
    if args.config_command is None:
        args.config_parser.print_help()
        return 0
    if args.config_command == "status":
        return _config_status(args)
    if args.config_command == "commit":
        return _config_commit(args)
    if args.config_command == "pull":
        return _config_pull(args)
    if args.config_command == "items":
        return _config_items(args)
    if args.config_command in ("add", "set", "remove", "export", "revert"):
        return _config_edit(args)
    if args.config_command == "diff":
        return _config_diff(args)
    if args.config_command == "roster":
        return _config_roster(args)
    return _config_show(args)


def _config_roster(args: argparse.Namespace) -> int:
    from aifactory.config import ConfigError
    from aifactory.config.roster import roster

    if args.roster_command is None:
        args.roster_parser.print_help()
        return 0
    options = {}
    if args.roster_command == "set":
        options = {
            key: getattr(args, key)
            for key in ("preset", "agent", "harness", "model", "thinking", "dry_run")
        }
        options["change"] = True
    try:
        data = roster(Path(args.repo) if args.repo else Path.cwd(), **options)
    except ConfigError as exc:
        return _fail_from_exception(exc, args.json, "factory config roster")
    warnings = []
    if data.get("changed"):
        warnings.append("local changes: runs use committed base until factory config commit")
    if data.get("comments_preserved") is False:
        warnings.append("complex YAML was serialized; review formatting and comments in the diff")
    if args.json:
        return _emit_ok(data, warnings)
    for agent in data["agents"]:
        print(f"{agent['name']:<20} {agent['harness']:<8} {agent['model']:<28} {agent['thinking']}")
    if "diff" in data:
        print(data["diff"] or "no changes", end="\n")
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _config_items(args: argparse.Namespace) -> int:
    from aifactory.config import ConfigError
    from aifactory.library.state import repo_items
    from aifactory.providers.base import ProviderError

    label = "factory config items"
    try:
        root = Path(args.repo) if args.repo else Path.cwd()
        data = repo_items(root, args.base)
    except ConfigError as exc:
        return _fail_from_exception(exc, args.json, label)
    except ProviderError as exc:
        return _library_fail(exc, args.json, label)
    if args.json:
        return _emit_ok(data)
    if data["manifest"] is None:
        print("no .factory/manifest.yaml (format 0): every item is local")
    for item in data["items"]:
        short = item["short"]
        versions = " ".join(f"{k}={v or '-'}" for k, v in short.items())
        origin = f" <- {item['item']}" if item["item"] and item["item"] != item["name"] else ""
        print(f"{item['type']:<9} {item['name'] + origin:<32} {item['state']:<9} {versions}")
    return 0


def _config_commit_fail(exc: ConfigCommitError, as_json: bool, label: str) -> int:
    if as_json:
        return _emit_fail(exc.code, exc.message, exit_code=2, data=exc.data, issues=exc.issues)
    print(f"{label}: {exc.code}: {exc.message}", file=sys.stderr)
    for issue in exc.issues:
        print(f"  {issue.get('path')}: {issue.get('message')}", file=sys.stderr)
    return 2


def _config_commit(args: argparse.Namespace) -> int:
    from aifactory.config import ConfigError
    from aifactory.config.commit import ConfigCommitError, commit_config

    label = "factory config commit"
    try:
        result = commit_config(
            _backlog_root(args.repo),
            pr=args.pr,
            dry_run=args.dry_run,
            expect=args.expect,
            message=args.message,
        )
    except ConfigCommitError as exc:
        return _config_commit_fail(exc, args.json, label)
    except ConfigError as exc:
        return _fail_from_exception(exc, args.json, label)
    if args.json:
        return _emit_ok(result.to_json(), result.warnings)
    plan = result.plan
    if result.dry_run:
        for f in plan.files:
            print(f"{f.action:<7} {f.path}")
        for b in plan.blockers:
            print(f"blocked: {b.code}: {b.message}")
        print(f"digest  {plan.digest}")
    elif not result.committed:
        print("nothing to commit in the configuration")
    elif result.pr is not None:
        print(f"opened {result.pr.url} from {result.branch}")
    else:
        pushed = "pushed" if result.pushed else "not pushed"
        moved = "base advanced" if result.advanced else "base not advanced"
        short = (result.commit or "")[:12]
        print(f"committed {len(plan.files)} file(s) to {plan.base} ({short}, {pushed}, {moved})")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _config_pull(args: argparse.Namespace) -> int:
    from aifactory.config import ConfigError
    from aifactory.config.commit import ConfigCommitError, pull_config

    label = "factory config pull"
    try:
        result = pull_config(_backlog_root(args.repo))
    except ConfigCommitError as exc:
        return _config_commit_fail(exc, args.json, label)
    except ConfigError as exc:
        return _fail_from_exception(exc, args.json, label)
    if args.json:
        return _emit_ok(result.to_json(), result.warnings)
    if result.updated:
        print(f"{result.base}: {result.before[:7]} -> {result.after[:7]}")
    else:
        print(f"{result.base} is up to date with {result.remote}/{result.base}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _add_backlog_commands(parser: argparse.ArgumentParser) -> None:
    from aifactory.backlog import CONTAINER_KEYS, STATUS_FILTERS

    parser.set_defaults(backlog_parser=parser)
    sub = parser.add_subparsers(dest="backlog_command", metavar="<subcommand>")
    check = sub.add_parser(
        "check",
        help="validate the backlog and list every problem",
        description="Load the backlog and report duplicate ids, unknown references, "
        "dependency cycles, invalid states and missing fields. Exits 1 on problems.",
    )
    list_ = sub.add_parser(
        "list",
        help="print the backlog tree with derived states",
        description="Print the backlog tree with task states (ready/blocked derived from "
        "depends_on) and progress of every container.",
    )
    sync = sub.add_parser(
        "sync",
        help="open one PR that marks tasks done whose PR was merged outside factory",
        description="Refresh the states of task PRs; for tasks whose PR was merged outside "
        "factory and that are not done in base, open one PR that sets status: done and adds "
        "a line to '## Běhy'. The commit goes only to its own branch factory-sync/<n>, never "
        "to base, and the sync PR is not merged. Closed PRs leave the task alone.",
    )
    auto = sub.add_parser(
        "auto-continue",
        help="switch auto-continue on, off or back to inherited for a project or step",
        description="Write (--on/--off) or remove (--inherit) 'auto_continue' in the index.md "
        "of a project or step. With auto_continue: true, a task run that opened its PR is "
        "followed by the next ready task that has auto_continue: true too; a chain never "
        "starts a task with it off. The change is written to the working tree; runs read the "
        "backlog from base, so commit it first.",
    )
    auto.add_argument("id", metavar="ID", help="project or step id")
    mode = auto.add_mutually_exclusive_group(required=True)
    mode.add_argument("--on", dest="auto_mode", action="store_const", const="on")
    mode.add_argument("--off", dest="auto_mode", action="store_const", const="off")
    mode.add_argument(
        "--inherit",
        dest="auto_mode",
        action="store_const",
        const="inherit",
        help="remove the field, inherit it from the parent",
    )
    merge = sub.add_parser(
        "auto-merge",
        help="switch auto-merge on, off or back to inherited for a project or step",
        description="Write (--on/--off) or remove (--inherit) 'auto_merge' in the index.md "
        "of a project or step (a task sets it with 'factory task edit ID --auto-merge'). "
        "With auto_merge: true, a succeeded run whose last review approved and whose PR "
        "merges cleanly with no red checks is approved and merged like 'factory task "
        "approve'; a workflow without a review phase is never merged automatically. "
        "Auto-continue then starts the next task only after the merge. The change is "
        "written to the working tree; runs read the backlog from base, so commit it first.",
    )
    merge.add_argument("id", metavar="ID", help="project or step id")
    merge_mode = merge.add_mutually_exclusive_group(required=True)
    merge_mode.add_argument("--on", dest="auto_mode", action="store_const", const="on")
    merge_mode.add_argument("--off", dest="auto_mode", action="store_const", const="off")
    merge_mode.add_argument(
        "--inherit",
        dest="auto_mode",
        action="store_const",
        const="inherit",
        help="remove the field, inherit it from the parent",
    )
    commit = sub.add_parser(
        "commit",
        help="commit the backlog working-tree changes to base (only files in the backlog roots)",
        description="Commit every change under the backlog roots, backlog_dir or every "
        "directory of backlog_dirs (new, edited and deleted task "
        "files) to base, so runs see it. Other changes in the checkout are left alone. The "
        "main checkout must be on base and the backlog must be valid. With a remote, the "
        "commit is pushed.",
    )
    commit.add_argument("-m", "--message", metavar="TEXT", help="commit message")
    add = sub.add_parser(
        "add",
        help="create a project, or a step in a project (a directory with index.md)",
        description="Create a project (without PARENT) or a step of project PARENT: the "
        "directory <code>-<slug> with an index.md holding id and title (a step's directory "
        "drops the project's prefix: M01-S03 -> S03-<slug>). The id matches the task id "
        "pattern, is unique, and a step's id starts with its project's id and '-'. The "
        "backlog is validated before writing; a change that would break it is rejected. "
        "Nothing is committed (factory backlog commit).",
    )
    add.add_argument(
        "parent", nargs="?", metavar="PARENT", help="project id for a new step (none: a project)"
    )
    add.add_argument(
        "--id", dest="container_id", required=True, metavar="CODE", help="short code, e.g. M01"
    )
    add.add_argument("--title", required=True, metavar="TEXT", help="short title")
    add.add_argument("--body", default="", metavar="TEXT", help="description in index.md")
    add.add_argument(
        "--backlog-dir",
        metavar="DIR",
        help="backlog root of a new project, one of backlog_dirs (it may match a pattern "
        "like moduly/*/backlog and not exist yet); default: the first existing root",
    )
    edit = sub.add_parser(
        "edit",
        help="change the title and settings of a project or step (its index.md)",
        description="Change the title of a project or step and set or remove (--clear) the "
        f"keys {', '.join(CONTAINER_KEYS)} of its index.md. Other keys and the description "
        "stay as they are. The backlog is validated before writing; nothing is committed.",
    )
    edit.add_argument("id", metavar="ID", help="project or step id")
    edit.add_argument("--title", metavar="TEXT", help="new title")
    edit.add_argument("--workflow", metavar="NAME", help="set the workflow")
    edit.add_argument("--writes", nargs="*", metavar="PATH", help="set writes (none = [])")
    edit.add_argument(
        "--test",
        nargs="+",
        metavar="ARG",
        help="set the test command: one argument is a shell string, more are argv",
    )
    edit.add_argument("--source", metavar="TEXT", help="set source")
    edit.add_argument("--target", metavar="TEXT", help="set target")
    edit.add_argument("--specs-dir", metavar="DIR", help="set specs_dir")
    edit.add_argument("--docs-dir", metavar="DIR", help="set docs_dir")
    edit.add_argument("--auto-continue", choices=("on", "off"), help="set auto_continue")
    edit.add_argument(
        "--clear",
        nargs="+",
        action="extend",
        default=[],
        choices=CONTAINER_KEYS,
        metavar="KEY",
        help=f"remove keys (inherit them again): {', '.join(CONTAINER_KEYS)}",
    )
    for child in (check, list_, sync, auto, merge, commit, add, edit):
        child.add_argument("--json", action="store_true", help="print machine-readable JSON")
        child.add_argument(
            "--repo",
            metavar="PATH",
            help="repository root with .factory/config.yaml (default: the current git repo)",
        )
    list_.add_argument("--status", choices=STATUS_FILTERS, help="show only tasks in this state")
    list_.add_argument("--project", metavar="ID", help="show only this project (id or directory)")


def _emit(envelope: Mapping[str, Any]) -> None:
    print(json.dumps(envelope, ensure_ascii=False, indent=2))


def _emit_ok(data: Mapping[str, Any], warnings: Iterable[str] = ()) -> int:
    _emit(envelope_ok(data, warnings))
    return 0


def _emit_fail(
    code: str,
    message: str,
    *,
    exit_code: int,
    data: Mapping[str, Any] | None = None,
    path: str | None = None,
    id: str | None = None,
    issues: Iterable[Mapping[str, Any]] = (),
    warnings: Iterable[str] = (),
) -> int:
    _emit(
        envelope_fail(code, message, data=data, path=path, id=id, issues=issues, warnings=warnings)
    )
    return exit_code


def _config_issues(exc: Exception) -> list[dict[str, Any]]:
    from aifactory.config import ConfigError

    if not isinstance(exc, ConfigError):
        return []
    return [
        {"code": exc.code, "message": i.message, "path": i.path, "id": None} for i in exc.issues
    ]


def _fail_from_exception(exc: Exception, as_json: bool, label: str) -> int:
    """Report an expected error of a command (``label``, e.g. ``factory task run``)."""
    from aifactory.backlog import TaskEditError
    from aifactory.config import ConfigError
    from aifactory.engine.role_registry import RolesError
    from aifactory.harness.config import HarnessConfigError
    from aifactory.review import ReviewError
    from aifactory.run import TaskRunError

    if isinstance(exc, TaskEditError):
        if as_json:
            return _emit_fail(
                exc.code,
                exc.message,
                exit_code=exc.exit_code,
                path=exc.path,
                id=exc.id,
                issues=[i.to_dict() for i in exc.issues],
            )
        print(f"{label}: {exc.message}", file=sys.stderr)
        for issue in exc.issues:
            print(f"  {issue.path}: {issue.code}: {issue.message}", file=sys.stderr)
        return exc.exit_code
    if isinstance(exc, TaskRunError | ReviewError):
        if as_json:
            return _emit_fail(exc.code, exc.message, exit_code=2)
        print(f"{label}: {exc.code}: {exc.message}", file=sys.stderr)
        return 2
    if as_json:
        if isinstance(exc, RolesError):
            issues = [i.to_dict() for i in exc.issues]
            return _emit_fail("invalid_roles", str(exc), exit_code=2, issues=issues)
        issues_: list[dict[str, Any]] = []
        code = "invalid_config"
        if isinstance(exc, ConfigError):
            issues_ = _config_issues(exc)
            code = exc.code
        elif isinstance(exc, HarnessConfigError):
            issues_ = [{"code": "invalid_config", "message": p} for p in exc.problems]
        return _emit_fail(code, str(exc), exit_code=2, issues=issues_)
    if isinstance(exc, ConfigError) and exc.code != "invalid_config":
        print(f"{label}: {exc.code}: {exc}", file=sys.stderr)
        return 2
    print(f"{label}: {exc}", file=sys.stderr)
    return 2


def _problem_warnings(count: int) -> list[str]:
    return [f"{count} problem(s), run 'factory backlog check'"] if count else []


def _backlog_root(repo: str | None) -> Path:
    from aifactory.config import ConfigError, repo_root

    if repo:
        return Path(repo)
    try:
        return repo_root(Path.cwd())
    except ConfigError:
        return Path.cwd()


def _backlog_sync(args: argparse.Namespace) -> int:
    from aifactory.config import ConfigError
    from aifactory.review import ReviewError, sync_backlog
    from aifactory.run import TaskRunError

    try:
        result = sync_backlog(_backlog_root(args.repo))
    except (ConfigError, ReviewError, TaskRunError) as exc:
        return _fail_from_exception(exc, args.json, "factory backlog sync")
    if args.json:
        data, warnings = strip_payload(result.to_json())
        return _emit_ok(data, warnings)
    ids = ", ".join(t.task_id for t in result.tasks)
    if result.pr is None:
        print("nothing to sync")
    elif result.created:
        print(f"opened {result.pr.url}: done for {ids}")
    elif result.updated:
        print(f"updated {result.pr.url}: done for {ids}")
    else:
        print(f"sync PR {result.pr.url} already open: done for {ids}")
    for skip in result.skipped:
        print(f"skipped {skip.task_id}: {skip.reason}")
    for state in result.states:
        print(f"PR {state['url']} of {state['task_id']} is {state['state']}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _backlog_auto_continue(args: argparse.Namespace) -> int:
    from aifactory.backlog import set_auto_continue

    return _backlog_flag(args, "auto_continue", set_auto_continue, "backlog auto-continue")


def _backlog_auto_merge(args: argparse.Namespace) -> int:
    from aifactory.backlog import set_auto_merge

    return _backlog_flag(args, "auto_merge", set_auto_merge, "backlog auto-merge")


def _backlog_flag(
    args: argparse.Namespace,
    key: str,
    setter: Callable[[Path, str, bool | None], ContainerWriteResult],
    command: str,
) -> int:
    from aifactory.backlog import TaskEditError
    from aifactory.config import ConfigError

    enabled = {"on": True, "off": False, "inherit": None}[args.auto_mode]
    try:
        result = setter(_backlog_root(args.repo), args.id, enabled)
    except (ConfigError, TaskEditError) as exc:
        return _fail_from_exception(exc, args.json, f"factory {command}")
    container = result.container
    value = container.defaults.get(key)
    if args.json:
        data = {
            "changed": result.changed,
            "id": container.id,
            "level": container.level,
            "path": result.path,
            key: value if isinstance(value, bool) else None,
            "issues": [i.to_dict() for i in result.issues],
        }
        return _emit_ok(data, _problem_warnings(len(result.issues)))
    if not result.changed:
        print(f"unchanged {container.id}")
    else:
        label = {"on": "on", "off": "off", "inherit": "inherited"}[args.auto_mode]
        print(f"{key} {label} for {container.id} ({result.path})")
    return 0


def _backlog_commit(args: argparse.Namespace) -> int:
    from aifactory.backlog import TaskEditError, commit_backlog
    from aifactory.config import ConfigError

    try:
        result = commit_backlog(_backlog_root(args.repo), args.message)
    except (ConfigError, TaskEditError) as exc:
        return _fail_from_exception(exc, args.json, "factory backlog commit")
    if args.json:
        return _emit_ok(result.to_json())
    if not result.committed:
        print("nothing to commit in the backlog")
        return 0
    short = (result.commit or "")[:12]
    pushed = ", pushed" if result.pushed else ""
    print(f"committed {len(result.paths)} backlog file(s) to {result.base} ({short}{pushed})")
    return 0


def _backlog_container_write(args: argparse.Namespace) -> int:
    from aifactory.backlog import (
        TaskEditError,
        add_container,
        container_detail_json,
        edit_container,
    )
    from aifactory.config import ConfigError

    command: str = args.backlog_command
    try:
        if command == "add":
            result = add_container(
                _backlog_root(args.repo),
                args.parent,
                args.container_id,
                args.title,
                body=args.body,
                backlog_dir=args.backlog_dir,
            )
        else:
            values: dict[str, object] = {}
            for key in ("workflow", "writes", "source", "target", "specs_dir", "docs_dir"):
                value = getattr(args, key)
                if value is not None:
                    values[key] = value
            if args.test is not None:
                values["test"] = args.test[0] if len(args.test) == 1 else args.test
            if args.auto_continue is not None:
                values["auto_continue"] = args.auto_continue == "on"
            result = edit_container(
                _backlog_root(args.repo), args.id, title=args.title, values=values, clear=args.clear
            )
    except (ConfigError, TaskEditError) as exc:
        return _fail_from_exception(exc, args.json, f"factory backlog {command}")
    container = result.container
    if args.json:
        data = {
            "action": result.action,
            "changed": result.changed,
            "path": result.path,
            "container": container_detail_json(result.backlog, container),
            "issues": [i.to_dict() for i in result.issues],
        }
        return _emit_ok(data, _problem_warnings(len(result.issues)))
    if not result.changed:
        print(f"unchanged {container.id}")
    else:
        verb = "added" if result.action == "add" else "updated"
        print(f"{verb} {container.level} {container.id} {result.path}")
    if result.issues:
        print(f"{len(result.issues)} problem(s), run 'factory backlog check'", file=sys.stderr)
    return 0


def _backlog(args: argparse.Namespace) -> int:
    if args.backlog_command is None:
        args.backlog_parser.print_help()
        return 0
    from aifactory.backlog import (
        backlog_to_json,
        check_backlog,
        counts,
        format_tree,
        issues_to_json,
        load_backlog,
    )
    from aifactory.config import ConfigError

    command: str = args.backlog_command
    if command == "sync":
        return _backlog_sync(args)
    if command in ("add", "edit"):
        return _backlog_container_write(args)
    if command == "auto-continue":
        return _backlog_auto_continue(args)
    if command == "auto-merge":
        return _backlog_auto_merge(args)
    if command == "commit":
        return _backlog_commit(args)
    try:
        backlog = load_backlog(_backlog_root(args.repo))
    except ConfigError as exc:
        return _fail_from_exception(exc, args.json, f"factory backlog {command}")
    issues = check_backlog(backlog)

    if command == "check":
        if args.json:
            data, warnings = strip_payload(issues_to_json(backlog, issues))
            data["issues"] = data.pop("errors", [])
            if not issues:
                return _emit_ok(data, warnings)
            return _emit_fail(
                "backlog_invalid",
                f"{len(issues)} problem(s) in the backlog",
                exit_code=1,
                data=data,
                issues=data["issues"],
                warnings=warnings,
            )
        if issues:
            for issue in issues:
                print(f"{issue.path}: {issue.code}: {issue.message}")
            print(f"{len(issues)} error(s)")
        else:
            summary = ", ".join(f"{n} {level}" for level, n in counts(backlog).items())
            print(f"OK: {summary}")
        return 1 if issues else 0

    missing_dir = any(i.code == "missing_backlog_dir" for i in issues)
    try:
        if args.json:
            payload = backlog_to_json(backlog, issues, status=args.status, project=args.project)
        else:
            lines = format_tree(backlog, status=args.status, project=args.project)
    except LookupError:
        message = f"unknown {backlog.settings.levels[0]} '{args.project}'"
        if args.json:
            return _emit_fail("unknown_project", message, exit_code=2, id=args.project)
        print(f"factory backlog list: {message}", file=sys.stderr)
        return 2
    if args.json:
        data, warnings = strip_payload(payload)
        if missing_dir:
            missing = next(i for i in issues if i.code == "missing_backlog_dir")
            return _emit_fail(
                "missing_backlog_dir",
                f"backlog directory '{missing.path}' not found",
                exit_code=1,
                data=data,
                path=missing.path,
                issues=[i.to_dict() for i in issues if i.code == "missing_backlog_dir"],
                warnings=warnings,
            )
        return _emit_ok(data, [*warnings, *_problem_warnings(len(issues))])
    if missing_dir:
        missing = next(i for i in issues if i.code == "missing_backlog_dir")
        print(f"error: backlog directory '{missing.path}' not found", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    if issues:
        print(f"{len(issues)} problem(s), run 'factory backlog check'", file=sys.stderr)
    return 0


TASK_EPILOG = """\
error codes (--json: error.code): with --json every command prints one envelope
{ok, data, error, warnings}; the full list of codes, formats and procedures is in
'factory --skill'. Exit 0 ok; 1 the command ran and found a problem (a failed run, a
write that would break the backlog, a PR that could not be opened); 2 the command could
not do its job (bad input, config, state, provider), nothing was changed.

task run: a failed run keeps its worktree and branch. After a successful run the branch
  is pushed and a pull request opened; when that fails the run stays succeeded and
  pr_error says why. --auto: after a run opens its PR the next ready task of the step,
  then of the project, starts. Without --auto only a task with auto_continue: true
  (inherited from index.md) is followed, by a task that has it too. auto_merge: true
  (inherited): a succeeded run with a review phase whose last review approved, a PR that
  merges cleanly and no red checks is approved and merged like 'task approve'; the chain
  continues only after that merge. Otherwise the PR stays open and auto_merge says why.
task publish: for the last succeeded run without a pull request (pr_failed) push the
  branch and open the PR as 'task run' does, or adopt the open PR the hosting has for the
  branch. No succeeded run (no_succeeded_run), a PR already known (pr_exists) or a run in
  progress (already_running): exit 2, nothing changed. Push or PR failed again: pr_failed,
  exit 1. A push failing on the network (RPC, HTTP2, hung up, timeout) is retried a few
  times; a rejected push is not.
task approve: on conflict run 'factory task resolve <task-id>'. No approve review is
  sent yet (temporary, D11).
task resolve: a run that fails leaves the branch as it was before the rebase.
task stop: the run is marked stopped; its worktree and branch stay (task clean).
  A paused run can be stopped too.
task pause: the phase in progress runs to its end (the run shows pausing), then the run
  waits as paused; its process stays alive and keeps its place among the parallel runs.
task resume: the paused run goes on with its next phase (a pending pause is dropped).
"""


def _add_task_commands(parser: argparse.ArgumentParser) -> None:
    parser.epilog = TASK_EPILOG
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.set_defaults(task_parser=parser)
    sub = parser.add_subparsers(dest="task_command", metavar="<subcommand>")
    add = sub.add_parser(
        "add",
        help="create a new task in a step",
        description="Create a new todo task file in the directory of STEP. The backlog is "
        "validated before writing; a change that would break it is rejected.",
    )
    add.add_argument("step", metavar="STEP", help="id of the step the task belongs to")
    add.add_argument("title", metavar="TITLE", help="task title")
    add.add_argument("--id", dest="task_id", metavar="ID", help="task id (default: next free)")
    add.add_argument("--slug", metavar="SLUG", help="file name slug (default: from the title)")
    add.add_argument("--workflow", metavar="NAME", help="workflow (default: inherited)")
    add.add_argument("--writes", nargs="*", metavar="PATH", help="paths the task writes")
    add.add_argument("--depends-on", nargs="+", default=[], metavar="ID", help="dependencies")
    add.add_argument("--related", nargs="+", metavar="ID", help="related tasks")
    add.add_argument("--body", default="", metavar="TEXT", help="text of '## Zadání'")
    add.add_argument(
        "--test",
        nargs="+",
        metavar="ARG",
        help="test command of the task (argv) instead of the inherited test_command",
    )

    edit = sub.add_parser(
        "edit",
        help="change header fields of a task",
        description="Change title, status (todo|cancelled), workflow, writes or auto_merge "
        "of a task.",
    )
    edit.add_argument("task_id", metavar="ID", help="task id")
    edit.add_argument("--title", metavar="TEXT", help="new title")
    edit.add_argument("--status", metavar="STATUS", help="todo or cancelled")
    edit.add_argument("--workflow", metavar="NAME", help="set the workflow")
    edit.add_argument(
        "--clear-workflow", action="store_true", help="remove the workflow (inherit it)"
    )
    edit.add_argument("--writes", nargs="*", metavar="PATH", help="set writes (none = [])")
    edit.add_argument("--clear-writes", action="store_true", help="remove writes (inherit)")
    edit.add_argument(
        "--auto-merge",
        choices=("on", "off", "inherit"),
        help="set auto_merge of the task (off, e.g. when it changes the guard or permissions) "
        "or remove it (inherit)",
    )

    link = sub.add_parser(
        "link",
        help="add or remove depends_on / related references",
        description="Add (or with --remove drop) depends_on and related references of a task.",
    )
    link.add_argument("task_id", metavar="ID", help="task id")
    link.add_argument("--depends-on", nargs="+", default=[], metavar="ID", help="dependencies")
    link.add_argument("--related", nargs="+", default=[], metavar="ID", help="related tasks")
    link.add_argument("--remove", action="store_true", help="remove the references instead")

    show = sub.add_parser(
        "show", help="print a task and its derived state", description="Print one task."
    )
    show.add_argument("task_id", metavar="ID", help="task id")

    list_ = sub.add_parser(
        "list",
        help="list tasks with derived states",
        description="List tasks with their derived state (ready/blocked/done/cancelled).",
    )
    list_.add_argument("--status", metavar="STATE", help="todo|done|cancelled|ready|blocked")
    list_.add_argument("--project", metavar="ID", help="only this project (id or directory)")
    list_.add_argument("--step", metavar="ID", help="only this step")

    run = sub.add_parser(
        "run",
        help="run a task in its own worktree and branch",
        description="Run a task from the backlog in base in a new worktree "
        "<worktrees_dir>/<run-id> on a new branch factory/<task-id>-<n>. Agents may change "
        "only the task's writes and its spec/doc files inside the worktree; anything else, "
        "including any change in the main checkout, is rolled back and fails the phase. "
        "With --auto a run that opened its PR is followed by the next ready task "
        "(auto-continue). Without it auto_continue: true (from the index.md of the step or "
        "project) must hold for both the finished and the next task. "
        "With auto_merge: true a reviewed run's PR is merged first when it may be "
        "(see 'factory backlog auto-merge --help').",
    )
    run.add_argument("task_id", metavar="ID", help="task id")
    run.add_argument("--note", metavar="TEXT", help="a note for the agents, appended to the task")
    run.add_argument(
        "--force",
        action="store_true",
        help="run even if depends_on are not done in base; never overrides a running task",
    )
    run.add_argument(
        "--auto",
        action="store_true",
        help="after a successful run (PR opened) start the next ready task of the step, then "
        "of the project, whatever its auto_continue (auto-continue); a failure stops the chain. "
        "The kanban's queue order goes first and tasks excluded in the kanban are never "
        "started by the chain",
    )
    from aifactory.harness.override import THINKING_LEVELS

    run.add_argument(
        "--harness",
        metavar="NAME",
        help="run every agent of the roster on this harness for this run only (nothing is "
        "written); a switch without --model takes the harness's preset model. Step overrides "
        "of the workflow still win, so one workflow can mix harnesses. With --auto only the "
        "first run of the chain gets it",
    )
    run.add_argument(
        "--model", metavar="NAME", help="model of every agent for this run only (like --harness)"
    )
    run.add_argument(
        "--thinking",
        metavar="LEVEL",
        choices=THINKING_LEVELS,
        help="thinking level of every agent for this run only (like --harness)",
    )
    # internal: one run of a parallel auto-continue chain (run/members.py), never a chain
    run.add_argument("--member", action="store_true", help=argparse.SUPPRESS)
    # internal: who started a member run (a chain: auto-continue)
    run.add_argument(
        "--started-by",
        choices=("manual", "auto-continue", "auto-resolve"),
        default="manual",
        help=argparse.SUPPRESS,
    )

    approve = sub.add_parser(
        "approve",
        help="merge the task's pull request after a commit with status: done",
        description="Add a commit with status: done and a line in '## Běhy' to the task's "
        "pull request, merge it, bring base up to date with the remote and remove the "
        "branch's worktrees. Azure sends an approval vote after the final push and before "
        "merge; local and GitHub do not send a self-approval review.",
    )
    approve.add_argument("task_id", metavar="ID", help="task id")

    return_ = sub.add_parser(
        "return",
        help="send the task back to the agents with a note",
        description="Start a new run on the same branch with the note in the prompt; the "
        "pull request is updated.",
    )
    return_.add_argument("task_id", metavar="ID", help="task id")
    return_.add_argument(
        "--note", required=True, metavar="TEXT", help="what to change, appended to the task"
    )

    resolve = sub.add_parser(
        "resolve",
        help="rebase the task's pull request onto base and resolve conflicts",
        description="Start a new run on the branch of the task's pull request: rebase it onto "
        "the current base; on a conflict an agent changes only the conflicted files. Then the "
        "suite runs, the branch is force-pushed (with a lease) and the pull request updated. "
        "When the run fails, the branch stays as it was before the rebase.",
    )
    resolve.add_argument("task_id", metavar="ID", help="task id")

    publish = sub.add_parser(
        "publish",
        help="push the branch of the last succeeded run and open its pull request",
        description="For the task's last succeeded run that has no pull request (its push or "
        "PR failed at the end of 'task run'): push the branch and open the pull request with "
        "the body from the run, recorded like after 'task run'. An open PR the hosting already "
        "has for the branch is adopted and its body updated. Without a succeeded run, with a "
        "known PR or while a run is in progress it fails with exit 2 and changes nothing.",
    )
    publish.add_argument("task_id", metavar="ID", help="task id")

    clean = sub.add_parser(
        "clean",
        help="remove worktrees that are no longer needed",
        description="Remove worktrees of runs whose PR is merged or closed, and of abandoned "
        "runs (a newer run of the task exists).",
    )

    stop = sub.add_parser(
        "stop",
        help="stop the running run of a task",
        description="Send SIGTERM to the coding agents of the task's running run and then to "
        "the run's process (SIGKILL after a timeout). The run is marked stopped; its worktree "
        "and branch stay (factory task clean removes them).",
    )
    stop.add_argument("task_id", metavar="ID", help="task id")
    stop.add_argument(
        "--run", metavar="RUN_ID", help="stop exactly this run (it must belong to the task)"
    )

    pause = sub.add_parser(
        "pause",
        help="pause the running run of a task before its next phase",
        description="Ask the task's running run to pause. The phase in progress (an agent, "
        "a test) runs to its end, then the run waits as paused before the next phase; its "
        "process stays alive. factory task resume lets it go on, factory task stop stops it.",
    )
    pause.add_argument("task_id", metavar="ID", help="task id")
    pause.add_argument(
        "--run", metavar="RUN_ID", help="pause exactly this run (it must belong to the task)"
    )
    resume = sub.add_parser(
        "resume",
        help="let a paused run of a task go on with its next phase",
        description="Resume the task's paused run: it goes on with its next phase in the same "
        "worktree and branch. A pause that is still pending (pausing) is dropped.",
    )
    resume.add_argument("task_id", metavar="ID", help="task id")
    resume.add_argument(
        "--run", metavar="RUN_ID", help="resume exactly this run (it must belong to the task)"
    )

    for child in (
        add,
        edit,
        link,
        show,
        list_,
        run,
        approve,
        return_,
        resolve,
        publish,
        clean,
        stop,
        pause,
        resume,
    ):
        child.add_argument("--json", action="store_true", help="print machine-readable JSON")
        child.add_argument(
            "--repo",
            metavar="PATH",
            help="repository root with .factory/config.yaml (default: the current git repo)",
        )


def _dep_label(backlog: Backlog, dep: str) -> str:
    from aifactory.backlog import Task, derived_state, is_done, progress

    node = backlog.by_id.get(dep)
    if node is None:
        return f"{dep} (unknown)"
    if isinstance(node, Task):
        return f"{dep} ({derived_state(backlog, node)})"
    if is_done(node):
        return f"{dep} (done)"
    done, total = progress(node)
    return f"{dep} ({done}/{total})"


def _task_show(args: argparse.Namespace, root: Path) -> int:
    from aifactory.backlog import (
        blocks,
        check_backlog,
        derived_state,
        effective_workflow,
        effective_writes,
        find_task,
        load_for_edit,
        task_to_json,
        waits_for,
    )
    from aifactory.run import task_prs_for, task_runs_for

    backlog = load_for_edit(root)
    issues = check_backlog(backlog)
    task = find_task(backlog, args.task_id, issues)
    reverse = blocks(backlog)
    own_issues = [i.to_dict() for i in issues if i.path == task.path]
    runs = task_runs_for(root, task.id)
    prs = task_prs_for(root, task.id)
    if args.json:
        data = {
            "task": task_to_json(backlog, task, reverse),
            "body": task.body,
            "issues": own_issues,
            "runs": [r.to_json() for r in runs],
            "prs": [p.to_json() for p in prs],
        }
        return _emit_ok(data, _problem_warnings(len(own_issues)))

    def joined(values: list[str]) -> str:
        return ", ".join(values) or "-"

    workflow = effective_workflow(task)
    rows = [
        ("id", task.id),
        ("title", task.title),
        ("path", task.path),
        ("status", task.status),
        ("state", derived_state(backlog, task)),
        ("workflow", "-" if workflow is None else str(workflow)),
        ("depends", joined([_dep_label(backlog, d) for d in task.depends_on])),
        ("waits for", (waits_for(backlog, task) if task.status == "todo" else "") or "-"),
        ("related", joined(task.related)),
        ("writes", joined(effective_writes(task))),
        ("blocks", joined(reverse.get(task.id, []))),
    ]
    for name, value in rows:
        print(f"{name:<9} {value}")
    print()
    print(task.body.strip("\n"))
    print()
    if runs:
        print("runs:")
        for r in runs:
            head = r.head_sha[:7] if r.head_sha else "-"
            print(f"  {r.started_at}  {r.run_id}  {r.shown_state:<9}  {r.branch}  {head}")
    else:
        print("no runs")
    if prs:
        print("prs:")
        for p in prs:
            print(f"  {p.state:<6}  {p.url}  {p.branch}")
    for issue in own_issues:
        print(f"{issue['path']}: {issue['code']}: {issue['message']}", file=sys.stderr)
    return 0


def _task_list(args: argparse.Namespace, root: Path) -> int:
    from aifactory.backlog import (
        STATUS_FILTERS,
        TaskEditError,
        blocks,
        check_backlog,
        derived_state,
        iter_containers,
        iter_tasks,
        load_for_edit,
        select_projects,
        task_matches,
        task_to_json,
        waits_for,
    )
    from aifactory.backlog.derived import descendant_tasks

    status: str | None = args.status
    if status is not None and status not in STATUS_FILTERS:
        raise TaskEditError(
            "invalid_status",
            f"invalid status filter '{status}', allowed: {', '.join(STATUS_FILTERS)}",
        )
    backlog = load_for_edit(root)
    issues = check_backlog(backlog)
    tasks = list(iter_tasks(backlog))
    if args.project is not None:
        try:
            projects = select_projects(backlog, args.project)
        except LookupError:
            level = backlog.settings.levels[0]
            raise TaskEditError(
                "unknown_project", f"unknown {level} '{args.project}'", id=args.project
            ) from None
        allowed = {t.path for p in projects for t in descendant_tasks(p)}
        tasks = [t for t in tasks if t.path in allowed]
    if args.step is not None:
        level = backlog.settings.levels[-2]
        steps = [
            c for c in iter_containers(backlog.containers) if c.id == args.step and c.level == level
        ]
        if not steps:
            raise TaskEditError("unknown_step", f"unknown {level} '{args.step}'", id=args.step)
        allowed = {t.path for s in steps for t in descendant_tasks(s)}
        tasks = [t for t in tasks if t.path in allowed]
    tasks = [t for t in tasks if task_matches(backlog, t, status)]
    if args.json:
        reverse = blocks(backlog)
        data = {
            "filters": {"status": status, "project": args.project, "step": args.step},
            "tasks": [task_to_json(backlog, t, reverse) for t in tasks],
            "issues": [i.to_dict() for i in issues],
        }
        return _emit_ok(data, _problem_warnings(len(issues)))
    width = max((len(t.id) for t in tasks), default=0)
    for task in tasks:
        state = derived_state(backlog, task)
        line = f"{task.id:<{width}} {state:<9} {task.title}"
        if state == "blocked":
            line += f"  (waits for: {waits_for(backlog, task)})"
        print(line)
    if issues:
        print(f"{len(issues)} problem(s), run 'factory backlog check'", file=sys.stderr)
    return 0


def _task_write(args: argparse.Namespace, root: Path) -> int:
    from aifactory.backlog import add_task, blocks, edit_task, link_task, task_to_json

    command: str = args.task_command
    if command == "add":
        result = add_task(
            root,
            args.step,
            args.title,
            task_id=args.task_id,
            slug=args.slug,
            workflow=args.workflow,
            writes=args.writes,
            depends_on=args.depends_on,
            related=args.related,
            body=args.body,
            test=args.test,
        )
    elif command == "edit":
        result = edit_task(
            root,
            args.task_id,
            title=args.title,
            status=args.status,
            workflow=args.workflow,
            clear_workflow=args.clear_workflow,
            writes=args.writes,
            clear_writes=args.clear_writes,
            auto_merge={"on": True, "off": False}.get(args.auto_merge or ""),
            clear_auto_merge=args.auto_merge == "inherit",
        )
    else:
        result = link_task(
            root,
            args.task_id,
            depends_on=args.depends_on,
            related=args.related,
            remove=args.remove,
        )
    if args.json:
        data = {
            "action": result.action,
            "changed": result.changed,
            "path": result.path,
            "task": task_to_json(result.backlog, result.task, blocks(result.backlog)),
            "issues": [i.to_dict() for i in result.issues],
        }
        return _emit_ok(data, _problem_warnings(len(result.issues)))
    if not result.changed:
        print(f"unchanged {result.task.id}")
    else:
        verb = "added" if result.action == "add" else "updated"
        print(f"{verb} {result.task.id} {result.path}")
    if result.issues:
        print(f"{len(result.issues)} problem(s), run 'factory backlog check'", file=sys.stderr)
    return 0


def _run_json(result: TaskRunResult) -> dict[str, Any]:
    return {
        "run": result.run.to_json(),
        "pr": result.pr.to_json() if result.pr is not None else None,
        "pr_error": result.pr_error,
        "auto_merge": result.auto_merge.to_json() if result.auto_merge is not None else None,
        "resolve_run": result.resolve_run.run.to_json() if result.resolve_run is not None else None,
    }


def _emit_runs(
    data: dict[str, Any], results: Sequence[TaskRunResult], warnings: Iterable[str]
) -> int:
    """The envelope of a run: ``run_failed``/``pr_failed`` from the first failing run."""
    failed = next((r for r in results if not r.ok), None)
    if failed is None:
        return _emit_ok(data, warnings)
    from aifactory.run.store import SUCCEEDED

    if failed.run.state == SUCCEEDED and failed.pr_error is not None:
        # the run itself succeeded; only the push or the pull request failed
        return _emit_fail("pr_failed", failed.pr_error, exit_code=1, data=data, warnings=warnings)
    message = failed.run.error or f"run {failed.run.run_id} {failed.run.state}"
    return _emit_fail(
        "run_failed", message, exit_code=1, data=data, id=failed.run.task_id, warnings=warnings
    )


def _print_run(command: str, result: TaskRunResult) -> None:
    row = result.run
    print(f"run {row.run_id} {row.state}: branch {row.branch}, worktree {row.worktree}")
    if result.pr is not None:
        print(f"pr {result.pr.url}")
    if row.error:
        print(f"factory task {command}: {row.error}", file=sys.stderr)
    if result.pr_error:
        print(f"factory task {command}: pr: {result.pr_error}", file=sys.stderr)
    merge = result.auto_merge
    if merge is not None and merge.merged:
        sha = f" ({merge.merge_sha[:7]})" if merge.merge_sha else ""
        base = result.pr.base if result.pr is not None else "base"
        print(f"auto-merge: merged {merge.pr_url} into {base}{sha}")
    elif merge is not None:
        print(
            f"auto-merge: not merged ({merge.code}): {merge.reason}; the PR stays open, "
            f"approve it with factory task approve {row.task_id}"
        )


def _run_output(args: argparse.Namespace, start: Callable[[], TaskRunResult]) -> int:
    """Start a run with `start` and print its result (``task return``, ``resolve``)."""
    command: str = args.task_command
    if args.json:
        # The engine narrates on stdout; with --json stdout carries only the result.
        with contextlib.redirect_stdout(sys.stderr):
            result = start()
        return _emit_runs(_run_json(result), [result], result.warnings)
    result = start()
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    _print_run(command, result)
    return 0 if result.ok else 1


def _member_run(
    root: Path,
    task_id: str,
    note: str | None,
    force: bool,
    code: CodeRunner | None = None,
    started_by: str = "manual",
    agents_override: dict[str, str] | None = None,
) -> TaskRunResult:
    """One run of a parallel chain: the task, then its auto-merge under the merge lock.

    A PR in conflict is resolved once (``resolve_and_merge``) outside the lock and merged
    under it, as the sequential chain does; the resolve run is ``result.resolve_run``.
    `code` reaches the resolve run only (tests).
    """
    import tempfile

    from aifactory.backlog import Task
    from aifactory.run import auto_merge_enabled, run_task
    from aifactory.run.queue import _base_backlog
    from aifactory.run.store import TaskRunStore

    result = run_task(
        root,
        task_id,
        note=note,
        force=force,
        started_by=started_by,
        agents_override=agents_override,
    )
    if not result.ok or result.pr is None:
        return result
    with tempfile.TemporaryDirectory(prefix="factory-member-") as tmp:
        task = _base_backlog(root, Path(tmp)).by_id.get(task_id)
        if not isinstance(task, Task) or not auto_merge_enabled(task):
            return result
        from aifactory.review.automerge import resolve_and_merge, try_auto_merge

        store = TaskRunStore(result.trace_db)
        try:
            with store.merge_lock():
                result.auto_merge = try_auto_merge(root, result, task)
            if not result.auto_merge.merged and result.auto_merge.code == "conflict":
                result.resolve_run, result.auto_merge = resolve_and_merge(
                    root, result, task, code=code, merge_lock=store.merge_lock
                )
        finally:
            store.close()
    return result


def _agents_override(args: argparse.Namespace) -> dict[str, str] | None:
    """``--harness``/``--model``/``--thinking`` of ``task run``; None when none is given."""
    values = {
        key: value
        for key in ("harness", "model", "thinking")
        if (value := getattr(args, key, None))
    }
    return values or None


def _task_run(args: argparse.Namespace, root: Path) -> int:
    from aifactory.run import STOP_EXHAUSTED, STOP_NOT_MERGED, run_chain

    if getattr(args, "member", False):

        def member() -> TaskRunResult:
            return _member_run(
                root,
                args.task_id,
                args.note,
                args.force,
                started_by=args.started_by,
                agents_override=_agents_override(args),
            )

        return _run_output(args, member)

    def start() -> ChainResult:
        return run_chain(
            root,
            args.task_id,
            note=args.note,
            force=args.force,
            auto=args.auto,
            agents_override=_agents_override(args),
        )

    if args.json:
        with contextlib.redirect_stdout(sys.stderr):
            chain = start()
        chain_json = chain.to_json()
        data = _run_json(chain.runs[0])
        keys = ("runs", "stop", "waiting", "max_parallel_runs", "exclusive", "chain_id")
        data["chain"] = {k: chain_json[k] for k in keys}
        return _emit_runs(data, chain.runs, chain.runs[0].warnings)
    chain = start()
    for warning in chain.runs[0].warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if chain.max_parallel > 1:
        print(f"auto-continue: up to {chain.max_parallel} parallel runs")
    for result in chain.runs:
        _print_run("run", result)
    for task_id in chain.exclusive:
        print(f"exclusive: {task_id} ran alone (wide writes)")
    if len(chain.runs) > 1 or chain.stop in (STOP_EXHAUSTED, STOP_NOT_MERGED):
        print(f"auto-continue: stopped ({chain.stop})")
        for skip in chain.waiting:
            print(f"waiting: {skip.task_id} {skip.reason}: {skip.detail}")
        if chain.stop == STOP_EXHAUSTED and not chain.waiting:
            print("auto-continue: nothing left to run")
    return 0 if chain.ok else 1


def _task_return(args: argparse.Namespace, root: Path) -> int:
    from aifactory.review import return_task

    return _run_output(args, lambda: return_task(root, args.task_id, args.note))


def _task_resolve(args: argparse.Namespace, root: Path) -> int:
    from aifactory.review import resolve_task

    return _run_output(args, lambda: resolve_task(root, args.task_id))


def _task_approve(args: argparse.Namespace, root: Path) -> int:
    from aifactory.review import approve_task

    result = approve_task(root, args.task_id)
    if args.json:
        data, warnings = strip_payload(result.to_json())
        return _emit_ok(data, warnings)
    sha = result.merge_sha[:7] if result.merge_sha else "?"
    print(f"merged {result.pr.url} into {result.pr.base} ({sha})")
    print("note: approve review sent" if result.reviewed else "note: approve review not sent")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _task_publish(args: argparse.Namespace, root: Path) -> int:
    from aifactory.review import publish_task

    result = publish_task(root, args.task_id)
    if args.json:
        data = result.to_json()
        if result.pr_error is not None:
            return _emit_fail("pr_failed", result.pr_error, exit_code=1, data=data)
        return _emit_ok(data)
    row = result.run
    if result.pr_error is not None:
        print(f"factory task publish: pr: {result.pr_error}", file=sys.stderr)
        return 1
    assert result.pr is not None
    print(f"run {row.run_id}: branch {row.branch} pushed")
    print(f"pr {result.pr.url}")
    return 0


def _task_clean(args: argparse.Namespace, root: Path) -> int:
    from aifactory.review import clean_worktrees

    result = clean_worktrees(root)
    if args.json:
        data, warnings = strip_payload(result.to_json())
        return _emit_ok(data, warnings)
    for item in result.removed:
        print(f"removed {item['worktree']} ({item['reason']}, {item['task_id']})")
    print(f"{len(result.removed)} worktree(s) removed")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _task_stop(args: argparse.Namespace, root: Path) -> int:
    from aifactory.run import TaskRunError, task_runs_for
    from aifactory.run import stop as run_stop

    task_id: str = args.task_id
    run_id: str | None = args.run
    if run_id is None:
        row = run_stop.running_run(root, task_id)
        if row is None:
            raise TaskRunError("run_not_running", f"task {task_id} has no running run")
        run_id = row.run_id
    elif run_id not in {r.run_id for r in task_runs_for(root, task_id)}:
        raise TaskRunError("invalid_value", f"run {run_id} is not a run of task {task_id}")
    result = run_stop.stop_run(root, run_id)
    if args.json:
        return _emit_ok(result.to_json())
    print(f"stopped run {run_id} of {task_id}")
    return 0


def _task_pause(args: argparse.Namespace, root: Path, *, resume: bool) -> int:
    from aifactory.run import TaskRunError, pause_run, resume_run, task_runs_for
    from aifactory.run import stop as run_stop

    task_id: str = args.task_id
    run_id: str | None = args.run
    if run_id is None:
        row = run_stop.running_run(root, task_id)
        if row is None:
            raise TaskRunError("run_not_running", f"task {task_id} has no running run")
        run_id = row.run_id
    elif run_id not in {r.run_id for r in task_runs_for(root, task_id)}:
        raise TaskRunError("invalid_value", f"run {run_id} is not a run of task {task_id}")
    result = resume_run(root, run_id) if resume else pause_run(root, run_id)
    if args.json:
        return _emit_ok({"run": result.to_json()})
    if resume:
        print(f"resumed run {run_id} of {task_id}")
    else:
        print(f"pausing run {run_id} of {task_id}: it pauses when the current phase ends")
    return 0


def _task(args: argparse.Namespace) -> int:
    if args.task_command is None:
        args.task_parser.print_help()
        return 0
    from aifactory.backlog import TaskEditError
    from aifactory.config import ConfigError
    from aifactory.review import ReviewError
    from aifactory.run import TaskRunError

    command: str = args.task_command
    root = _backlog_root(args.repo)
    try:
        if command == "run":
            return _task_run(args, root)
        if command == "approve":
            return _task_approve(args, root)
        if command == "return":
            return _task_return(args, root)
        if command == "resolve":
            return _task_resolve(args, root)
        if command == "publish":
            return _task_publish(args, root)
        if command == "clean":
            return _task_clean(args, root)
        if command == "stop":
            return _task_stop(args, root)
        if command in ("pause", "resume"):
            return _task_pause(args, root, resume=command == "resume")
        if command == "show":
            return _task_show(args, root)
        if command == "list":
            return _task_list(args, root)
        return _task_write(args, root)
    except (ConfigError, TaskEditError, TaskRunError, ReviewError) as exc:
        return _fail_from_exception(exc, args.json, f"factory task {command}")


def _add_workflow_commands(parser: argparse.ArgumentParser) -> None:
    parser.set_defaults(workflow_parser=parser)
    sub = parser.add_subparsers(dest="workflow_command", metavar="<subcommand>")
    check = sub.add_parser(
        "check",
        help="validate a workflow against the role registry and the agents",
        description="Validate a workflow file against the role registry (.factory/roles.yaml "
        "or the packaged defaults) and the agent roster (.factory/agents.yaml) of the working "
        "tree. Nothing runs. Exits 1 when the workflow has problems, 2 when the registry or "
        "roster cannot be loaded.",
    )
    check.add_argument("file", type=Path, metavar="FILE", help="workflow YAML file")
    check.add_argument("--json", action="store_true", help="print machine-readable JSON")
    check.add_argument(
        "--roles", type=Path, metavar="PATH", help="role registry instead of .factory/roles.yaml"
    )
    check.add_argument(
        "--agents", type=Path, metavar="PATH", help="agent roster instead of .factory/agents.yaml"
    )


@dataclass
class _WorkflowSources:
    roles: RoleRegistry
    agents: SSSFConfig | None
    roles_source: str
    agents_source: str | None


def _workflow_sources(args: argparse.Namespace) -> _WorkflowSources:
    """The registry and roster to check against: flags first, then the working tree."""
    from aifactory.config import ConfigError, load_worktree_config, repo_root
    from aifactory.config.loader import AGENTS_FILE, ROLES_FILE
    from aifactory.engine.role_registry import load_roles
    from aifactory.harness.config import load_config

    root: Path | None
    try:
        root = repo_root(Path.cwd())
    except ConfigError:
        root = None
    if (
        root is not None
        and (root / ".factory" / "config.yaml").is_file()
        and args.roles is None
        and args.agents is None
    ):
        cfg = load_worktree_config(root)
        has_roles = (root / ROLES_FILE).is_file()
        return _WorkflowSources(
            roles=cfg.roles,
            agents=cfg.agents,
            roles_source=ROLES_FILE if has_roles else "packaged defaults",
            agents_source=AGENTS_FILE,
        )
    roles = load_roles(args.roles) if args.roles is not None else load_roles()
    agents = load_config(args.agents) if args.agents is not None else None
    return _WorkflowSources(
        roles=roles,
        agents=agents,
        roles_source=str(args.roles) if args.roles is not None else "packaged defaults",
        agents_source=str(args.agents) if args.agents is not None else None,
    )


def _workflow_check(args: argparse.Namespace) -> int:
    from aifactory.config import ConfigError
    from aifactory.engine.role_registry import RolesError
    from aifactory.harness.config import HarnessConfigError
    from aifactory.workflow import check_workflow

    try:
        sources = _workflow_sources(args)
    except (ConfigError, RolesError, HarnessConfigError, OSError) as exc:
        return _fail_from_exception(exc, args.json, "factory workflow check")
    result = check_workflow(
        args.file,
        sources.roles,
        sources.agents,
        roles_source=sources.roles_source,
        agents_source=sources.agents_source,
    )
    if args.json:
        data, warnings = strip_payload(result.to_json())
        data["issues"] = data.pop("errors", [])
        if result.ok:
            return _emit_ok(data, warnings)
        return _emit_fail(
            "workflow_invalid",
            f"{len(result.issues)} problem(s) in {args.file}",
            exit_code=1,
            data=data,
            path=str(args.file),
            issues=data["issues"],
            warnings=warnings,
        )
    if result.ok:
        print(f"OK: {result.workflow} ({len(result.outline)} steps)")
    else:
        for issue in result.issues:
            print(f"{args.file}:{issue.path}: {issue.code}: {issue.message}")
        print(f"{len(result.issues)} error(s)")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0 if result.ok else 1


def _workflow(args: argparse.Namespace) -> int:
    if args.workflow_command is None:
        args.workflow_parser.print_help()
        return 0
    return _workflow_check(args)


def main(argv: Sequence[str] | None = None) -> int:
    if argv is None:
        oscompat.utf8_stdio()
    load_env_file()
    argv_list = list(sys.argv[1:] if argv is None else argv)
    want_json = "--json" in argv_list
    parser = build_parser()
    try:
        args = parser.parse_args(argv_list)
    except _UsageError as exc:
        if want_json:
            return _emit_fail("usage_error", f"{exc.parser.prog}: {exc.message}", exit_code=2)
        exc.parser.print_usage(sys.stderr)
        print(f"{exc.parser.prog}: error: {exc.message}", file=sys.stderr)
        raise SystemExit(2) from None
    if args.skill:
        from aifactory.skill import render_skill, skill_json

        if args.root_json:
            return _emit_ok(skill_json(parser))
        print(render_skill(parser), end="")
        return 0
    if args.root_json:
        return _emit_fail(
            "usage_error", "factory: --json before the command needs --skill", exit_code=2
        )
    if not getattr(args, "json", False):
        return _dispatch(parser, args)
    try:
        return _dispatch(parser, args)
    except Exception as exc:  # --json promises an envelope even for a bug
        traceback.print_exc(file=sys.stderr)
        return _emit_fail("internal_error", f"{type(exc).__name__}: {exc}", exit_code=2)


def _add_obs_command(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo",
        metavar="PATH",
        help="register this repository and open it (any folder inside it): its backlog, "
        "or its Factory tab when the factory is not ready",
    )
    parser.add_argument(
        "--port",
        metavar="N",
        type=int,
        help="port (default: port in the registry dashboard.yaml, else 4700)",
    )
    parser.add_argument(
        "--host",
        metavar="ADDR",
        help="address to listen on (default: $HAIFA_DASH_HOST, else 127.0.0.1); "
        "0.0.0.0 serves the whole network, with no login",
    )
    parser.add_argument("--no-open", action="store_true", help="do not open the browser")
    parser.add_argument(
        "--json", action="store_true", help="print the URL as a JSON envelope before serving"
    )


def _obs(args: argparse.Namespace) -> int:
    import webbrowser

    from aifactory.config import ConfigError, load_local_checked
    from aifactory.home import haifa_home
    from aifactory.web import app as web_app
    from aifactory.web import server as web_server
    from aifactory.web.backlog import UsageError
    from aifactory.web.registry import Registry, RepoEntry, RepoError
    from aifactory.web.repos import register_repo, repo_status

    label = "factory obs"
    if args.port is not None and not 1 <= args.port <= 65535:
        message = f"--port must be between 1 and 65535, got {args.port}"
        if args.json:
            return _emit_fail("invalid_value", message, exit_code=2)
        print(f"{label}: {message}", file=sys.stderr)
        return 2
    home = haifa_home()
    registry = Registry(home)
    state, snapshot_warnings = registry.snapshot()
    warnings: list[str] = list(snapshot_warnings)
    port: int = args.port if args.port is not None else state.port
    entry: RepoEntry | None = None
    fragment = ""
    if args.repo:
        raw = str(Path(args.repo).expanduser().absolute())
        try:
            entry, _created, add_warnings = register_repo(registry, raw)
        except RepoError as exc:
            if args.json:
                return _emit_fail(exc.code, exc.message, exit_code=2, data=exc.data or None)
            print(f"{label}: {exc.code}: {exc.message}", file=sys.stderr)
            return 2
        except UsageError as exc:
            if args.json:
                return _emit_fail("usage_error", exc.message, exit_code=2)
            print(f"{label}: {exc.message}", file=sys.stderr)
            return 2
        warnings.extend(w for w in add_warnings if w not in warnings)
        try:
            _local, local_warnings = load_local_checked(Path(entry.path))
        except (ConfigError, OSError):
            local_warnings = []  # factory check reports a broken local.yaml
        warnings.extend(local_warnings)
        # a repo that is not ready (no factory, uncommitted config, ...) opens its Factory tab
        screen = "backlog" if repo_status(entry)["status"] == "ok" else "factory"
        fragment = f"#/r/{entry.id}/{screen}"

    host = web_server.resolve_host(args.host)
    url = web_server.dashboard_url(port, host)
    restarted = os.environ.pop(web_server.RESTART_ENV, None) is not None
    data: dict[str, Any] = {
        "url": url,
        "host": host,
        "port": port,
        "repo": entry.path if entry is not None else None,
        "version": __version__,
        "repo_id": entry.id if entry is not None else None,
        "home": str(home),
        "reused": False,
    }
    try:
        web_server.check_port(port, wait=10.0 if restarted else 0.0, host=host)
    except web_server.PortInUseError:
        if not restarted and web_server.probe_dashboard(port, host):
            if not args.no_open:
                webbrowser.open(url + fragment)
            data["reused"] = True
            if args.json:
                return _emit_ok(data, warnings)
            print(f"HAIFA dashboard už běží: {url}{fragment}")
            for warning in warnings:
                print(f"warning: {warning}", file=sys.stderr)
            return 0
        message = f"port {port} on {host} is already in use; pick another with --port"
        if args.json:
            return _emit_fail("port_in_use", message, exit_code=2, warnings=warnings)
        print(f"{label}: {message}", file=sys.stderr)
        return 2
    app = web_app.create_multi_app(
        home=home, port=port, allowed_hosts=web_server.allowed_hosts(host), background_checks=True
    )
    if args.json:
        _emit_ok(data, warnings)
    else:
        where = "" if host in web_server.LOOPBACK else f", naslouchá na {host}:{port}"
        print(f"HAIFA dashboard: {url}{fragment}  (Ctrl+C ukončí{where})")
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)
    sys.stdout.flush()
    try:
        with contextlib.suppress(KeyboardInterrupt):
            web_server.serve(
                app,
                port,
                open_browser=not args.no_open and not restarted,
                host=host,
                open_path=fragment,
            )
    finally:
        left = len(app.state.launcher.running())
        message = f"Běhy spuštěné z dashboardu, které pokračují: {left}"
        if left:
            message += " (zastaví je factory task stop ID)"
        print(message, file=sys.stderr if args.json else sys.stdout)
    return 0


def _add_upgrade_command(parser: argparse.ArgumentParser) -> None:
    parser.description = (
        "Install a newer HAIFA from a bundle haifa-<version>.zip (a path, or an https or "
        "file URL; other schemes are invalid_url). The bundle is unpacked into a temporary "
        "directory, SHA256SUMS is verified (checksum_mismatch), the version is read from the "
        "wheel and compared with the installed one (up_to_date when not newer; a broken zip "
        "or a missing file is bundle_invalid). Then uv tool install --force <wheel> "
        "--constraints constraints.txt runs in the bundle (upgrade_failed, uv_missing). An "
        "editable install is refused (editable_install): update it with git pull. Restart a "
        "running dashboard afterwards."
    )
    parser.add_argument("bundle", metavar="BUNDLE", help="path or https/file URL of the zip")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="check the bundle and show the versions and the command; install nothing",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")


def _upgrade(args: argparse.Namespace) -> int:
    from aifactory.upgrade import RESTART_HINT, UpgradeError, run_upgrade

    try:
        result = run_upgrade(args.bundle, dry_run=args.dry_run)
    except UpgradeError as exc:
        if args.json:
            return _emit_fail(exc.code, exc.message, exit_code=exc.exit_code, data=exc.data)
        print(f"factory upgrade: {exc.code}: {exc.message}", file=sys.stderr)
        if exc.code == "upgrade_failed" and exc.data and exc.data.get("stderr"):
            print(exc.data["stderr"], end="", file=sys.stderr)
        return exc.exit_code
    if args.json:
        data = result.to_json()
        if result.installed:
            data["next"] = RESTART_HINT
        return _emit_ok(data, result.warnings)
    print(f"current  {result.current_version}")
    print(f"target   {result.target_version}")
    print(f"library  needs {result.min_factory_version or '-'}")
    print(f"command  {' '.join(result.command)}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if result.dry_run:
        print("dry run: nothing installed")
    else:
        print(f"installed HAIFA {result.target_version}; {RESTART_HINT}")
    return 0


def _dispatch(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    command: str | None = args.command
    if command is None:
        parser.print_help()
        print()
        print("První spuštění: factory check")
        return 0
    if command == "check":
        return _check(args)
    if command == "init":
        return _init(args)
    if command == "onboard":
        return _onboard(args)
    if command == "adopt":
        return _adopt(args)
    if command == "update":
        return _update(args)
    if command == "harness":
        return _harness(args)
    if command == "skills":
        return _skills(args)
    if command == "library":
        return _library(args)
    if command == "config":
        return _config(args)
    if command == "backlog":
        return _backlog(args)
    if command == "task":
        return _task(args)
    if command == "workflow":
        return _workflow(args)
    if command == "upgrade":
        return _upgrade(args)
    if command == "obs":
        return _obs(args)
    print(f"factory {command}: not implemented yet", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
