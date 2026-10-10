---
name: factory
description: >-
  Use when a coding agent adds HAIFA to an existing Git repository, configures
  its agents and workflows, turns a plan into a project/step/task backlog, or
  drives factory tasks. Do not use for general coding without HAIFA, installing
  the HAIFA CLI itself, library administration, multi-repository operations,
  or HAIFA upgrades.
---

# HAIFA skill: driving the `factory` CLI (aifactory {{version}})

This guide is generated from the installed code by `factory --skill`.
Save its Markdown output as an agent's `SKILL.md`; `factory --skill --json`
returns the same guide inside the JSON envelope. Compare `factory --version`
with aifactory {{version}}: whenever the version changes, regenerate this skill
with `factory --skill` and replace the saved copy.

## Prerequisites

Start in the existing Git repository with `factory check --json`. The check only
reads; even a failed check can return `data.findings`. Read each finding's `action`
and `fix`, together with `data.state` and `data.action`, before making changes:

| State | Action | Next step |
| --- | --- | --- |
| `none` (repo without factory) | `init` | Add factory to the existing repo below. |
| `uncommitted` (configuration only in the working tree) | `config_commit` | Review and commit configuration using the Commit configuration procedure, then check again. |
| `installed` (manifest in base) | none | Factory is installed. Run `factory update` to bring items from the library. |
| `unsupported` (`.factory/` without a manifest, or sssf `adws/`) | none | HAIFA does not take over a configuration it did not install. Tell the user; do not convert it. |

Resolve machine findings (Git, provider CLI, chosen harness CLI and credentials)
using their `fix`; do not run tasks until error findings are resolved. See Check for
the payload details.

## Calling convention

- Start with `factory check --json` in a repository you have not worked in yet: it says
  (only by reading) whether factory will run there and on this machine, and what to fix.
  On a new machine run it anywhere, even outside a repository (`factory` without a command
  prints "První spuštění: factory check").
- Always pass `--json`. stdout then carries exactly one JSON document, the envelope below;
  engine narration and tracebacks go to stderr. Parse stdout only.
- Most commands take `--repo PATH` (default: the git repository of the current directory).
- Runs read the configuration (`.factory/`) and the backlog from the **base commit**, not
  from the working tree. Commit (and push) backlog and `.factory/` edits before you run a
  task; `factory config status --json` lists the uncommitted `.factory/` changes a run
  would not see. Commit them with `factory config commit --json` (see Commit
  configuration) and the backlog with `factory backlog commit --json`.

### The envelope

Success:

```json
{"ok": true, "data": {"...": "command payload"}, "error": null, "warnings": []}
```

Failure:

```json
{
  "ok": false,
  "data": null,
  "error": {"code": "unknown_task", "message": "...", "path": null, "id": "X-T01", "issues": []},
  "warnings": []
}
```

Rules (every command follows them, tests enforce them):

- The top-level keys are exactly `ok`, `data`, `error`, `warnings`.
- `ok` is true exactly when the exit code is 0. With `ok: true`, `error` is `null`.
- With `ok: false`, `error` is an object with exactly `code` (string), `message` (non-empty
  string), `path` (string or null), `id` (string or null) and `issues` (list of objects).
- With `ok: false`, `data` may still be filled when a result exists: a failed run,
  `backlog check` or `workflow check` with problems, a missing harness.
- `error.code` is always one of the error codes listed below.
- `error.issues` lists the problems that caused the error (backlog, workflow, roles or
  config issues). Each has at least `code` and `message` (config issues have
  `code: "invalid_config"` and a `path`).
- `warnings` is always a list of strings. Read them; they are not errors.
- Exit codes:
  - `0`: ok.
  - `1`: the command ran and found a problem: validation issues, a failed run, a missing
    harness, a pull request that could not be opened, a write that would break the backlog.
  - `2`: the command could not do its job: bad input, configuration, state, or a provider
    error. Nothing was changed.
- `--help` and `--version` print plain text, not an envelope.

## Commands

### Switch the local roster

`factory config roster show --json` lists effective local agent harness/model/thinking.
`factory config roster set codex --dry-run --json` previews all-Codex
(`gpt-6.1-sol`, medium); omit `--dry-run` to write locally. Use
`factory config roster set claude --json` for all-Claude (`claude-opus-5-5`, medium).
A whole-roster preset clears existing per-agent harness/model/thinking overrides,
retaining purposes, prompts, writes and other settings. For a mixed roster, set Claude
first, then `factory config roster set codex --agent builder --json`; a reviewer can
be set with `factory config roster set claude --agent reviewer --json`.
`--harness`, `--model`, `--thinking` override preset values; all commands accept `--repo`.
Review the returned diff, then use the existing `factory config commit` flow. Runs read
committed base; workflow step overrides remain authoritative.

Every command below accepts `--json`.

{{commands}}

## Error codes

`error.code`, the exit code it comes with, and what it means:

{{error_codes}}

Codes that appear in `error.issues[].code` (and in `data.issues[].code`), by source
(`check`: `data.findings[].code` of `factory check`; `item_state`: `data.items[].state` of
`factory config items`):

{{issue_codes}}

What to do with the common ones:

- `unmet_dependencies`: wait until the dependencies are done in base, or pass `--force`.
- `conflict`: run `factory task resolve ID --json`, then approve again.
- `backlog_invalid`: read `error.issues`, fix the files, run `factory backlog check --json`
  until `ok` is true.
- `already_running`: another run of the task is in progress; wait for it.
- `run_already_paused`, `run_not_paused`: see Procedures, Pause, resume and stop.
- `pr_failed`: the run succeeded and its branch exists; `data.pr_error` says why. Check the
  remote and the provider CLI (`gh`, `az`), then `factory task publish ID --json` (see
  Publish). A push that failed on the network was already retried a few times.
- `run_failed`: read `data.run.error`; the worktree and branch are kept. Re-run with
  `factory task run ID --note TEXT --json`.
- `invalid_config`: read `error.issues[].path` and `message`, fix `.factory/`, commit.
- `format_unsupported`: the repo's `.factory/manifest.yaml` is newer than the installed
  HAIFA; run `factory upgrade`. Nothing ran.
- `usage_error`: the arguments are wrong; see the command reference above.
- `checks_failed`: `factory check` found errors; read `data.findings` (see Procedures,
  Check), fix the `error` findings and run the check again.

## Backlog format

The backlog is a tree of markdown files under `backlog_dir` (setting in
`.factory/config.yaml`):

```
<backlog_dir>/<project>/<step>/<task>.md
```

- One repo may hold several backlog roots: `backlog_dirs: [path, ...]` in
  `.factory/config.yaml` instead of `backlog_dir` (setting both is a configuration error).
  Each entry is a directory relative to the repository; a path part may use `*`, e.g.
  `moduly/*/backlog` (`*` does not cross `/`). Every root holds projects like a single
  `backlog_dir`. Ids of projects, steps and tasks must be unique across all roots
  (`factory backlog check` reports `duplicate_id` with both files). All commands read and
  write every root, and `factory backlog commit` commits the changes in all of them.
  `factory backlog add --backlog-dir DIR` picks the root of a new project (a directory
  matching an entry; without it the first existing root).
- The levels come from `levels` (default `{{default_levels}}`). Tasks live only in the
  directories of the second-to-last level (steps by default).
