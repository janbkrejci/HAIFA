"""Every ``error.code`` the CLI can emit, and the codes that appear in ``issues[].code``.

The codes are string literals at their raise sites; ``tests/test_skill.py`` scans the
sources and fails when a code is missing here, so this registry stays complete.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorCode:
    """One ``error.code``: the exit code it comes with (``"1"``, ``"2"`` or ``"1|2"``)."""

    code: str
    exit: str
    meaning: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "exit": self.exit, "meaning": self.meaning}


_CODES: tuple[tuple[str, str, str], ...] = (
    ("repo_io_error", "2", "a registered repository could not be read or written"),
    # Task and backlog input.
    ("invalid_config", "2", "the configuration (.factory/, roster, provider) is invalid"),
    (
        "missing_backlog_dir",
        "1|2",
        "the backlog directory <docs_root>/backlog is missing where it cannot be created "
        "(otherwise it is created silently; 1 for backlog list/check, 2 for task commands)",
    ),
    ("unknown_workflow_advice", "2", "dashboard API: workflow advice expired or not found"),
    ("unknown_task", "2", "no task with this id"),
    ("unknown_step", "2", "no step with this id"),
    ("unknown_project", "2", "no project with this id or directory"),
    ("unknown_container", "2", "no project or step with this id"),
    ("no_index", "2", "the container has no index.md to write"),
    ("duplicate_id", "2", "the id is ambiguous or already used in the backlog"),
    ("invalid_id", "2", "the id does not match ^[A-Za-z0-9][A-Za-z0-9._-]*$"),
    ("invalid_value", "2", "an argument value is not allowed (empty title, bad path, ...)"),
    ("invalid_status", "2", "the status (or status filter) is not allowed"),
    ("no_changes", "2", "the command was given nothing to change"),
    ("conflicting_options", "2", "two options that exclude each other were given"),
    ("self_ref", "2", "a task cannot reference itself"),
    ("file_exists", "2", "the task file or the project/step directory already exists"),
    ("outside_backlog", "2", "the file is outside backlog_dir"),
    ("write_failed", "2", "the task file could not be written"),
    (
        "remote_backlog_conflict",
        "2",
        "local and shared backlog edits conflict, or the shared snapshot changed; "
        "preserve local edits, reload the backlog and retry",
    ),
    (
        "backlog_invalid",
        "1",
        "the backlog has problems (backlog check) or the write would break it (nothing "
        "written); see error.issues",
    ),
    # Runs.
    ("already_running", "2", "a run of this task is in progress"),
    ("task_not_in_base", "2", "the task is not committed in base"),
    ("unmet_dependencies", "2", "depends_on are not done in base (use --force)"),
    ("no_writes", "2", "the task has no writes"),
    ("no_workflow", "2", "the task has no workflow (none set nor inherited)"),
    (
        "unknown_workflow",
        "2",
        "the workflow is neither in .factory/workflows in base nor in the library (the seed "
        "without a library)",
    ),
    ("invalid_workflow", "2", "the task's workflow does not validate"),
    (
        "invalid_test_timeout",
        "2",
        "the task's test_timeout (own or inherited) is not a whole number of seconds above 0",
    ),
    (
        "invalid_override",
        "2",
        "task run --harness/--model/--thinking: unknown harness or thinking, or a model the "
        "harness rejects",
    ),
    ("worktree_failed", "2", "the git worktree could not be created or used"),
    ("trace_db_locked", "2", "the trace database is locked by another process"),
    ("unknown_branch", "2", "the branch does not exist"),
    ("unknown_run", "2", "no run with this id in the trace database"),
    ("unknown_phase", "2", "no phase with this id in the run"),
    ("run_not_running", "2", "the run is not running (finished, stopped or aborted)"),
    ("remote_run", "2", "stop the shared run on the machine that started it"),
    ("run_running", "2", "the run is still running and cannot be archived"),
    ("run_already_paused", "2", "the run is already pausing or paused (factory task pause)"),
    ("run_not_paused", "2", "the run is not paused, there is nothing to resume"),
    ("run_not_archived", "2", "only an archived run can be deleted"),
    (
        "run_not_retryable",
        "2",
        "task retry: the run is not failed, stopped or aborted, or it is a resolve run",
    ),
    ("task_done", "2", "task retry: the task's PR is merged or the task is done in base"),
    ("unknown_chain", "2", "no auto-continue chain with this id in the trace database"),
    ("chain_running", "2", "the chain is still running and cannot be dismissed"),
    # Review, PR and provider.
    ("no_pr", "2", "the task has no pull request"),
    ("no_succeeded_run", "2", "task publish: the task has no succeeded run to publish"),
    (
        "pr_exists",
        "2",
        "task publish: the task (or the run's branch) already has a pull request",
    ),
    ("pr_not_open", "2", "the task's pull request is not open"),
    ("conflict", "2", "the pull request conflicts with base (run factory task resolve)"),
    (
        "task_blocked",
        "2",
        "the task has unmet depends_on (a blocker a run reported); finish them first",
    ),
    ("branch_checked_out", "2", "the branch is checked out in another worktree"),
    ("dirty_worktree", "2", "the worktree has uncommitted changes"),
    ("missing_note", "2", "task return needs a non-empty --note"),
    ("unknown_base", "2", "the base branch does not exist"),
    (
        "not_on_base",
        "2",
        "backlog/config commit: the main checkout is not on the base branch",
    ),
    ("commit_failed", "2", "backlog/config commit or a library write: the commit failed"),
    (
        "base_behind",
        "2",
        "the remote base has commits the local base lacks (run factory config pull)",
    ),
    ("base_diverged", "2", "the local base and the remote base have diverged; nothing changed"),
    (
        "run_in_progress",
        "2",
        "a run with a live process is in progress in the repository (blocks base moves and "
        "config set/remove/move)",
    ),
    (
        "plan_changed",
        "2",
        "config commit/set/remove/move or init --expect: the plan's digest differs (move: "
        "also when the library HEAD moved); global library API plan changed; review the "
        "plan again",
    ),
    ("no_remote", "2", "config pull or library status/pull/push: no remote is configured"),
    ("remote_exists", "2", "library remote: the library is already shared through a remote"),
    ("pull_failed", "2", "config pull or library pull: git could not move the branch"),
    ("sync_on_base", "2", "backlog sync refused to commit on the base branch"),
    ("merge_failed", "2", "the hosting did not merge the pull request"),
    ("approve_failed", "2", "host approval failed or the pull request head changed; merge stopped"),
    ("push_failed", "2", "git push failed"),
    (
        "pr_failed",
        "2",
        "library write/push: gh could not fork or open the pull request; the library is unchanged",
    ),
    ("fetch_failed", "2", "git fetch failed"),
    ("base_moved", "2", "base moved on the remote during the operation"),
    ("dirty_base", "2", "the base checkout has uncommitted changes"),
    ("worktree_remove_failed", "2", "a worktree could not be removed"),
    ("invalid_strategy", "2", "merge_strategy is not squash or merge"),
    ("gh_missing", "2", "the gh CLI is not installed"),
    ("gh_failed", "2", "a gh command failed"),
    ("az_missing", "2", "the az CLI is not installed"),
    ("az_failed", "2", "an az command failed"),
    ("az_timeout", "2", "an Azure CLI command exceeded its timeout; retry the operation"),
    ("az_devops_missing", "2", "the az devops extension is not installed"),
    ("az_not_logged_in", "2", "az is not logged in"),
    # Library in the home directory.
    ("library_exists", "2", "library init: the library directory already exists"),
    (
        "library_missing",
        "2",
        "there is no library yet (run factory library init); config move needs one",
    ),
    ("library_dirty", "2", "the library has uncommitted changes; commit or discard them"),
    (
        "library_behind",
        "2",
        "the library is behind its remote (run factory library pull); nothing changed",
    ),
    (
        "library_diverged",
        "2",
        "the library and its remote have diverged; nothing changed, nothing is forced",
    ),
    ("remote_not_empty", "2", "library init --remote: the remote already has refs"),
    ("clone_failed", "2", "library clone: git clone failed"),
    (
        "invalid_library",
        "2",
        "library clone: the remote has no commit or no valid library.yaml (format, id, name)",
    ),
    ("git_identity_missing", "2", "git has no user.name or user.email"),
    ("outside_home", "2", "library import: the path or a symlink in it is outside home"),
    ("invalid_item", "2", "library import: the item does not validate; see error.issues"),
    (
        "unknown_item",
        "2",
        "no item of this type and name in the library (config remove/move: no own copy in "
        "the repo; config set: the agent is neither in the repo nor in the library)",
    ),
    (
        "in_use",
        "2",
        "config remove: the library lacks the item and a workflow, roles.yaml, an agent or a "
        "backlog task in base uses it; see data.used_by",
    ),
    ("unknown_version", "2", "the item has no such version in its history (or it is ambiguous)"),
    ("not_in_seed", "2", "library seed --take: the installed seed has no such item"),
    ("already_installed", "2", "factory init: .factory/config.yaml is committed"),
    (
        "existing_config",
        "2",
        "factory init: the repo has an sssf installation (adws/adw_sssf_config/); HAIFA does "
        "not take it over",
    ),
    (
        "config_not_committed",
        "2",
        "factory init --commit: .factory/config.yaml is only in the working tree; run factory "
        "config commit",
    ),
    (
        "dirty_paths",
        "2",
        "init --commit and config set/remove/move --commit: planned paths exist in the "
        "working tree with other content",
    ),
    (
        "invalid_plan",
        "2",
        "init --commit and config set/remove/move: the planned configuration does not load "
        "or a workflow fails its preflight; see error.issues",
    ),
    # Results of a command that ran.
    ("run_failed", "1", "the run ended failed or accept was not met; worktree and branch kept"),
    (
        "pr_failed",
        "1",
        "the run succeeded but push or pull request failed (task run, task publish); see "
        "data.pr_error and retry with factory task publish",
    ),
    ("workflow_invalid", "1", "workflow check found problems; see error.issues"),
    ("harness_missing", "1", "a harness CLI is missing or broken; see data.harnesses"),
    ("checks_failed", "1", "factory check found errors; see data.findings"),
    ("skills_sync_failed", "2", "factory skills sync could not write .agents/skills"),
    # factory upgrade.
    ("update_busy", "1", "dashboard update is installing; wait for its restart"),
    ("update_unavailable", "1", "no newer installable release is available"),
    ("editable_install", "2", "upgrade: factory is an editable install from the repo; git pull"),
    ("invalid_url", "2", "upgrade: the bundle URL is neither https nor file"),
    ("download_failed", "2", "upgrade: the bundle URL could not be downloaded"),
    ("bundle_invalid", "2", "upgrade: the bundle is missing, not a zip or lacks a file"),
    ("checksum_mismatch", "2", "upgrade: a file of the bundle differs from SHA256SUMS"),
    (
        "up_to_date",
        "1",
        "upgrade: the bundle's version is not newer than the installed one; nothing installed",
    ),
    ("uv_missing", "2", "upgrade: uv is not on PATH"),
    ("dashboard_running", "2", "upgrade on Windows: the running dashboard locks factory"),
    (
        "upgrade_failed",
        "1",
        "upgrade: uv tool install failed (data.stdout, data.stderr); the old version stays",
    ),
    # Dashboard.
    ("port_in_use", "2", "the dashboard port is already taken (factory obs --port N)"),
    ("not_found", "2", "dashboard API: no such endpoint (HTTP 404)"),
    (
        "cross_origin",
        "2",
        "dashboard API: a write from another origin (Origin or Sec-Fetch-Site) was rejected"
        " (HTTP 403)",
    ),
    (
        "unsupported_media_type",
        "2",
        "dashboard API: a write body that is not application/json (HTTP 415)",
    ),
    ("unknown_repo", "2", "dashboard API: no registered repository has this id (HTTP 404)"),
    ("repo_missing", "2", "dashboard API: the registered repository's folder is gone (HTTP 404)"),
    ("path_not_found", "2", "dashboard API: the path does not exist (HTTP 404)"),
    ("not_a_directory", "2", "dashboard API: the path is not a directory (HTTP 422)"),
    (
        "not_git",
        "2",
        "dashboard API: the folder is not in a git repository; HAIFA runs no git init",
    ),
    ("bare_repo", "2", "dashboard API: a bare repository has no working tree (HTTP 422)"),
    (
        "linked_worktree",
        "2",
        "dashboard API: a linked worktree; add the main checkout instead (HTTP 422)",
    ),
    ("run_worktree", "2", "dashboard API: the path is a worktree of a task run (HTTP 422)"),
    ("no_commits", "2", "dashboard API: the repository has no commit yet (HTTP 422)"),
    (
        "trace_db_shared",
        "2",
        "dashboard API: another registered repository uses the same trace DB (HTTP 409)",
    ),
    (
        "registry_invalid",
        "2",
        "dashboard.yaml in the HAIFA home is invalid; fix it by hand, it is not overwritten",
    ),
    (
        "outside_home",
        "2",
        "dashboard API: the folder is outside the user's home once symlinks are resolved"
        " (HTTP 403)",
    ),
    ("permission_denied", "2", "dashboard API: the folder cannot be read (HTTP 403)"),
    (
        "picker_unavailable",
        "2",
        "dashboard API: no graphical session or dialog program for a folder dialog (HTTP 503)",
    ),
    ("picker_busy", "2", "dashboard API: a folder dialog is already open (HTTP 409)"),
    (
        "picker_timeout",
        "2",
        "dashboard API: the folder dialog was not answered in time (HTTP 504)",
    ),
    ("picker_failed", "2", "dashboard API: the folder dialog program failed (HTTP 502)"),
    (
        "busy",
        "2",
        "dashboard API: another apply or base pull runs in this repository, or another "
        "global library write is running (HTTP 409)",
    ),
    # CLI.
    ("not_a_repository", "2", "the folder is not a git repository"),
    ("invalid_roles", "2", "the role registry cannot be loaded; see error.issues"),
    ("usage_error", "2", "the arguments were rejected (unknown option, missing argument)"),
    ("internal_error", "2", "an unexpected exception; the traceback is on stderr"),
)

ERROR_CODES: dict[str, ErrorCode] = {c: ErrorCode(c, e, m) for c, e, m in _CODES}

ISSUE_CODES: dict[str, tuple[str, ...]] = {
    "backlog": (
        "invalid_frontmatter",
        "missing_field",
        "invalid_field",
        "missing_backlog_dir",
        "misplaced_file",
        "missing_index",
        "misplaced_dir",
        "invalid_status",
        "duplicate_id",
        "unknown_ref",
        "id_prefix",
        "cycle",
    ),
    "workflow": (
        "unknown_agent",
        "invalid_agent",
        "missing_file",
        "bad_condition",
        "bad_description",
        "invalid_id",
        "duplicate_id",
        "invalid_step",
        "unknown_key",
        "missing_max",
        "invalid_max",
        "empty_repeat",
        "unknown_step",
        "unknown_harness",
        "invalid_thinking",
        "invalid_model",
        "invalid_input",
        "override_on_code_step",
        "missing_id",
        "missing_argv",
        "invalid_timeout",
        "test_without_plan",
        "invalid_coverage",
        "unknown_ref",
        "unknown_field",
        "not_a_mapping",
        "missing_name",
        "missing_steps",
        "invalid_yaml",
    ),
    "roles": (
        "missing_output_type",
        "unknown_output_type",
        "invalid_output_type",
        "invalid_gates",
        "unknown_gate",
        "bad_description",
        "invalid_role",
        "unknown_key",
        "missing_agent",
        "invalid_retries",
        "invalid_aliases",
        "unknown_code_step",
        "invalid_code_step",
        "missing_owner",
        "not_a_mapping",
        "missing_roles",
        "missing_code_steps",
        "missing_code_step",
        "alias_conflict",
        "missing_key",
        "missing_file",
        "invalid_yaml",
    ),
    "config": ("invalid_config",),
    # data.items[].origin of the dashboard's factory items and roster
    "item_origin": ("repo", "library"),
    # data.state of `factory check` and the state of a repo, first match wins
    "repo_state": ("installed", "unsupported", "uncommitted", "none"),
    # data.action of `factory check`: what the repo state calls for
    "repo_action": ("config_commit", "init"),
    # data.items[].action of `factory library seed`
    "library_seed": ("create", "update", "unchanged", "kept", "take"),
    # warnings of `factory library status` and `factory library clone`
    "library_status": ("seed_update_available",),
    # data.sync_state of `factory library status`
    "library_sync": ("unshared", "local", "pending", "behind", "synced"),
    # warnings `factory` prints on stderr at start
    "startup": ("env_file_mode",),
    # error.issues of library import (invalid_item)
    "library": (
        "invalid_type",
        "invalid_name",
        "missing_item",
        "missing_file",
        "not_a_file",
        "symlink",
        "too_many_files",
        "too_large",
        "not_utf8",
        "invalid_yaml",
        "not_a_mapping",
        "unknown_key",
        "missing_purpose",
        "invalid_defaults",
        "unexpected_file",
        "missing_skill_md",
        "invalid_front_matter",
        "name_mismatch",
        "missing_description",
        "missing_entry",
    ),
    # findings[].code of `factory check` (data.findings, not error.issues)
    "check": (
        "factory_missing",
        "config_not_committed",
        "repo_unsupported",
        "repo_installed",
        "base_missing",
        "checkout_not_on_base",
        "remote_missing",
        "remote_base_missing",
        "base_behind_remote",
        "base_ahead_of_remote",
        "base_config_invalid",
        "worktree_config_invalid",
        "config_uncommitted",
        "base_setting_mismatch",
        "backlog_missing",
        "backlog_invalid",
        "workflow_unset",
        "workflow_unknown",
        "workflow_invalid",
        "gitignore_missing",
        "skill_mirror_missing",
        "skill_mirror_differs",
        "skill_mirror_extra",
        "harness_missing",
        "disallowed_commands_unenforced",
        "local_config_invalid",
        "local_port_ignored",
        "gh_missing",
        "gh_login",
        "az_missing",
        "az_devops_missing",
        "az_login",
        "hosting_skipped",
        "codex_not_isolated",
        "pi_not_isolated",
        "unsupported_platform",
        "git_missing",
        "git_identity_missing",
        "uv_missing",
        "node_missing",
        "harness_login",
        "pi_model_unknown",
        "env_file_mode",
        "env_override",
        "factory_outdated",
        "library_missing",
        "library_dirty",
        "library_behind",
        "library_unpushed",
        "seed_update_available",
        "roles_full_copy",
        "unknown_thinking",
        "check_failed",
    ),
}
