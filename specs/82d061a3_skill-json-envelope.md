# Plan: `factory --skill` and a single `--json` envelope (task 2.16, D12)

## Goal

1. `factory --skill` prints a markdown skill for coding agents. It is built from the current code:
   - the command list comes from the argparse definition,
   - format constants and error codes come from their source modules,
   - the prose is a packaged template.
2. Every leaf command's `--json` output uses one envelope with stable error codes. The code list appears in the skill.
3. New tests check that every CLI command is in the skill and that every `--json` command returns a valid envelope.
4. `just test`, `just typecheck` and `just lint` pass. They run from the repo root; the justfile does `cd aifactory` itself.

Out of scope: the dashboard. Do not touch `vendor/` or `prototype/`. Also leave the engine files excluded in `pyproject.toml` alone, and do not change `docs/product-brief.md`.

## Facts found during recon (so you don't need to re-read everything)

- All of the CLI is in `aifactory/src/aifactory/cli.py` (~1100 lines). It is argparse with `SUBCOMMANDS` for `task|backlog|workflow|config|harness`.
- There are 18 leaf commands:
  - `harness check`
  - `config status|show`
  - `backlog check|list|sync|auto-continue`
  - `task add|edit|link|show|list|run|approve|return|resolve|clean`
  - `workflow check`

  Every leaf already has `--json`. Each one has `--repo` too, except `harness check`, `config *` and `workflow check`.
- Current JSON output uses three inconsistent shapes:
  - `{"ok":false,"errors":[{code,message,path?,id?}]}` from backlog/task commands (`cli.py` 285, 291, 329, 335, 389, 417, 954, 960, 968)
  - `{"ok":false,"error":str,"issues":[...]}` from `config` (128) and `workflow check` (1054)
  - raw payloads carrying their own `ok`/`warnings`/`errors`
- Payload builders that put `ok` (and some `warnings`) inside the payload:
  - `SyncResult.to_json` (review/sync.py:75)
  - `ApproveResult.to_json` / `CleanResult.to_json` (review/flow.py:60, 79)
  - `ChainResult.to_json` (run/queue.py:144)
  - `WorkflowCheckResult.to_json` (workflow/check.py:73; issues under `errors`)
  - `issues_to_json` (backlog/render.py:69; `errors`, `counts`)
  - `backlog_to_json` (render.py:128; `issues`)
  - `RunConfig.to_json` (config/run.py:29; `warnings`)

  **Do not change these builders.** `tests/backlog/test_backlog_render.py` and `tests/config/test_config_commit.py` read them directly. The CLI strips `ok`/`warnings` when it wraps them (see below).
- Error classes all carry `code` and `message`. Codes are string literals at the raise sites, not constants.
  - `TaskEditError(code, message, ..., exit_code=2, path, id, issues)` is in `backlog/edit.py:59`. `errors()` returns the backlog issues for `backlog_invalid`.
  - `TaskRunError(code, message)` is in `run/errors.py`.
  - `ReviewError(code, message)` is in `review/errors.py`.
  - `ProviderError(code, message)` and `MergeFailed` are in `providers/base.py:25/34`. They are re-raised as Review/TaskRunError with the same code.
  - `ConfigError` (`config/errors.py`) has `issues: [ConfigIssue(path,message)]` and no code.
  - `RolesError` (`engine/role_registry.py:62`) has `issues` with codes.
  - `HarnessConfigError` (`harness/config.py:29`) has `problems: list[str]`.
- Constants to reuse in the skill:

  | Constant | Location |
  |---|---|
  | `VALID_STATUSES`, `DERIVED_STATES`, `INHERITED_KEYS`, `LIST_FIELDS`, `INDEX_FILE` | `backlog/model.py` |
  | `STATUS_FILTERS` | `backlog/render.py:22`, exported from `aifactory.backlog` |
  | `FIELD_ORDER`, `RUNS_HEADING`, `RUNS_PLACEHOLDER` | `backlog/taskfile.py` |
  | `CODE_ACTIONS`, `DEFAULT_ROLES_PATH`, `load_roles()` | `engine/role_registry.py` |
  | `HARNESSES`, `ALIASES` | `harness/__init__.py` |
  | `THINKING_LEVELS` | `harness/override.py:20` |
  | `ProjectSettings` (pydantic; `backlog_dir`, `levels`, `base`, `git_provider`, `merge_strategy`, `test_command`, `worktrees_dir`, …) | `config/settings.py:68` |
  | `AGENTS_FILE`, `ROLES_FILE` | `config/loader.py` |

  The packaged workflows are `aifactory/src/aifactory/defaults/workflows/*.yaml`: document, plan, plan-build, plan-build-test, resolve, scout and simple-sdlc.