- Every container directory (project, step) has `{{index_file}}` with a YAML header:
  `id` and `title` are required; the optional inherited defaults are
  `{{inherited_keys}}`. Tasks inherit them; the nearest level wins. A markdown body with the
  description follows the header.
- A task is one file named `<id>-<slug>.md` (slug: ASCII lowercase, e.g.
  `M01-S02-T01-endpoint.md`).

### Task header

YAML front matter; HAIFA writes the keys in this order: `{{field_order}}`.

- `id`, `title` and `status` are required.
- `status` is one of `{{statuses}}`. Set `todo` or `cancelled` by hand
  (`factory task edit`); `done` is set only by `factory task approve` (or `backlog sync`).
- `{{list_fields}}` are lists of strings.
- `depends_on` may reference tasks or steps (a step is done when all its tasks are done).
  Store only `depends_on`; "blocks" is computed. `related` is informational.
- `writes` is the list of paths or globs the agents may change; anything else is rolled back.
  Own or inherited; when no level sets it, the whole repo (`**`), protected files excepted.
  An explicit empty list `[]` cannot run (`no_writes`).
- `workflow` names the workflow (own or inherited); when no level sets it, `simple-sdlc`.
  An explicit `null` means none (`no_workflow`).
- `test_timeout` is the shared time limit of the checks a workflow's `test` step runs, in
  whole seconds greater than 0 (own, or the nearest `index.md` above); without it `test_timeout` from
  `.factory/config.yaml`, else 600. An invalid value is reported by `factory backlog check`
  and stops `factory task run` with `invalid_test_timeout`.
- `specs_dir` and `docs_dir` are the directories of the task's spec and documentation
  (own or inherited, like `test_timeout`); without them those of `.factory/config.yaml`. A value
  must be a relative path inside the repository; otherwise `factory backlog check` reports
  it and `factory task run` stops with `invalid_output_dir`.

The body has two sections:

- `## Zadání`: what to do, where, "done means", out of scope, hard constraints.
- `{{runs_heading}}` with `{{runs_placeholder}}`; HAIFA adds one line per approved PR.

Ids match `^[A-Za-z0-9][A-Za-z0-9._-]*$`, are unique across the backlog and start with the
parent id plus `-` (`M01` -> `M01-S02` -> `M01-S02-T01`). The default task id is
`<step>-T<NN>` (next free number).

States: the file stores `{{statuses}}`; `ready` and `blocked` are derived from
`depends_on` for `todo` tasks; running, failed and in review live in the trace DB and the
hosting. List filters (`--status`): `{{status_filters}}`.

Example `{{index_file}}` of a project (its id is any short code, e.g. `M01` or `HAIFA`):

```markdown
---
id: M01
title: Core
workflow: plan-build-test
source: src/
target: src/
writes: [src/]
auto_continue: false
auto_merge: false
---

Core: the data model and the API.
```

Example `{{index_file}}` of a step:

```markdown
---
id: M01-S02
title: API
---

Read-only HTTP API over the model.
```

Example task file `backlog/M01-core/S02-api/M01-S02-T01-endpoint.md`:

```markdown
---
id: M01-S02-T01
title: Endpoint
status: todo
workflow: plan-build-test
depends_on: [M01-S01]
related: [M02-S01-T01]
writes: [src/api/, tests/api/]
---

## Zadání
Add GET /model returning the model as JSON.

Where: `src/api/`, `tests/api/`.

Done means:
- GET /model returns 200 with the model; a test covers it.
- The suite passes.

Out of scope: writing endpoints.

Hard constraints: do not change `src/model/`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
```

### `.factory/config.yaml`

Shared settings are committed in `.factory/config.yaml`. Create them through
`factory init`,
review the detected base and provider, then edit the YAML to fit
this repository. Validate with `factory check --json` and
`factory backlog check --json`; review and commit using Commit configuration.
Runs read these files from base. Machine-local `trace_db` and `database_url`
belong in `.factory/local.yaml`, not here; the dashboard port is in its registry.

Every key, including nested entries, is generated from the configuration model.
`null` means unset, `[]` an empty list, and `required` has no default:

{{settings_keys}}

### Agents and prompts

`.factory/agents.yaml` contains a `defaults` mapping and an `agents` list.
Each agent has a unique `name` (its slot). The slot identifies its prompts and is
what a role's `agent` or a workflow step's `agent` selects. The manifest maps the
slot to its source `item` and `version`; slot and library item names may differ.
Bindings (`harness`, `model`, `thinking`, tools and permissions) belong to the
repository and are separate from the reusable prompt item.

| Key | Meaning |
| --- | --- |
| `name` | Required slot name in each agent entry. |
| `harness` | Explicit harness: {{harnesses}}; never inferred from model. May be inherited from defaults. |
| `coding_agent` | Compatibility alias for harness; conflicting values are rejected. |
| `model` | Model accepted by the selected harness; may be inherited. |
| `thinking` | Reasoning level: {{thinking_levels}}; may be inherited. |
| `purpose` | Agent role description. |
| `color` | Dashboard lane color; may be inherited. |
| `tools` | Tool allowlist; null allows all tools supported by the harness. May be inherited. |
| `writes` | Allowed paths/globs: null unrestricted except protections, [] read-only. Task scope also applies. May be inherited. |
| `disallowed_commands` | Shell command patterns denied by the harness; may be inherited. Unsupported enforcement is reported. |
| `harness_engineering` | Paths to pi extensions; may be inherited, rejected for other harnesses. |

Every declared slot requires both `.factory/prompts/<slot>/system.md` and
`.factory/prompts/<slot>/user.md`; `prompt_engineering` is forbidden in this
roster because the paths are fixed. Put role instructions in system.md and the
request plus expected output in user.md. Variables are replaced literally using
double braces around their names:

| Variable | Value |
| --- | --- |
| `prompt` | Task header, effective source/target, allowed paths, output paths, assignment and operator note. |
| `previous_envelope` | Previous agent's Report JSON, or `(none)`. |
| `context_handoff_dir` | Absolute session handoff directory. |
| `task_id` | Current task ID. |
| `spec_path`, `doc_path` | Specification and documentation paths relative to the worktree. |
| `workdir` | Absolute task worktree path. |
| `test_result` | Latest test results as JSON. |
| `baseline` | Commit the run started from; `git diff <baseline>` is the whole change. |
| `previous_test_plan` | The plan the last test ran, `(none)` before the first. |
| `failed_test` | In a tester triage: the red test to judge; otherwise `(none)`. |
| `rebase_onto` | Target commit, only in conflict resolution runs. |

`<context_handoff_dir>` is an absolute path outside the repo. Write handoff files at exactly that path; never create a directory of the same name inside the repo or the worktree.

A workflow role step's `input` mapping supplies additional named variables with
JSON results of the selected earlier steps. Engine variables take precedence on
a collision; unknown variables remain unchanged. A workflow `test` step executes
code, not an agent prompt: it runs the checks the latest `test_plan` step chose.
Timeout and slots follow the Workflow format rules below.

Editing a tracked agent prompt in this repository makes its item `modified`
when the library has not moved (or `diverged` if both changed).
`factory config items --json` shows this state. `factory config export agent
<slot> --dry-run --json` previews returning the prompt to the library; after
review, `factory config export agent <slot> --expect <digest> --json` writes it
there and records the new version in the manifest. Commit the shared configuration.


## Workflow format

A workflow is YAML in `.factory/workflows/<name>.yaml` (read from base), falling back to the
packaged workflows: {{workflows}}.

- Top-level keys: `name` (required), `description`, `steps` (required), `accept`.
- A step is one of:
  - a bare name: `- plan`
  - a name with options: `- commit: {when: test.passed, description: ...}`
  - a loop: `- repeat: {max: 3, until: test.passed, when: ...}` with `steps: [...]`
    (`max` required).
- Role steps are the roles of the registry (`.factory/roles.yaml`, else packaged):
  {{roles}}. Their options: `agent` (a name from `.factory/agents.yaml`; the step runs on it
  and keeps the role's output type and gates), `harness` (one of {{harnesses}}), `model`,
  `thinking` (one of {{thinking_levels}}), `when`, `id`, `description` and `input`.
- Code steps are {{code_actions}}. `command` needs `id` and `argv` (a list) and takes an
  optional `timeout`. Code steps reject `agent`, `harness`, `model` and `thinking`.
- A `test_plan` role step (agent `tester`) reads the change since the `baseline` prompt variable and the
  repo, and returns `coverage` (`full`, `scoped` or `none`), `reason` and `checks`
  (`name`, `argv` list, optional `timeout` in seconds): enough checks to trust the
  change, nothing beyond. There is no configured test command; every repo, whatever its
  stack, gets its checks from the tester. The gate `checks_runnable` requires the first
  argv element of every check on PATH or as a file in the worktree.
- A later `test_plan` keeps every check of the previous plan (same argv) or names it in
  `dropped` with a reason (gate `plan_keeps_checks`). Workflows plan again after every
  fix and every revision, from the whole diff since `baseline`.
- A `test_plan` step may require a coverage: `coverage: full` (every check the repo has)
  or `coverage: scoped` (only the latest changes); gate `coverage_required`. The result of
  a `test` repeats the plan's coverage, so conditions can read `test.coverage == "full"`.
  The packaged `heal` workflow runs the whole suite, repairs until it is green (each repair
  checked scoped, then confirmed on the whole suite) and commits only on a green full run.
- A red `test` goes to the tester first (phase `triage`): `failure_cause: plan` (the
  checks themselves were wrong) replaces the plan and runs the test again without a
  repair round and without the builder, at most twice per run; `code` leaves the
  failure for `fix`.
- A `test` step (also under another `id`, e.g. `retest`) runs the checks of the latest
  `test_plan` in order, without a shell, and runs every check even after one fails (only
  a failed check with `stop_on_fail: true` or an exhausted time limit stops the rest,
  which the result lists in `not_run` with the reason); a workflow with a
  `test` and no earlier `test_plan` is invalid (`test_without_plan`). `none` runs nothing
  and passes. The checks share one time limit: the task's `test_timeout`, else the
  nearest `index.md` `test_timeout`, else `test_timeout` from `.factory/config.yaml`,
  else 600 s; a check over the limit is stopped and the step fails (exit 124). The
  step's `test_plan` field (also in the `test_result` prompt variable) records coverage, reason, the commands
  and how many ran. Reviewers judge the plan: enough to trust the change, not wider than
  it needs.
- At most `test_slots` (`.factory/config.yaml`, whole number ≥ 1, default 1) `test`
  steps run their command on the machine at once; the others wait in a queue in the
  order they asked (`<HAIFA home>/test_slots`). The wait is traced as `test_slot` events
  (`state: waiting` with `ahead`, then `state: acquired` with `waited_seconds`), shows in
  the dashboard and does not count into `test_timeout`. A slot of a crashed, stopped or
  killed run frees itself.
- Conditions (`when`, `until`, `accept`) read `<step>.<field>` of an earlier step's result
  (e.g. `test.passed`); every step has `ran`. `accept` decides whether
  the run succeeded.
- Agents come from `.factory/agents.yaml` and roles from `.factory/roles.yaml`; a workflow
  names roles. `agent:` on a role step changes the agent for that step only;
  `factory workflow check` and the run's preflight verify that it is in the roster and
  accepts the step's `harness`, `model` and `thinking` (`unknown_agent` at
  `steps[N].<step>.agent`). `data.steps[].agent` shows each step's agent.
- `.factory/roles.yaml` without `code_steps` is an overlay of the packaged registry: an
  existing role changes only the fields it names (e.g. `review: {agent: critic}`), a new
  role needs `agent`, `output_type`, `gates` and `description`. An alias cannot be
  overridden; override its canonical name. A file with `code_steps` replaces the whole
  registry. Problems come as issues with `path` and `code` (`unknown_key`,
  `alias_conflict`, `missing_key`, ...):

  ```yaml
  roles:
    review: {agent: critic}
    audit:
      agent: auditor
      output_type: ReviewOutput
      gates: [artifacts_exist]
      description: Audit the change against the security checklist
  ```
- Validate with `factory workflow check FILE --json` (`data.issues`, `data.steps`).

Example:

```yaml
name: plan-build-test
description: Plan and build, repair until the suite is green, and commit only green code
steps:
  - plan
  - build:
      harness: codex
      thinking: high
  - test_plan
  - repeat: {max: 3, until: test.passed}
    steps:
      - test
      - fix
  - commit:
      when: test.passed
accept: test.passed
```

## Procedures

### Check

`factory check [--repo PATH] [--offline] --json` only reads; it changes nothing in the
repository, the trace DB, the library or the home directory, and never fetches.

1. `data.state` is the state of the repo, read from base, first match wins:
   - `installed`: `.factory/manifest.yaml` is in base. No action.
   - `unsupported`: `.factory/config.yaml` or `.factory/agents.yaml` without a manifest,
     or an sssf installation in `adws/`. No action: HAIFA does not take over a
     configuration it did not install.
   - `uncommitted`: the configuration exists only in the working tree. Action
     `config_commit`.
   - `none`: no factory. Action `init`.

   `data.action` is what that state calls for (`config_commit`, `init` or `null`) and
   `data.onboarding` is the `onboarding` block of the manifest (who, when, from what),
   else `null`. The finding of the state carries the same action: `factory_missing`
   (`init`), `config_not_committed` (`config_commit`), `repo_unsupported` (info for
   `.factory/` without a manifest, error for sssf `adws/`) and `repo_installed` (info).
2. Outside a git repository (no `--repo`) only the machine and the library are checked:
   `data.in_repo` is `false` and `data.repo`, `data.state`, `data.action` and `data.base`
   are `null`. Inside a repository `data.in_repo` is `true`.
3. `data.findings` is a list of `{code, scope, severity, message, fix, action}`:
   - `scope: repo`: fix it in the repository and commit it to base (runs read base).
   - `scope: machine`: fix it on this machine (install a program, log in); nothing to commit.
   - `scope: library`: fix it in the library in `$HAIFA_HOME` (`factory library ...`).
   - `severity`: `error` (factory will not run), `warning` (it runs, but something is off),
     `info`.
   - `fix` says in words what to do. `action` names the fix (`init`, `update`, `export`,
     `config_commit`, `config_pull`) or is `null` for a manual fix.
     `config_commit` and `config_pull` are `factory config commit` and `factory config pull`
     (see Commit configuration); `init` is `factory init`, `update` is `factory update`
     (see Update from the library) and `export` is `factory config export`.