- Auto-continue reasons are in `run/queue.py:37,39`:
  - skip: `waits_on_pr|blocked|in_review|running|cannot_start`
  - stop: `failed|exhausted|disabled`
- Nothing outside `aifactory/tests/` reads `factory --json` output (no justfile recipe, nothing in adws).
- Tests that expect `SystemExit` from argparse:
  - `tests/backlog/test_backlog_auto_continue.py:104`
  - `tests/run/test_task_pr_flow.py:136` (`--help`) and `:180`

  The non-JSON behaviour must therefore keep raising `SystemExit(2)` on usage errors.

## Design

### Envelope (every `--json` output, including `factory --skill --json`)

```json
{
  "ok": true,
  "data": { "...": "command payload" },
  "error": null,
  "warnings": ["..."]
}
```

On failure:

```json
{
  "ok": false,
  "data": null,
  "error": {"code": "unknown_task", "message": "...", "path": null, "id": null, "issues": []},
  "warnings": []
}
```

Rules. They go into the skill verbatim, and the tests enforce them.

- The top-level keys are exactly `ok`, `data`, `error`, `warnings`.
- `ok` is true exactly when the exit code is 0. With `ok: true`, `error` is `null`.
- With `ok: false`, `error` is an object with exactly `code` (str), `message` (non-empty str), `path` (str|null), `id` (str|null) and `issues` (list of objects).
- With `ok: false`, `data` may still be filled when a result exists: a failed run, `backlog check` with problems, `workflow check` with problems, a missing harness.
- `error.code` is always one of the documented error codes (`ERROR_CODES`).
- `error.issues` lists the problems that caused the error (backlog/workflow/roles/config issues). Each has at least `code` (config issues get `code: "invalid_config"`) and `message`.
- `warnings` is always a list of strings.
- Exit codes:
  - 0 means ok.
  - 1 means the command ran and found a problem: validation issues, a failed run, a missing harness, a PR that could not be opened, or a write that would break the backlog.
  - 2 means the command could not do its job: bad input, config, state, or a provider error.
- stdout carries only the envelope (engine narration is already redirected to stderr for runs).

### New package `aifactory/src/aifactory/skill/`

**`__init__.py`**
- Re-exports `render_skill`, `skill_json`, `iter_commands`, `CommandSpec`, `ERROR_CODES`, `ISSUE_CODES`, `envelope_ok`, `envelope_fail`, `envelope_problems`.

**`envelope.py`**
- `envelope_ok(data: dict[str, Any], warnings: Iterable[str] = ()) -> dict[str, Any]`
- `envelope_fail(code: str, message: str, *, data: dict[str, Any] | None = None, path: str | None = None, id: str | None = None, issues: Iterable[Mapping[str, Any]] = (), warnings: Iterable[str] = ()) -> dict[str, Any]`
- `strip_payload(payload: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]`. It removes `ok` and `warnings` from a builder payload and returns `(data, warnings)`.
- `envelope_problems(obj: object) -> list[str]`. It returns the rule violations listed above (empty list means valid) and also checks `error.code in ERROR_CODES`. The tests use it, and it doubles as the executable spec.

**`codes.py`**
- `ErrorCode` is a frozen dataclass with `code: str`, `exit: int` and `meaning: str`.
- `ERROR_CODES: dict[str, ErrorCode]` holds every `error.code` the CLI can emit, with a one-line English meaning each. It includes at least:
  - Task and backlog input:
    - Exit 2: `invalid_config`, `missing_backlog_dir`, `unknown_task`, `unknown_step`, `unknown_module`, `unknown_container`, `no_index`, `duplicate_id`, `invalid_id`, `invalid_value`, `invalid_status`, `no_changes`, `conflicting_options`, `self_ref`, `file_exists`, `outside_backlog`, `write_failed`.
    - Exit 1: `backlog_invalid`. It is used for a write that would break the backlog and for `backlog check` with problems.
    - `missing_backlog_dir` from `backlog list` is exit 1. Document it as "1 (list/check), 2 (writes)". Alternatively give `ErrorCode.exit` the type `str` and write "1|2" where it varies. Pick one and keep the table honest.
  - Runs (exit 2): `already_running`, `task_not_in_base`, `unmet_dependencies`, `no_writes`, `no_workflow`, `unknown_workflow`, `invalid_workflow`, `worktree_failed`, `trace_db_locked`, `unknown_branch`.
  - Review, PR and provider (exit 2): `no_pr`, `pr_not_open`, `conflict`, `branch_checked_out`, `dirty_worktree`, `missing_note`, `unknown_base`, `sync_on_base`, `merge_failed`, `push_failed`, `fetch_failed`, `base_moved`, `dirty_base`, `worktree_remove_failed`, `invalid_strategy`, `gh_missing`, `gh_failed`, `az_missing`, `az_failed`, `az_devops_missing`, `az_not_logged_in`.
  - New result codes (introduced by this task):
    - Exit 1: `run_failed` (the run ended failed or `accept` was not met), `pr_failed` (the run succeeded but push or PR failed; the message is `pr_error`), `workflow_invalid` (`workflow check` found issues), `harness_missing` (`harness check` found a missing or broken CLI).
    - Exit 2: `invalid_roles` (the role registry cannot be loaded), `usage_error` (argparse rejected the arguments), `internal_error` (uncaught exception with `--json`; the traceback goes to stderr).
- `ISSUE_CODES: dict[str, tuple[str, ...]]` maps a group to its codes, for the codes that appear in `issues[].code` rather than in `error.code`:
  - `"backlog"`: `invalid_frontmatter`, `missing_field`, `invalid_field`, `missing_backlog_dir`, `misplaced_file`, `missing_index`, `misplaced_dir`, `invalid_status`, `duplicate_id`, `unknown_ref`, `id_prefix`, `cycle`
  - `"workflow"`: `unknown_agent`, `invalid_agent`, `missing_file`, `bad_condition`, `bad_description`, `invalid_id`, `duplicate_id`, `invalid_step`, `unknown_key`, `missing_max`, `invalid_max`, `empty_repeat`, `unknown_step`, `unknown_harness`, `invalid_thinking`, `invalid_model`, `invalid_input`, `override_on_code_step`, `missing_id`, `missing_argv`, `invalid_timeout`, `unknown_ref`, `unknown_field`, `not_a_mapping`, `missing_name`, `missing_steps`, `invalid_yaml`
  - `"roles"`: `missing_output_type`, `unknown_output_type`, `invalid_output_type`, `invalid_gates`, `unknown_gate`, `bad_description`, `invalid_role`, `unknown_key`, `missing_agent`, `invalid_retries`, `invalid_aliases`, `unknown_code_step`, `invalid_code_step`, `missing_owner`, `not_a_mapping`, `missing_roles`, `missing_code_steps`, `missing_code_step`, `alias_conflict`, `missing_file`, `invalid_yaml`
- Verify these lists against the source (a completeness test is below). Do not trust the recon blindly.

**`commands.py`**
- `CommandSpec` is a dataclass with these fields:
  - `path: tuple[str, ...]` (e.g. `("task","run")`)
  - `help: str`, `description: str`
  - `arguments: list[ArgSpec]`
  - `has_json: bool`, `has_repo: bool`
- `ArgSpec` has these fields:
  - `names: tuple[str, ...]` (option strings, or `(metavar,)` for positionals)
  - `metavar: str | None`, `help: str`, `required: bool`, `nargs`, `choices: tuple[str,...] | None`, `default`
  - `group: str | None` (mutually exclusive group marker, e.g. `--on|--off|--inherit` required)
- `iter_commands(parser: argparse.ArgumentParser) -> list[CommandSpec]` walks `parser._actions`. It finds `argparse._SubParsersAction`, recurses into `.choices`, and takes help text from `._choices_actions`. It skips `-h/--help` and groups without leaves, and reads `parser._mutually_exclusive_groups` for the groups.
  - The walk is generic, so a new command appears in the skill automatically.
  - Private argparse attributes are typed in typeshed. If mypy strict complains, use a narrow `# type: ignore[...]` with a comment rather than `Any` everywhere.
- `format_commands(specs) -> str` renders markdown. For each command it produces:
  - a heading `### factory task run`,
  - a usage line built from the specs (e.g. `factory task run ID [--note TEXT] [--force] [--auto] [--json] [--repo PATH]`),
  - the description,
  - a bullet list of arguments with help, choices and required marks.