4. Findings and their fixes, by group:
   - Installation: `factory_outdated` (machine, error: the library needs a newer factory;
     `factory upgrade`).
   - Platform and tools: `unsupported_platform` (only macOS, Linux and WSL),
     `git_missing`, `git_identity_missing` (`git config --global user.name/user.email`),
     `uv_missing` (install uv), `node_missing` (a roster with pi needs node).
   - Harnesses: `harness_missing` (error for a harness the roster uses; outside a
     repository `info` for each of claude, codex and pi), `harness_login` (`claude auth
     status`, `codex login status`, `pi auth check --model M --json --no-refresh` failed;
     log in with `claude auth login`, `codex login` or `pi auth login`),
     `pi_model_unknown` (the model is not in `pi --list-models` or matches several;
     register it in pi or fix `model` in `.factory/agents.yaml`), `codex_not_isolated`
     and `pi_not_isolated` (global files the harness loads).
   - Hosting by `git_provider`: `gh_missing`, `gh_login` (`gh auth login`), `az_missing`,
     `az_devops_missing`, `az_login` (`az login` or the PAT variable), `hosting_skipped`.
   - Library: `library_missing` (`factory library clone URL` or `factory library init`),
     `library_dirty` (commit or discard in the library), `library_behind` (`factory
     library pull`), `library_unpushed` (`factory library push`), both as of the last
     fetch, and `seed_update_available` (`factory library seed`).
   - Environment: `env_file_mode` (`$HAIFA_HOME/env` is not 0600; `chmod 600`),
     `env_override` (one of `CLAUDE_SAFE_MODE`, `CLAUDE_MCP_CONFIG`,
     `CLAUDE_PERMISSION_MODE`, `CODEX_SAFE_MODE`, `CODEX_SANDBOX`, `PI_SAFE_MODE` is set;
     unset it unless you want it).
   - Items of base that are not `synced` with the library (AR23): `item_local` (info,
     `export`), `item_missing` (warning, `update`), `item_unknown` (warning, `export`),
     `item_outdated` (info, `update`), `item_modified` (info, `export`) and
     `item_diverged` (warning, `update`), and `update_available` (info, `update`: the
     library (or the seed) has new versions of items of the manifest, a missing item can
     be restored or a migration applies).
   - Repo: `workflow_not_in_repo` (the backlog names a workflow a repo with a manifest does
     not have in `.factory/workflows/`; add it or change the tasks), `roles_full_copy`
     (`.factory/roles.yaml` has `code_steps`; keep only the changed roles),
     and `unknown_thinking` (an agent's `thinking` is not a known level).
5. `data.ahead` / `data.behind` compare base with `refs/remotes/<remote>/<base>` as of the
   last `git fetch`; fetch first when you need the current state.
6. `--offline` skips the calls to the hosting and the harness logins (`gh auth status`,
   `az account show`, `claude auth status`, `codex login status`, `pi auth check`,
   `pi --list-models`); inside a repository the finding `hosting_skipped` says so.
7. Exit codes: 0 no errors (`ok: true`, warnings may still be listed), 1 errors
   (`checks_failed`, the report is in `data`), 2 only when `--repo` is not a git
   repository (`not_a_repository`).

### Add factory to an existing repo

`factory init` installs factory into a repository that has none. Install it into base with
one commit, after the user has seen the plan.

1. `factory check --json`: follow `data.action` and the findings' actions.
   `init` means a repo without factory. `config_commit` means configuration exists only
   in the working tree; commit it before continuing. State `installed` needs no init,
   and HAIFA does not take over a repo in state `unsupported`.
2. `factory init --dry-run --json [options]` writes nothing and returns the plan:
   - `data.files`: `path`, `action`, `diff` and `content`, including
     `.factory/manifest.yaml`.
   - `data.blockers`: `code`, `message` and `fix` when a command removes the blocker.
   - `data.warnings`: `code` and `message`.
   - `data.digest`, `data.exclude` and `data.validation`.
   - `data.detected`: `remote`, `base` (from `refs/remotes/<remote>/HEAD`, else the current
     branch), `provider` (`github`, `azure` with `azure.organization`, `project` and
     `repository`, or `local`) and `harnesses` (`installed` and `path` per harness CLI).
   - `data.available`: the `agents` (with default `harness`, `model` and `thinking`) and
     `workflows` (with their `agents`) of the library, or of the seed without a library.
     `default` marks the default choice.
   Options:
   - `--base BRANCH` and `--provider local|github|azure`. Azure takes `--azure-org`,
     `--azure-project` and `--azure-repo`, each falling back to the remote URL.
   - `--agents LIST`, `--workflows LIST` and `--bind AGENT=HARNESS[:MODEL[:THINKING]]` per
     agent (repeatable, for example `--bind builder=codex:gpt-5.5`).
   - `--backlog-dir`, `--specs-dir` and `--docs-dir`. `$specs_dir/` and `$docs_dir/` in
     `writes` become the chosen directories.
   - `--pr` plans a pull request; the direct-only blockers then do not apply.
   Example (choose agents and bindings for the intended workflow):
   `factory init --dry-run --json --agents builder,reviewer --workflows simple-sdlc
   --bind builder=codex --bind reviewer=claude`.
3. Show the user the files, the bindings, the blockers, the warnings and the digest.
4. When the user agrees: `factory init --commit --expect <digest> [-m TEXT] --json`. It is
   the same plan as one commit on base. Repeat all selection options (`--agents`,
   `--workflows`, `--bind`, directories and provider) from the preview; `--expect`
   validates the recomputed plan, it does not store those options. The commit is pushed before base moves, and the
   files reach the working tree only after the push (`data.commit`, `data.pushed`,
   `data.advanced`).
5. `plan_changed`: base or the plan changed since the preview. Run `--dry-run` again and
   show the user the new plan.
6. `push_failed`: nothing changed. The remote may refuse direct pushes. Ask the user, and
   only with their consent repeat it as `factory init --commit --pr --expect <digest>
   --json`. The commit then goes to `factory-init/<n>` with a pull request (`data.branch`,
   `data.pr`), and base and the checkout stay as they are.
7. Blockers (the commit refuses with the first one):
   - `already_installed`: factory is installed; run `factory update`.
   - `existing_config`: sssf or `.factory/` configuration without a manifest; HAIFA does
     not take over existing configuration.
   - `config_not_committed`: run `factory config commit`.
   - `dirty_paths`: the user moves or commits the listed files.
   - `invalid_plan`: see `data.validation.issues`, or `error.issues` on commit; change the
     bindings or the workflows.
   - `not_on_base`, `run_in_progress`, `base_behind` and `base_diverged`: as in Commit
     configuration.
8. Warnings never block:
   - `harness_missing`: a bound harness CLI is not on PATH; install it before runs.
   - `gitignore_dirty`: `.gitignore` has uncommitted changes, so the runtime lines go to
     `info/exclude` (`data.exclude`).
   - `foreign_content`: the backlog, specs or docs directory already has files.
   - `remote_note` and `invalid_item`.
9. After the direct commit (or after the installation PR is merged and base is
   synchronized), verify `factory check --json` and `factory backlog check --json`.
   Resolve findings before creating or running tasks.
10. Without `--dry-run` and `--commit`, `factory init` writes the files to the working tree,
   skips existing files unless `--force`, and commits nothing.

### Commit configuration

`factory config commit` commits the uncommitted shared `.factory/` files (the paths of
`factory config status`; never `local.yaml`) to base in one commit. The commit is built on
base without a checkout: other staged and unstaged work in the checkout stays.

1. `factory config commit --dry-run --json` returns the plan: `data.files` (`path`,
   `action` create/modify/delete, `diff` against base, `content`), `data.blockers`
   (`code`, `message`) and `data.digest`. The digest covers base, its sha and every
   file's old blob and new content; not the target and not the message.
2. Review the plan, then `factory config commit --expect <digest> [-m TEXT] --json`.
   `plan_changed` means base or the files changed since: run `--dry-run` again.
3. Direct target: the main checkout must be on base (`not_on_base`), no run may be in
   progress (`run_in_progress`), and with a remote the remote base must not be ahead
   (`base_behind`: run `factory config pull --json`) nor diverged (`base_diverged`: fix it
   by hand). The commit is pushed without force; `push_failed` changed nothing. The local
   base moves only after the push (`data.pushed`, `data.advanced`); when that move fails,
   `warnings` say so and `factory config pull` catches up.
4. `--pr`: the commit goes to a new branch `factory-config/<n>`, which is pushed and gets a
   pull request (`data.branch`, `data.pr`); base and the checkout stay as they are.
5. Nothing to commit: `data.committed: false`.
6. `factory config pull --json` fast-forwards the local base to the remote base
   (`data.updated`, `data.before`, `data.after`). `base_diverged`, `dirty_base`,
   `run_in_progress` and `no_remote` change nothing.

### Plan -> backlog

There is no importer; converting a plan is this procedure (D12).

1. Read the plan (for example `implementation-plan` output: an index plus linked, sharded
   markdown files; follow the links).
2. Map every module of the plan to a project: a project directory
   `<backlog_dir>/<project-id>-<slug>/` with
   `{{index_file}}`, and every step to a step directory inside it with its own
   `{{index_file}}`. Create them with
   `factory backlog add --id CODE --title TEXT [--body TEXT] --json` (a project) and
   `factory backlog add PROJECT --id CODE --title TEXT --json` (a step). Give only the short
   code (`S03`); the id is always composed from the parent's id: `M01-S03`, in the directory
   `S03-<slug>`. Put shared defaults (`workflow`, `writes`, ...) into
   the project or step index with `factory backlog edit ID --workflow NAME --writes PATH ...
   --json` (`--clear KEY ...` removes a key; keys it does not know stay as they are). The
   project id is any short code; keep the module's code from the plan (e.g. `M01`).
   An invalid code (letters, digits, `.` and `_`, no `-`) or a duplicate is rejected with
   `invalid_id` or `backlog_invalid` (`error.issues`: `duplicate_id`) and nothing is written.
3. Add each task, in dependency order:
   `factory task add STEP TITLE [--id CODE] --writes PATH ... --depends-on ID ... --body TEXT --json`
   (`--id T05` makes `STEP-T05`; without it the next free `T<nn>`)
   (or write the task files directly in the format above). `--body` is the text of
   `## Zadání`: what, where, "done means", out of scope, hard constraints.
4. Add references later with `factory task link ID --depends-on ID ... --json`.
5. Run `factory backlog check --json` until `ok` is true, then `factory backlog list`.
6. `factory backlog commit --json` commits and pushes it to base; runs read the
   backlog from base.

Example with the default project → step → task hierarchy:

```bash
factory backlog add --id M01 --title "Core" --json
factory backlog edit M01 --workflow simple-sdlc --writes src/ tests/ --json
factory backlog add M01 --id S01 --title "API" --json
factory task add M01-S01 "Health endpoint" --id T01 --body "Add GET /health; cover HTTP 200 in tests/api." --json
factory backlog check --json
factory backlog commit --json
```

Put common settings at project level, narrower defaults on the step and only
exceptions on the task; the nearest value wins.

### Run

1. `factory task list --status ready --json` lists the tasks that can start.
2. `factory task run ID [--note TEXT] [--auto] --json` runs one task in its own worktree on
   a new branch `factory/<task-id>-<n>` and opens a pull request. `--harness NAME`,
   `--model NAME` and `--thinking LEVEL` put every agent on them for this run only (step
   overrides of the workflow still win; with `--auto` only the first run gets them). An
   unknown harness or thinking level, or a model the harness rejects, is `invalid_override`.
3. Read `data.run.state`, `data.pr` (the pull request), `data.pr_error` and `data.chain`.
4. On failure (`run_failed`) the worktree and branch are kept; re-run with `--note` to tell
   the agents what to fix.
5. Auto-continue (`--auto`, or `auto_continue: true` in the project or step
   `{{index_file}}`, set with `factory backlog auto-continue ID --on|--off|--inherit`):
   after a run opens its PR, the next ready task of the step, then of the project, starts.
   Without `--auto` the chain continues only after a task with `auto_continue: true` and
   starts only tasks with `auto_continue: true`; `--auto` starts any task.
   The dashboard's kanban sets the order of ready tasks (taken first) and can exclude a
   task from auto-continue (skipped as `excluded`, with `--auto` too; it still runs when
   started by hand).
   Tasks it skips carry a reason ({{skip_reasons}}); the chain stops with
   {{stop_reasons}} (`data.chain.stop`, `data.chain.waiting`). The chain approves and
   merges nothing except through `auto_merge` (next point).
6. Auto-merge (`auto_merge: true`, inherited project -> step -> task; set it with
   `factory backlog auto-merge ID --on|--off|--inherit` or on a task with
   `factory task edit ID --auto-merge on|off|inherit`, e.g. off for a task that changes
   the guard or permissions): after the run its PR is approved and merged like
   `factory task approve` (`merged_by: auto-merge` in `task_prs`) only when the run
   `succeeded`, the workflow has a review phase whose last review approved with no blocking
   or unmet item, the PR merges cleanly and none of its checks is red. A workflow without
   review is never merged automatically. Otherwise `data.auto_merge` (`merged`, `code`,
   `reason`) says why and the PR waits for `factory task approve`. With auto-continue the
   next task starts only after the merge; a PR that was not merged stops the chain
   (`not_merged`).
7. Parallel runs (`max_parallel_runs` in `.factory/config.yaml`, whole number ≥ 1,
   default 1): with 1 the chain runs one task after another. Above 1 the chain keeps up to
   that many runs at once (each a separate `factory task run` process) and refills a slot
   whenever a run ends. A task starts only when its effective `writes` do not overlap (path
   prefix) the `writes` of a running run nor the files of an open, unmerged PR; otherwise it
   is skipped as `writes_overlap` (which run or PR, which paths). A task whose `writes` cover
   the whole repo or a whole package (e.g. `src/`) runs alone (`exclusive`,
   `data.chain.exclusive`). The dashboard's Runs screen shows the chain, its free slots and
   the skipped tasks.

### Pause, resume and stop

Run states in `data.run.state` and `task_runs`: `running`, `succeeded`, `failed`,
`aborted` (its process is gone), `stopped`. A running run also has `pause`: `null`,
`pausing` or `paused`; a run with `pause: paused` is shown in state `paused`
(`factory task show`, the dashboard).

1. `factory task pause ID [--run RUN_ID] --json` asks the running run to pause. The phase in
   progress (an agent, a test) runs to its end; meanwhile `pause` is `pausing`. Before the
   next phase the run turns `paused` and waits: its process stays alive, no further phase
   starts. Nothing is frozen. A pause asked for in the last phase is dropped when the run
   finishes. Errors: `run_not_running` (the task has no running run, or it is finished),
   `run_already_paused` (`pausing` or `paused` already); exit 2, nothing changed.
2. `factory task resume ID [--run RUN_ID] --json` lets a paused run go on with its next
   phase in the same worktree and branch (a pending `pausing` is dropped). Errors:
   `run_not_running`, `run_not_paused` (the run has no pause); exit 2, nothing changed.
3. A paused run keeps its place among the parallel runs (`max_parallel_runs`) and blocks
   another run of its task; an auto-continue chain waits until it ends.
4. `factory task stop ID --json` stops a running or paused run (state `stopped`); its
   worktree and branch stay. A pause does not survive a restart of the machine: the run's
   process is gone and the run becomes `aborted`.

### Review

1. `factory task show ID --json` gives the task, its body, its runs and its PRs.
2. Review the PR diff through the hosting provider (`gh pr diff`, `az repos pr`, or
   `git diff` of the branch in local mode).
3. Then approve, or return with a note.

### Approve

1. `factory task approve ID --json` adds a commit with `status: done` and a
   `{{runs_heading}}` line to the PR, merges it, updates base from the remote and removes
   the branch's worktrees.
2. On `conflict`, resolve first (below), then approve again.
3. Note (D11, temporary): no approve review is sent to the hosting yet.

### Publish

`factory task publish ID --json` repeats the end of `task run` for the task's last
succeeded run that has no pull request (its push or PR failed, `pr_failed`): it pushes the
branch and opens the PR with the body kept from the run, recorded in `task_prs` as after a
run. When the hosting already has an open PR for the branch that factory does not know, it
is adopted (recorded, its body updated) instead of opening a second one. A push failing on
the network (RPC failed, HTTP2 framing, remote end hung up, timeout) is retried a few times
with a pause; a rejected push (non-fast-forward, rights) is not.

- `data.run`, `data.pr`, `data.pr_error`: as for a run.
- `no_succeeded_run` (exit 2): no succeeded run; nothing changed.
- `pr_exists` (exit 2): the task or the branch already has a PR; nothing changed.
- `already_running` (exit 2): a run of the task is in progress; nothing changed.
- `pr_failed` (exit 1): push or PR failed again; `data.pr_error` says why, retry later.

The dashboard shows `pr_error` of a succeeded run without a PR and a button that publishes it.

### Return

`factory task return ID --note TEXT --json` starts a new run on the same branch with the note
in the prompt; the pull request is updated. Read `data.run` and `data.pr` as for a run.

### Resolve

`factory task resolve ID --json` rebases the PR branch onto the current base. On a conflict
an agent changes only the conflicted files. Conflicted files inside a generated output
(`generated:` in `.factory/config.yaml`, entries `{path, command, timeout}`) are not the
agent's: the code step `rebuild` runs the output's `command` and the rebuilt output is
committed with the resolution. Then the suite runs and the branch is
force-pushed with a lease and the PR updated. On failure the branch stays as it was before
the rebase. Then approve.

### Sync and cleanup

- `factory backlog sync --json` finds task PRs merged outside factory and opens one sync PR
  that marks them done (never commits to base, never merges it).
- `factory task clean --json` removes worktrees of merged, closed or abandoned runs.

### Upgrade

`factory upgrade BUNDLE [--dry-run] --json` installs a newer HAIFA from a distribution
bundle `haifa-<version>.zip`. `BUNDLE` is a path or a URL; only `https` and `file` URLs are
downloaded (into a temporary directory), any other scheme is `invalid_url`, a failed
download `download_failed`.

1. An editable install (development from the HAIFA repo) is refused with
   `editable_install`; update it with `git pull` instead.
2. The bundle is unpacked into a temporary directory and every file listed in `SHA256SUMS`
   is verified. A broken zip, a missing `SHA256SUMS`, a listed file that is missing, or no
   `aifactory` wheel or `constraints.txt` is `bundle_invalid`; a wrong sum is
   `checksum_mismatch` (`data.file`, `data.expected`, `data.actual`).
3. The target version is read from the wheel's metadata. Not newer than the installed
   `__version__` is `up_to_date` (exit 1, `data.current_version`, `data.target_version`);
   nothing is installed.
4. `data` has `current_version`, `target_version`, `wheel`, `min_factory_version` of the
   library (`null` without a library or minimum), `command` (argv), `dry_run`,
   `installed`, `stdout`, `stderr` and `restart_dashboard`. A target below the library's
   `min_factory_version` adds a warning.
5. `--dry-run` stops here and runs nothing. Without it the command
   `uv tool install --force <wheel> --constraints constraints.txt` runs in the unpacked
   bundle: `uv_missing` when uv is not on PATH, `upgrade_failed` (exit 1, uv's output in
   `data`) when uv fails; the old version stays. On success `installed` is `true` and
   `data.next` reminds to restart a running dashboard (`factory obs`).
6. Then see "After a HAIFA upgrade" below for the library seed.

### Library

The library is a git repository in the home directory, `$HAIFA_HOME/library`
(`HAIFA_LIBRARY` overrides the path). `library.yaml` holds `format: 1`, `id` (uuid4),
`name`, `min_factory_version` and `seed` (`type/name` to the seed version the item came
from). Items: `agents/<name>/{agent.yaml,system.md,user.md}`, `workflows/<name>.yaml`,
`skills/<name>/` (with `SKILL.md`) and `extensions/<name>/` (with `<name>.ts`).

1. `factory library init [--name N] --json` creates it from the seed in one commit
   (`library_exists`, `git_identity_missing`).
2. `factory library list [--type T] --json` lists the items of HEAD with `version`,
   `short_version` (8 characters) and the date and author of the last change.
   `factory library show TYP JMENO [--version V] --json` returns `files` and `history`
   (`n`, `version`, `commit`, `date`, `author`). Both read HEAD, never the working tree;
   the history is cached in `$HAIFA_HOME/cache/` and recomputed when the cache is gone.
3. `factory library import CESTA --type agent|workflow|skill|extension [--name N]
   --dry-run --json` validates a folder or file under the user's home directory
   (`outside_home`, also for a symlink leading out of it; `invalid_item` with
   `error.issues`) and returns the plan: `items[].action` (`create`, `update`,
   `unchanged`), `files` with diffs and `digest`. Review it, then run the same command
   without `--dry-run`. Equal content is a no-op (`committed: false`); new content under an
   existing name becomes the next version of that item.
4. A write holds `$HAIFA_HOME/library.lock`, so concurrent writes run one after another.
   It refuses a library with uncommitted changes (`library_dirty`; commit or discard them
   in the library yourself), commits on HEAD without a checkout and fast-forwards the
   branch and working tree. Nothing is forced and history is never rewritten.

#### Sharing the library

A team shares the library through a git remote, stored as `origin` without user and
password (`https://user:secret@host/x` is kept and shown as `https://host/x`; git asks its
credential helper).

1. `factory library init --remote URL --json` pushes the new library to an empty remote
   before it exists locally (`remote_not_empty`, `push_failed`; nothing is created).
   Others join with `factory library clone URL [--branch B] --json` (`library_exists`,
   `clone_failed`, `invalid_library` when `library.yaml` lacks `format`, `id` or `name`).
2. `factory library status [--fetch] --json` returns `library`, `id`, `name`, `remote`,
   `branch`, `ahead` and `behind` (from the last fetched refs unless `--fetch`),
   `last_fetch`, `dirty` with `uncommitted`, `min_factory_version`, `factory_version` and
   `compatible` (a warning when the installed factory is older).
3. `factory library pull --json` only fast-forwards (`library_dirty`, `library_diverged`).
   `factory library push --json` pushes local commits, never forced (`library_behind`,
   `library_diverged`, `push_failed`); `no_remote` without a remote.
4. A write to a shared library fetches first. Behind the remote it is `library_behind`
   (`data.fix` is `factory library pull`; run it, then repeat the write); diverged it is
   `library_diverged` (resolve it in the library with git, never by force). The commit is
   built on HEAD without a checkout and pushed without force before the local branch moves,
   so `push_failed` leaves local refs, index and files exactly as they were.

#### After a HAIFA upgrade

A new HAIFA can ship new versions of the seed agents and workflows. `seed` in
`library.yaml` records the seed version each item last took.

1. `factory library status --json` has `seed_update_available` (with `seed_updates`, the
   `type/name` list) and a `seed_update_available` warning when the installed seed has
   versions the library's `seed` lacks.
2. `factory library seed --dry-run --json` returns the plan. `items[].action`: `create`
   (missing in the library, added), `update` (the team did not change it since the last
   seed, replaced), `unchanged` (the library already has the seed version) and `kept` (the
   team changed it; `items[].diff` shows what the seed would change). Review it, then run
   it without `--dry-run`. `seed` in `library.yaml` is set to the installed seed.
3. A `kept` item stays as the team made it. To take the seed version anyway, run
   `factory library seed --take TYP/JMENO --json` (repeatable; action `take`; `not_in_seed`
   when the seed lacks it). Items the seed no longer has are never deleted.
4. The write goes like `import` (lock, `library_dirty`, fetch, push). A second run without a
   new seed commits nothing (`committed: false`).
5. Then run `factory update` in every repo to bring the new library versions into
   `.factory/`.

### Manifest and item states

`.factory/manifest.yaml` records where the repo's items came from. A repo without it is
format 0 and runs as before. Keys: `format` (1), `written_by` (the HAIFA version),
`library` (`id`, `name`, `remote`; `null` when the items came from the seed), `onboarding`
(`source` `init`, older manifests may carry `sssf` or `pre_library` and still load;
`source_commit`, `at`, `by`, `factory`,
`library_commit`; written once) and `items` by type (`agents`, `workflows`, `skills`,
`extensions`), each `name in the repo: {item, version}`. It is shared configuration:
`factory config status` reports it and `factory config commit` commits it.
A run reads only `format` from this provenance record; it executes the committed
repository configuration and prompts, without fetching items from the library.

1. A `format` newer than the installed HAIFA stops `factory config show`, `factory check`
   and every run before it starts with `format_unsupported`; run `factory upgrade`.
2. A repo with a manifest runs workflows only from `.factory/workflows/` in base, so a task
   runs the same on every machine. Only the internal `resolve` and `resolve-reviewed` come
   from the package. A missing workflow is `unknown_workflow`; add it with
   `factory config add workflow <name>`.
3. `factory config items [--repo PATH] [--base [REF]] --json` returns `data.items[]` with
   `type`, `name` (in the repo), `item` (the library item), `state`, `repo_version` (R),
   `manifest_version` (M) and `library_version` (L, the library head or, without a library,
   the seed), plus `data.library.source` (`library` or `seed`). Without `--base` it reads
   the working tree. States, the first matching wins:
   - `local`: not in the manifest.
   - `missing`: in the manifest, but its files are gone.
   - `synced`: R = L.
   - `unknown`: M is not in the library item's history.
   - `outdated`: R = M and the library moved on.
   - `modified`: R ≠ M and the library did not move.
   - `diverged`: both changed.

### Items of the repo: config add / set / remove

```bash
factory config add workflow solo --json            # workflow + the agents of its steps
factory config add agent builder --as builder2 --model claude-opus-5-5 --thinking high --json
factory config add skill lint --json               # .claude/skills/lint/ + .agents/skills/lint/
factory config set agent builder --thinking high --tools read,bash --color '#112233' --json
factory config remove workflow solo --prune --json
```

1. Modes, as `factory init`: `--dry-run` returns the plan (`data.files`, `added`, `kept`,
   `removed`, `bindings`, `blockers`, `validation`, `digest`) and writes nothing. Without
   an option the plan is written to the working tree only (nothing committed; commit it
   later with `factory config commit`). `--commit [--pr] [-m TEXT]` makes it one commit on
   base (pushed before base moves) or a PR from `factory-config/<n>`. Review first:
   `--dry-run` (with `--commit` for the commit plan), check it, then repeat the command
   with `--expect <digest>`; a changed plan is `plan_changed`.
2. `add` takes the item from the library HEAD (the seed without a library). Closure: a
   workflow brings the agents of its steps, an agent the skills and extensions of its
   defaults; what is already in the repo stays (`kept`, reason `present`). Skills go to
   `.claude/skills/<name>/` with a copy in `.agents/skills/<name>/`. A new agent slot gets
   the item's defaults, overridden by `--harness`, `--model`, `--thinking`.
3. A slot with other content is `slot_taken`: pick another one with `--as NEW` (agents and
   workflows). The same content is a no-op (`changed: false`).
4. `set agent SLOT` changes only the bindings in `agents.yaml`; comments and key order
   stay. `--tools`/`--writes` take comma lists (`-` removes the key). An unknown
   `--thinking` is `invalid_value`.
5. `remove` refuses an item in use (`in_use`, `data.used_by`): an agent named by a workflow
   or `roles.yaml`, a workflow named by a backlog task in base, a skill or extension bound
   by another agent. `--prune` also removes manifest dependencies nobody else uses.
6. Blockers: `run_in_progress`, `invalid_plan` (working tree); `dirty_paths`,
   `invalid_plan`, `not_on_base`, `base_behind`, `base_diverged` (`--commit`). A repo
   without a manifest is `not_onboarded`: run `factory init`.

### Repo and library: config export / revert / diff

```bash
factory config diff agent builder --json                # repo vs manifest version and vs head
factory config export agent builder --dry-run --json    # library files + manifest, digest
factory config export agent builder --expect <digest> --json
factory config export agent builder --as builder-strict --commit --json
factory config revert agent builder --to manifest --json   # or --to head
```

1. `export` writes the repo copy into the library, then records the library item and the
   version in the manifest. An item of the manifest becomes the next version of its
   library item; `--as NEW` (agents and workflows) or a `local` item becomes a new library
   item. A library item of that name with other content is `item_exists` (fix `--as NEW`).
2. When the library head moved on since the manifest version and the repo copy differs,
   export is `library_changed_since`: take the library version with `factory update`, or
   export the copy as a new item with `--as NEW`.
3. Order: the library first (fetch, push without force), then the repo (working tree,
   `--commit` or `--commit --pr`, as `config add`). A rejected library push
   (`push_failed`, `library_behind`, `library_diverged`, `library_dirty`) leaves the repo
   untouched. When the repo write fails after the library push, `data.library_commit`
   names the unused library version: run the same export again and it only connects it
   (`data.export.action` `connect`).
4. Move a good agent to another repo: `factory config export agent NAME [--as NEW]` in
   this repo, then `factory config add agent NAME [--as SLOT]` in the other repo (both
   use the same library; `factory library pull` there first when it is shared).
5. `revert --to manifest` (default) puts the copy back to the manifest version from the
   library history (`unknown_version`, state `unknown`, when the history lacks it: use
   `--to head`); `--to head` takes the library head and moves the manifest version. The
   bindings in `agents.yaml` stay. A local item is `unknown_item`.
6. `diff` only reads: `data.manifest` and `data.head` list `files[]` with `status` and a
   unified `diff` (library version first, then the repo copy).

### Update from the library

```bash
factory update --dry-run --json                       # the plan: items, files, migrations, digest
factory update --expect <digest> --json               # write it to the working tree
factory update --take agent/builder:system.md --json  # take the library version of one file
factory update --take agent/builder --json            # ... or of every file of the item
factory update --merge workflow/solo --json           # git merge-file of the conflicting files
factory update --migrate m001 --json                  # run a listed migration
factory update --commit [--pr] [--expect <digest>] [-m TEXT] --json
```

1. `factory update` brings new versions of the items of `.factory/manifest.yaml` from the
   library head (the seed without a library). It never overwrites a file the repo changed
   unless you pass `--take` or `--merge`, and it never merges text on its own: ask the
   user before you pass either.
2. The unit is a file: an agent's `purpose` (its roster entry), `system.md` and
   `user.md`; a workflow's file; every file of a skill or extension, also added and
   deleted ones. base is the manifest version (from the library history), ours the repo
   copy, theirs the library head. `data.update.items[].files[].status`:
   - `same`: ours = theirs, nothing to do;
   - `take`: ours = base, theirs is written;
   - `keep`: theirs = base, the repo change stays;
   - `conflict`: both changed; ours stays, `ours_diff` (base -> repo) and `theirs_diff`
     (base -> library) show both sides, warning `update_conflict`;
   - `taken`: `--take TYPE/NAME[:FILE]` took theirs;
   - `merged`: `--merge TYPE/NAME` took the result of `git merge-file`; when it has
     conflicts or the merged item is not valid the command fails with `merge_conflict`
     and writes nothing;
   - `unknown`: the manifest version is not in the library history (item state
     `unknown`), there is no base; `diff` shows ours against theirs, ours stays, warning
     `update_unknown`, `--take` takes theirs (`--merge` is `invalid_value`);
   - `restore`: the item is `missing`; its missing files come back.
3. `data.update.items[].action` sums the item up: `same`, `update`, `keep`, `conflict`,
   `unknown`, `restore`, `absent` (the library no longer has the item, warning
   `item_not_in_library`; it stays as it is).
4. The same plan moves every manifest entry to the library head, sets `written_by` to the
   installed HAIFA, restores the missing prompts of agents declared in `agents.yaml`
   (`data.update.restored`; warning `prompt_missing` when the library has no such agent)
   and the runtime lines of `.gitignore` (`data.update.gitignore.added`). A skill that
   changes is copied again to `.agents/skills/`.
5. Migrations: `data.update.migrations[]` lists each detected migration with `id`,
   `title` and `diff` (warning `migration_available`); it runs only with `--migrate ID`.
   `m001` changes `levels: [module, step, task]` in `.factory/config.yaml` to
   `[project, step, task]`, comments kept. A migration that does not apply any more is
   `migration_not_needed`. The second run finds nothing to migrate.
6. Modes as `config add`: `--dry-run` (the plan and its `digest`), the working tree (the
   default; `run_in_progress` blocks; `factory config commit` commits it later) and
   `--commit [--pr]` (one commit on base or a pull request; `dirty_paths`,
   `plan_changed`, `invalid_plan`). Nothing to change: `changed` false.
7. Refused: `not_onboarded` (no manifest in base; `data.fix` is `factory init` for a repo
   without `.factory/` or `adws/`, HAIFA does not take over the others), `config_not_committed` (the
   manifest is only in the working tree: `factory config commit`), `format_unsupported`
   (`factory upgrade`), `library_mismatch` is a warning (another library than the
   manifest's).

### Repo instructions and skills

Agents run as if their harness had been started from the CLI in the repository. The
agent's role stays in its system prompt (`--system-prompt`, codex `developer_instructions`);
the repo's instructions and skills ride along through each harness's native mechanism:

- claude reads `CLAUDE.md`, `.claude/settings*.json` and `.claude/skills/`
  (`--setting-sources project,local`); nothing from `~/.claude` (hooks, plugins, skills,
  agents, CLAUDE.md). MCP stays off (`--strict-mcp-config`).
- codex reads `AGENTS.md` and `.agents/skills/`; `--ignore-user-config` leaves out
  `~/.codex/config.toml`.
- pi reads `AGENTS.md`, `CLAUDE.md` and `.agents/skills/` with project trust granted
  (`--approve`); personal skills, extensions and prompt templates are left out
  (`--no-skills`, `--no-extensions`, `--no-prompt-templates`).

A skill has its source in `.claude/skills/<name>/`; edit it there. `.agents/skills/` is
its exact copy for codex and pi, with no symlinks. After a change run
`factory skills sync [--repo PATH] --json` (`data.added`, `data.updated`, `data.removed`;
`skills_sync_failed` when it cannot write) and commit both trees. `factory check` compares
them in base and reports `skill_mirror_missing`, `skill_mirror_differs` and
`skill_mirror_extra` (scope repo).

Global files of the operator a harness cannot leave out are reported by `factory check` as
`codex_not_isolated` (`~/.codex/AGENTS.md`, `AGENTS.override.md`, `~/.codex/skills`,
`~/.agents/skills`) and `pi_not_isolated` (`AGENTS.md`, `AGENTS.override.md`, `CLAUDE.md`,
`APPEND_SYSTEM.md` in `~/.pi/agent`), scope machine.

`CLAUDE_SAFE_MODE=1`, `CODEX_SAFE_MODE=1` and `PI_SAFE_MODE=1` restore full isolation
(claude `--safe-mode`, codex `project_doc_max_bytes=0`, pi without context files, skills,
extensions and project trust). The default is off: native repo loading.

Registered repositories: `factory library where TYPE NAME --json` reports slots, states
and versions, including `repo_missing` for missing folders. `factory update --repos
all|ID,ID [--item TYPE/NAME]` and `factory config add TYPE NAME [--agent A] --repos
all|ID,ID` plan and execute each repository sequentially. Use `--dry-run --commit`
to review each digest, then `--commit --expect ID=DIGEST` for every selected repo
(option repeatable), optionally `--pr` and `-m TEXT`. There is no transaction: inspect
`data.repos[].status`, `plan`, `result`, `error` and `data.partial`; blocked or failed
repos are skipped while others continue. Repeating an operation is idempotent.
Without the registry, these commands return `registry_missing`.

For `config add` and `update` in PR mode, the plan digest identifies the branch.
Repeating the same plan returns the existing commit, branch and open PR, including
a retry of a partially successful batch. Commit message changes do not create another
PR for the same contents. An edited published branch is skipped with `plan_changed`;
base and the working tree stay unchanged.