**`render.py`**
- `render_skill(parser: argparse.ArgumentParser | None = None) -> str`. With no parser it imports `build_parser` from `aifactory.cli` lazily to avoid the circular import. It fills the template.
- `skill_json(parser) -> dict[str, Any]` returns this data for `--skill --json`:
  - `version`
  - `skill` (the markdown text)
  - `commands` (list of `CommandSpec` as dicts)
  - `error_codes` (list of `{code, exit, meaning}`)
  - `issue_codes`
- It loads the template with `importlib.resources.files("aifactory.skill") / "skill.md"`. Hatch already packages non-py files under `src/aifactory`, the same way `defaults/workflows/*.yaml` are.
- Placeholders are `{{name}}`, filled with `str.replace`. After filling, assert that no `{{` remains.
- Generated placeholders:
  - `{{version}}`: `aifactory.__version__`
  - `{{commands}}`: `format_commands(iter_commands(parser))`
  - `{{error_codes}}`: a markdown table `code | exit | meaning` from `ERROR_CODES`, sorted by exit then code
  - `{{issue_codes}}`: per group, comma-separated
  - `{{statuses}}`: `VALID_STATUSES`
  - `{{status_filters}}`: `STATUS_FILTERS`
  - `{{inherited_keys}}`: `INHERITED_KEYS`
  - `{{field_order}}`: `FIELD_ORDER`
  - `{{list_fields}}`: `LIST_FIELDS`
  - `{{runs_heading}}`: `RUNS_HEADING`
  - `{{runs_placeholder}}`: `RUNS_PLACEHOLDER`
  - `{{index_file}}`: `INDEX_FILE`
  - `{{default_levels}}`: the `ProjectSettings` default `levels`
  - `{{settings_keys}}`: `ProjectSettings.model_fields` names with defaults
  - `{{code_actions}}`: `CODE_ACTIONS`
  - `{{harnesses}}`: `HARNESSES` keys plus `ALIASES`
  - `{{thinking_levels}}`: `THINKING_LEVELS`
  - `{{workflows}}`: sorted stems of the packaged `defaults/workflows/*.yaml`, each with its `description:` if cheap to read via yaml
  - `{{roles}}`: packaged role names, and aliases, from `load_roles()` on the default path
  - `{{skip_reasons}}` / `{{stop_reasons}}`: from `run/queue.py`. If they are only literals there, promote them to module constants `SKIP_REASONS` / `STOP_REASONS` in `queue.py` (a small, safe refactor) and import them.

**`skill.md`** (the template, in English, with the Czech section names kept literally) has these sections:

1. **Header.** Name, `{{version}}`, and when to use: an agent driving HAIFA (Helios AI Factory) from the command line. Regenerate with `factory --skill`; never copy it into a repo.
2. **Calling convention.**
   - Always pass `--json`.
   - The envelope, its rules and the exit codes 0/1/2 (from the Design section above).
   - Parse stdout only.
   - Most commands take `--repo PATH`.
   - Runs read config and backlog from the **base commit**: commit backlog and `.factory/` edits first (`factory config status`).
3. **Commands.** `{{commands}}`.
4. **Error codes.** `{{error_codes}}`, then the issue codes `{{issue_codes}}`, then what to do for the common ones:
   - `unmet_dependencies` → wait or `--force`
   - `conflict` → `factory task resolve`
   - `backlog_invalid` → read `error.issues`, fix, `factory backlog check`
   - `already_running` → wait
   - `pr_failed` → the run succeeded, check the remote and the provider CLI
5. **Backlog format.**
   - The tree is `<backlog_dir>/<module>/<step>/<task>.md`. Levels come from `levels` (default `{{default_levels}}`). Tasks live only in the directory of the second-to-last level.
   - Every container directory has `{{index_file}}` with frontmatter `id`, `title` (required) and optional inherited defaults `{{inherited_keys}}` (tasks inherit, the nearest level wins). A body with the description follows.
   - The task file name is `<id>-<slug>.md`. The frontmatter keys, in the written order `{{field_order}}`, are:
     - `id`, `title`, `status` are required;
     - `status` is one of `{{statuses}}`, and `done` is set only by `task approve`;
     - `{{list_fields}}` are lists of strings;
     - `depends_on` may reference tasks or steps;
     - `writes` is a list of paths or globs the agents may change.
   - The body is `## Zadání` (what, where, "done means", out of scope, hard constraints) and `{{runs_heading}}` with `{{runs_placeholder}}`, which HAIFA fills on approve.
   - Id rules: `^[A-Za-z0-9][A-Za-z0-9._-]*$`, unique, prefixed by the parent id plus `-`. The default task id is `<step>-T<NN>`.
   - Derived states and the list filters `{{status_filters}}`.
   - Include one complete example `index.md` and one complete task file (take them from the brief and adapt them to the real fields).
   - The `.factory/config.yaml` keys: `{{settings_keys}}`.
6. **Workflow format.**
   - YAML in `.factory/workflows/<name>.yaml` from base, falling back to the packaged workflows `{{workflows}}`.
   - Top-level keys: `name` (required), `description`, `steps` (required), `accept`.
   - Step forms: a bare name, `{name: {opts}}`, or `{repeat: {max, until, when}, steps: [...]}`.
   - Role steps are the registry roles `{{roles}}`. Their options are `harness` (`{{harnesses}}`), `model`, `thinking` (`{{thinking_levels}}`), `when`, `id`, `description` and `input`.
   - Code steps are `{{code_actions}}`. `command` needs `id` and `argv` and takes an optional `timeout`. Code steps reject harness, model and thinking.
   - Conditions read `<step>.<field>`, and every step has `ran`. `accept` decides success.
   - Agents come from `.factory/agents.yaml` and roles from `.factory/roles.yaml`. The workflow never names an agent directly.
   - Validate with `factory workflow check FILE --json`. Include one example workflow.
7. **Procedures** (numbered, each naming the exact commands):
   - **Plan → backlog.** Read the plan (e.g. `implementation-plan` output: an index plus linked sharded markdown files, followed by links). Map modules to module dirs with `index.md` and steps to step dirs with `index.md`; these are created by hand as files, since `task add` only creates tasks. Then add each task with `factory task add STEP TITLE --id … --writes … --depends-on … --body … --json`, or write task files directly in the format above. Run `factory backlog check --json` until `ok`, then `factory backlog list`, commit, and push to base. There is no importer; the conversion is this procedure (D12).
   - **Run.** `factory task list --status ready --json`, then `factory task run ID [--note] [--auto] --json`.
     - Read `data.run.state`, `data.pr` and `data.chain`.
     - On failure the worktree and branch are kept. Re-run with `--note`.
     - Describe auto-continue with its skip reasons `{{skip_reasons}}` and stop reasons `{{stop_reasons}}`; it never approves or merges.
   - **Review.** `factory task show ID --json` gives runs, PRs and the body. Review the PR diff through the hosting provider.
   - **Approve.** `factory task approve ID --json` adds a done commit and `## Běhy` line, merges, updates base and removes worktrees. On `conflict`, resolve first. Note D11: no approve review is sent yet.
   - **Return.** `factory task return ID --note TEXT --json` starts a new run on the same branch and updates the PR.
   - **Resolve.** `factory task resolve ID --json` rebases onto base; an agent fixes only the conflicted files, then the tests run and the branch is force-pushed with a lease. On failure the branch stays as it was. Then approve.
   - **Sync and cleanup.** `factory backlog sync --json` handles PRs merged outside factory. `factory task clean --json` removes worktrees. `factory backlog auto-continue ID --on|--off|--inherit`.

### CLI changes (`aifactory/src/aifactory/cli.py`)

1. **Root options** in `build_parser()`:
   - `--skill` (`store_true`, help "print the agent skill for this version and exit")
   - `--json` with `dest="root_json"`. Use a distinct dest so it does not collide with the subcommand `--json` dest; it is only meaningful with `--skill`.
2. **Parser class.** Add `class _Parser(argparse.ArgumentParser)` whose `error(message)` raises `_UsageError(parser=self, message=message)`, and use it for the root. Subparsers inherit the class through `add_subparsers`, which defaults `parser_class` to `type(self)`; verify this.
3. **`main(argv)`:**
   - Compute `argv_list = list(sys.argv[1:] if argv is None else argv)` and `want_json = "--json" in argv_list`.
   - Wrap `parse_args` in `try/except _UsageError`:
     - With `want_json`, print `envelope_fail("usage_error", message)` and return 2.
     - Otherwise call `exc.parser.print_usage(sys.stderr)`, print `f"{exc.parser.prog}: error: {message}"` to stderr, and `raise SystemExit(2)`. This keeps the old behaviour, and the tests expect `SystemExit`.
   - If `args.skill`: with `args.root_json`, print `envelope_ok(skill_json(parser))`; otherwise print `render_skill(parser)`. Return 0.
   - Wrap the command dispatch: if the command asked for JSON (`getattr(args, "json", False)`) and an unexpected `Exception` escapes, print the traceback to stderr, print `envelope_fail("internal_error", f"{type(exc).__name__}: {exc}")` and return 2. Without `--json` let it propagate as today.
4. **Output helpers.** Replace `_print_json` and the scattered error printing with:
   - `_emit(envelope)`: `json.dumps(..., ensure_ascii=False, indent=2)`.
   - `_emit_ok(data, warnings)`.
   - `_emit_fail(code, message, **kw)`.
   - `_config_issues(exc: ConfigError) -> list[dict]`: `[{"code":"invalid_config","message":i.message,"path":i.path,"id":None}]`.
   - One `_fail_from_exception(exc, as_json, command) -> int`. It maps `ConfigError`, `TaskEditError`, `TaskRunError`, `ReviewError`, `RolesError` and `HarnessConfigError` to envelope and exit code, and falls back to today's stderr text when not JSON.
   - For `TaskEditError`, use `code=exc.code`, `message=exc.message`, `path=exc.path`, `id=exc.id`, `issues=[i.to_dict() for i in exc.issues]`. The exit code stays `exc.exit_code`.
   - Keep the non-JSON output byte-for-byte as it is now wherever practical, because existing text tests assert on it.
5. **Per command `data` and failure mapping** (warnings go to the envelope, never into `data`):

   | Command | `data` on success | failure (`error.code`, exit, `data`) |
   |---|---|---|
   | harness check | `{harnesses: [...]}` | missing → `harness_missing` exit 1, message `"missing: a, b"`, data kept; bad `--config` → `invalid_config` exit 2, issues from `problems` (`{"code":"invalid_config","message":p}`) |
   | config status | `{base, commit, clean, changes}`; `warnings` = change warnings | `invalid_config` exit 2, issues |
   | config show | `run.to_json()` minus `warnings`; `warnings` = `run.warnings` | `invalid_config` exit 2 |
   | backlog check | `{counts, issues}` (the builder's `errors` renamed to `issues`) | issues → `backlog_invalid` exit 1, message `"N problem(s)"`, `error.issues` = the same list, data kept |
   | backlog list | `backlog_to_json(...)` minus `ok`; if issues exist add warning `"N problem(s), run 'factory backlog check'"` | `missing_backlog_dir` exit 1 (data kept); `unknown_module` exit 2 (`id`=module); `invalid_config` exit 2 |
   | backlog sync | `result.to_json()` minus `ok`/`warnings` | exceptions via `_fail_from_exception` |
   | backlog auto-continue | `{changed, id, level, path, auto_continue, issues}` | via `_fail_from_exception` |
   | task add/edit/link | `{action, changed, path, task, issues}`; warning if issues | via `_fail_from_exception` (`backlog_invalid` exit 1 with `error.issues`) |
   | task show | `{task, body, issues, runs, prs}` | via `_fail_from_exception` |
   | task list | `{filters, tasks, issues}`; **ok true, exit 0** even with issues (as today's exit code), plus the warning | via `_fail_from_exception` |
   | task run | `{run, pr, pr_error, chain: {runs, stop, waiting}}`; `warnings` = first run's warnings | run failed → `run_failed` exit 1, message `run.error or "run failed"`; run ok but `pr_error` → `pr_failed` exit 1; for a chain, use the first failing run's code; data kept |
   | task return / resolve | `{run, pr, pr_error}` | same mapping as run |
   | task approve | `result.to_json()` minus `ok`/`warnings` | via `_fail_from_exception` |
   | task clean | `{removed}` | via `_fail_from_exception` |
   | workflow check | `result.to_json()` minus `ok`/`warnings`, with `errors` renamed to `issues` | issues → `workflow_invalid` exit 1 with `error.issues`, data kept; registry or roster load failure: `RolesError` → `invalid_roles`, `ConfigError`/`HarnessConfigError`/`OSError` → `invalid_config`, exit 2 |

   Invariant: `ok == (exit_code == 0)`. Exit codes stay exactly as today; only the JSON shape changes (`task list` `ok` now follows exit 0).

6. **`TASK_EPILOG`.** Replace the hand-maintained code lists with a short text that keeps the behavioural notes (the exit 1 vs 2 meaning, auto-continue, conflict → resolve, D11 approve note). Keep the words "D11" and "no approve review", because `test_approve_help_mentions_d11` reads the `approve` description, so check it still passes. Point to `factory --skill` for the full code list, and change `errors[].code` to `error.code`.
7. **Module docstring.** Update it to mention `--skill`.

### Out of the envelope
- `--help` / `--version` stay plain argparse output.
- Group commands without a subcommand (`factory task`) print help as today. They have no `--json`, so `factory task --json` is a usage error, and with `--json` in argv it returns the `usage_error` envelope.

## Tests

### New `aifactory/tests/test_skill.py`
- `test_every_command_is_in_skill`:
  - Walk `build_parser()` independently of `iter_commands`: write a small local recursive walk over `_SubParsersAction` in the test.
  - For every leaf path, assert `"factory " + " ".join(path)` is in `render_skill()`.
  - For every non-help option string and positional metavar of that leaf, assert it appears in that command's section. The section is the text between its heading and the next `### `.
  - Also assert the leaf count equals `len(iter_commands(...))`.
- `test_every_command_has_json`: every leaf has a `--json` option.
- `test_skill_lists_error_codes`: every key of `ERROR_CODES` and every issue code appears in the skill, and `{{` does not.
- `test_skill_sections`: the skill contains the headings for backlog format, `index.md`, the task header fields (`depends_on`, `writes`, `## Zadání`, `## Běhy`), the workflow format (`repeat`, `accept`), and the procedures (plan → backlog, run, review, approve, return, resolve).
- `test_skill_cli`:
  - `main(["--skill"]) == 0` and stdout starts with the skill header.
  - `main(["--skill","--json"])` gives an envelope that passes `envelope_problems`, with `data.skill`, `data.commands` and `data.error_codes`.
- `test_error_codes_complete`:
  - Use `ast` to scan `aifactory/src/aifactory/**/*.py`, excluding the ported engine files where ruff and mypy are excluded, but including `engine/role_registry.py`.
  - Calls to `TaskEditError`, `TaskRunError`, `ReviewError`, `ProviderError`, `MergeFailed` with a string-literal first positional argument or `code=` literal must be in `ERROR_CODES`.
  - Calls to `Issue(...)` with a literal code in `backlog/`, `workflow/` and `engine/role_registry.py` must be in the union of `ISSUE_CODES`.
  - Literal codes passed to `_emit_fail` / `envelope_fail` in `cli.py` must be in `ERROR_CODES`.
  - Adjust the matched names to the real constructors (check `MergeFailed`'s signature, and whether `Issue` is imported under another name).
- `test_usage_error_json`:
  - `main(["task","return","X","--json"])` (missing `--note`) returns 2 with a valid envelope and `error.code == "usage_error"`.
  - Without `--json` it raises `SystemExit`.

### New `aifactory/tests/test_json_envelope.py`
- Parametrize over every leaf of `build_parser()` that has `--json`. The parametrization is generated from the parser, so a new command is covered automatically.
- Build argv from the spec:
  - the path;
  - dummy positionals by metavar (`ID`→`"X-T01"`, `STEP`→`"X"`, `TITLE`→`"t"`, `FILE`→`str(tmp_path/"missing.yaml")`, anything else → `"x"`);
  - required options: `--note` → `"n"`; for a required mutually-exclusive group, use its first option;
  - `--json`;
  - `--repo tmp_path` when the command has `--repo`.
- `monkeypatch.chdir(tmp_path)` (an empty non-git dir).
- For `harness check`, `monkeypatch.setenv("PATH", str(tmp_path / "empty"))` so it is deterministic and never starts a real CLI.
- Assert that:
  - stdout is exactly one JSON document;
  - `envelope_problems(obj) == []`;
  - `obj["ok"] == (rc == 0)`;
  - when not ok, `error.code in ERROR_CODES`.

  These are mostly error paths (`invalid_config`, `harness_missing`, `workflow_invalid`, …), which is fine; the point is that every command wraps its output.
- Success-path envelope tests use the existing fixtures:
  - `tests/backlog/backlog_repo.py` for `backlog check|list`, `task list|show|add`
  - `tests/config/config_repo.py` for `config status|show`
  - the `workflow check` of a packaged default with the test roster, as in `test_default_workflows.py`

  Each asserts `ok` true, `envelope_problems == []`, and that `data` has the documented keys.

### Migrate the existing JSON tests
Mechanical changes; no behaviour changes:

- Move payload keys under `P["data"]`.
- Change `P["errors"][0]["code"]` to `P["error"]["code"]`. For `backlog_invalid` cases, e.g. the cycle case in `test_task_cli.py::test_errors`, assert `error.code == "backlog_invalid"` and read `error.issues[0].code/path`.
- Change validation lists (`errors`) to `data.issues`.
- Top-level `warnings` stay top-level.

Files and what changes in each:

- `tests/config/test_config_cli.py`: `ok`/`clean`/`base`/`changes`/`agents`/`workflows`/`local` move under data. The broken-config test reads `error.issues[0].path`.
- `tests/backlog/test_backlog_auto_continue.py`: data keys; `error.code == "unknown_container"`.
- `tests/backlog/test_task_cli.py`: all tests, as described above.
- `tests/backlog/test_backlog_cli.py`:
  - `test_check_ok` compares the whole envelope `{"ok":True,"data":{"counts":…, "issues":[]},"error":None,"warnings":[]}`;
  - check errors come from `data.issues[*].path`;
  - the list keys move under data;
  - missing dir → `error.code == "missing_backlog_dir"`.
- `tests/harness/test_harness_check_cli.py`: `data.harnesses`.
- `tests/workflow/test_workflow_cli.py` and `tests/workflow/test_default_workflows.py`: `errors` → `data.issues`, the other keys under data, and `warnings` at top level. The exit-2 roles test reads `error.code == "invalid_roles"` and `error.issues[*].code`.
- `tests/run/test_task_run.py`, `test_task_run_cli.py` and `test_auto_continue.py`: `data.run`, `data.pr`, `data.pr_error`, `data.chain`. A failed run is `error.code == "run_failed"` with `data.run.state`/`error`.
- `tests/run/test_task_pr_flow.py`, `test_task_resolve.py` and `test_backlog_sync.py`: update `cli_json` callers to `data`/`error`. `test_clean_without_runs` compares the whole envelope `{"ok":True,"data":{"removed":[]},"error":None,"warnings":[]}`.
- `tests/test_smoke.py`: add `--skill` to the help check if trivial. Otherwise leave it.
- Consider adding a tiny shared helper, `aifactory/tests/cli_json.py` with `run_json(capsys, argv) -> tuple[int, dict]` that also asserts `envelope_problems == []`. That way every migrated test checks the envelope for free. The existing per-file helpers can call it.

## Order of work

1. `skill/codes.py`, `skill/envelope.py` and their unit tests.
2. CLI output refactor (the envelope everywhere, `_Parser`/usage errors, `internal_error`), then migrate the existing tests and get `just test` green.
3. `skill/commands.py`, `skill/render.py`, `skill/skill.md`, the `--skill` flag, and the new tests.
4. Adjust `TASK_EPILOG` and the docstring.
5. `just lint` (ruff check plus `ruff format --check`; run `uv run ruff format` in `aifactory/` first), `just typecheck` (mypy strict over src and tests) and `just test`. Judge each by its exit status.

## Verification

- `just test`, `just typecheck` and `just lint` all exit 0.
- `just factory --skill | head -50` shows the header and calling convention. `just factory --skill` contains `### factory task resolve` and the error-code table.
- `just factory --skill --json` is a valid envelope.
- `just factory task show NOPE --json` gives `{"ok": false, "data": null, "error": {"code": "unknown_task", ...}, "warnings": []}` with exit 2.
- `just factory task return X --json` gives a `usage_error` envelope with exit 2.

## Non-goals and constraints
- Do not change `vendor/`, `prototype/`, `docs/product-brief.md`, `adws/`, or the ported engine files listed in `pyproject.toml` `extend-exclude`. `engine/role_registry.py` is not in that list, but it needs no change.
- Do not change the payload builders' `to_json` shapes (other tests read them). Do the wrapping only in the CLI.
- No dashboard work, and no plan importer in code: plan → backlog is a procedure in the skill (D12).
