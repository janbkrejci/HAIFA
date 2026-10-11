# HAIFA-S01-T12: `factory init` with a preview, one commit to base and per-agent bindings

## Goal

Extend `factory init` (HAIFA-S04-T01, `aifactory/src/aifactory/library/install.py`) with two new modes the dashboard will use on a repo without factory:

- **preview**: `factory init --dry-run --json` returns the full plan (files with content including the manifest, blockers, warnings, `digest`), the detected values `detected` and the offer `available`.
- **commit**: `factory init --commit [--pr] [--expect DIGEST] [-m TEXT] --json` makes the same plan as one commit on base via the M7 publish path (`aifactory/src/aifactory/providers/publish.py`, used today by `factory config commit` in `config/commit.py`). Nothing is written to the working tree before the push has succeeded.

Without `--dry-run`/`--commit` (the **legacy mode**) the behaviour of HAIFA-S04-T01 stays: files are written to the working tree, existing ones are skipped (unless `--force`), nothing is committed. Existing tests in `aifactory/tests/library/test_library_install.py` must still pass unchanged.

## Hard constraints (from the task)

- `init` without `--commit` commits nothing; without `--force` it overwrites nothing.
- `init` never writes to the library or `$HAIFA_HOME`.
- Do not touch `.factory/`, `vendor/`, `prototype/` of the HAIFA repo itself. Only `aifactory/`, `justfile` and the spec/doc paths are allowed.
- Tests never call a model or the network (bare local remotes, fake `gh` from `aifactory/tests/providers/gh_fake.py`).

## Decisions

- **D1 Modes and options.** New options on `factory init`: `--dry-run`, `--commit`, `--pr`, `--expect DIGEST`, `-m/--message TEXT`, `--provider {local,github,azure}` (default now `None`), `--azure-org`, `--azure-project`, `--azure-repo`, `--backlog-dir DIR`, `--specs-dir DIR`, `--docs-dir DIR`.
  - `--dry-run` (with or without `--commit`) = preview. `--pr` is allowed with `--dry-run` (it sets `target: pr` and drops the direct-only blockers, exactly like `config commit --dry-run --pr`).
  - `--expect`, `-m` without `--commit`, `--pr` without `--commit`/`--dry-run`, `--expect` together with `--dry-run`, and `--force` together with `--dry-run`/`--commit` → `conflicting_options` (exit 2, existing code).
  - `--azure-*` with an explicit `--provider` other than `azure` → `conflicting_options`.
  - `--agents`, `--bind`, `--workflows`, `--backlog-dir`, `--specs-dir`, `--docs-dir`, `--provider`, `--azure-*`, `--base` apply in all three modes.
- **D2 Defaults per mode.** Legacy mode keeps the S04-T01 defaults (base = current branch, provider `local`) so its output does not change. Preview and commit modes default to the **detected** values (`detected.base`, `detected.provider`, `detected.azure`). Explicit options always win. `--provider azure` takes org/project/repo from `--azure-*`, falling back per field to `detected.azure`; any field still missing → `invalid_value` ("--provider azure needs --azure-org, --azure-project and --azure-repo"). The config gets `azure: {organization, project, repository}` (see `AzureSettings` in `config/settings.py`).
- **D3 Detection** (new module `aifactory/src/aifactory/library/detect.py`, pure functions + small git reads, no network):
  - remote: `origin` when it exists, else the first name of `git remote` (sorted), else none.
  - base: `git symbolic-ref --quiet refs/remotes/<remote>/HEAD` → strip `refs/remotes/<remote>/` (`base_source: "remote_head"`); else the current branch (`"branch"`); else `null` (detached, `base_source: null`).
  - provider from the remote URL via `parse_remote_url(url) -> RemoteInfo(provider, github: {owner, repo} | None, azure: {organization, project, repository} | None)`:
    - `github`: host `github.com` in `https://github.com/o/r(.git)`, `https://user@github.com/o/r`, `ssh://git@github.com/o/r.git`, `git@github.com:o/r.git` (scp form). Strip a trailing `.git` and `/`.
    - `azure`: `https://[user@]dev.azure.com/{org}/{project}/_git/{repo}`; `git@ssh.dev.azure.com:v3/{org}/{project}/{repo}` and `ssh://git@ssh.dev.azure.com/v3/{org}/{project}/{repo}`; `https://{org}.visualstudio.com/[DefaultCollection/]{project}/_git/{repo}`; `{org}@vs-ssh.visualstudio.com:v3/{org}/{project}/{repo}` (and its `ssh://` form). Percent-decode segments (`My%20Project` → `My Project`). Org is the bare name (not the URL).
    - anything else (other hosts, file paths, bare remotes in tests), or no remote → `local`.
  - harnesses: for each name in `harness.CLI_BINARIES`, whether its binary (env override var, else default name) is on PATH. Add `installed_path(name) -> str | None` in `aifactory/src/aifactory/harness/check.py` (just `shutil.which`, **no** `--version` subprocess) and reuse it from `check_harness`.
  - `detected` JSON: `{remote, remote_url (redacted with providers.git.redact_url), base, base_source, provider, github, azure, harnesses: {claude: {installed, path}, codex: {...}, pi: {...}}}`.
- **D4 `available`.** Items of the source the plan uses (library HEAD, else the seed — the existing `_Source` rule, never mixed): `{source, library, agents: [{name, purpose, version, harness, model, thinking, default}], workflows: [{name, version, agents, default}]}`. `harness/model/thinking` are the item `defaults`; `default` is true for `DEFAULT_AGENTS`/`DEFAULT_WORKFLOWS`; `agents` of a workflow come from `_workflow_agents`. Library listing: enumerate `item_paths(tree_files(root, head))` (or `store.list_items`) then `read_items`; seed: `seed_items()`. Invalid library items are skipped in `available` (with a warning), not fatal.
- **D5 Bindings per agent (D24).** Unchanged `parse_binding`/`_agent_entry` logic; it applies in all modes. After the roster is final, each distinct harness used by a roster entry whose binary is not installed adds warning `harness_missing` (`"agent builder uses harness codex, whose CLI codex is not on PATH"`). It never blocks.
- **D6 Plan files.** Refactor `init_repo` so file rendering is shared: `_render(root, choice, source, at) -> dict[str, bytes]` producing `config.yaml` (the S04-T01 keys `base, git_provider, backlog_dir, specs_dir, docs_dir`, plus `remote: <name>` only when the detected remote is not `origin`, plus `azure` when provider is azure), `agents.yaml` (writes expanded with the chosen `specs_dir`/`docs_dir` through `ProjectSettings(...)` → `roster_entry`/`expand_writes`, which already replace `$specs_dir/`/`$docs_dir/`), prompts, workflows, manifest. Validate `--backlog-dir/--specs-dir/--docs-dir` by building `ProjectSettings` (catch `ValidationError` → `invalid_value`).
  - Plan mode adds `<backlog_dir>/.gitkeep` **only when the backlog directory exists neither in the base tree nor on disk**. (Legacy mode keeps its current behaviour.)
  - `.gitignore` in plan mode: if `.gitignore` has no uncommitted changes (working-tree bytes equal the blob in base, or both absent) and lines from `GITIGNORE_LINES` are missing in base's `.gitignore` → the plan includes `.gitignore` (`create`/`modify`, base content + missing lines, same append rule as `_gitignore`). If `.gitignore` has uncommitted changes (modified, or untracked file not in base, or deleted) → `.gitignore` is not in the plan; instead `data.exclude = {"path": "<git common dir>/info/exclude", "lines": [missing lines]}` (lines already present in `info/exclude` are omitted; `null` when nothing to add) and warning `gitignore_dirty` says the runtime lines go to `info/exclude`.
  - Build `PlannedFile`s from in-memory bytes: new helper in `publish.py`: `plan_contents(root, base_sha, contents: Mapping[str, bytes]) -> list[PlannedFile]` (mode `100644`, diff against `git.blob_at`, skip paths whose base blob is identical; reuse logic from `plan_files`).
- **D7 Digest must be stable.** The manifest has `onboarding.at = _now()`, which would change the digest every second. Compute the digest with `publish.plan_digest(base, base_sha, digest_files)` where `digest_files` are the planned files with the manifest rendered with `at=""` (helper `_render(..., at="")` or replace the manifest file before hashing). The committed manifest gets the real time. Also include the `exclude` lines in the digest: hash them as a pseudo file `"\0exclude"` with content `"\n".join(lines)` — simplest: append a synthetic `PlannedFile(path=":info/exclude", action="create", ..., content=...)` only to the digest list. Document it in the module docstring.
- **D8 Blockers** (plan mode; listed in `data.blockers`, the commit refuses with the first one, exit 2, `data` = the plan). Order:
  1. `already_installed` — manifest committed in base (or HEAD). Message advises `factory update`.
  2. `existing_config` — sssf `adws/adw_sssf_config/` (base tree or disk), or `.factory/config.yaml`/`.factory/agents.yaml` in base or working tree, while there is no manifest in base nor in the working tree. Advises `factory onboard`.
  3. `config_not_committed` — `.factory/manifest.yaml` exists on disk but not in base (an earlier legacy `init`; with `config.yaml` but no manifest it is `existing_config`). Advises `factory config commit`.
  4. `dirty_paths` — a planned path exists on disk with bytes different from the planned content (message lists the paths). A path whose disk content already equals the plan is fine.
  5. `invalid_plan` (new code) — validation of D9 failed; its `issues` go to `error.issues` on commit and to `data.validation.issues` in the plan.
  6. M7 blockers through the same code as `plan_config_commit`: `not_on_base` (direct only), `run_in_progress` (direct only, see D10), `base_behind`/`base_diverged` (direct only, when a remote exists; `fetch_failed` raises). Factor the shared part of `plan_config_commit` into a helper in `publish.py` (e.g. `direct_blockers(main, remote, base, base_sha, store) -> (blockers, warnings)`) and use it from both, without changing `config commit` behaviour.
  - Add `fix: str | None = None` to `publish.Blocker`; `to_json` emits `fix` only when set (keeps `config commit` JSON unchanged). Set `fix` to `factory update` / `factory onboard` / `factory config commit` for blockers 1–3.
  - `unknown_base` (base branch `refs/heads/<base>` does not exist) and `invalid_value` stay raised errors, not blockers.
- **D9 Validation.** New `OverlaySource` in `config/source.py`: wraps an optional `CommitSource(main, base, base_sha)` and an overlay `dict[str, bytes]`; `read_text` returns the overlay first, `list_files` is the union, `label` names `"<base>+plan:<rel>"`, never reads `local.yaml` from the overlay base. Run `load_config(OverlaySource(...))`; `ConfigError` → `invalid_plan` blocker with the issues. Then for every planned workflow: `parse_workflow(yaml.safe_load(bytes), cfg.roles)` and `interpreter.preflight(workflow, cfg.agents)`; `WorkflowError` → `invalid_plan` with its issues. Verify that preflight does not require the harness CLI on PATH (it resolves models via the harness registry); if it does fail only because the CLI is missing, do not treat that as a blocker (harness_missing is a warning per D5) — inspect and handle explicitly. No network.
- **D10 Trace DB.** A repo without factory normally has no trace DB, and opening `TaskRunStore` would create `.factory/trace.db` in the working tree. Open the store only when `load_local(main).trace_db_path(main)` exists; otherwise there can be no run. Make `store` optional in `publish.publish_direct`/`_advance` (`TaskRunStore | None`; `None` = no lock, no live-run check). `config commit` keeps passing its store.
- **D11 Commit.** `commit_init(...)`: build the plan; `--expect` mismatch → `plan_changed` (data = plan); no blockers allowed; message `-m` or default `factory: install from the library <name>` / `factory: install from the seed`. Settings for publishing = the planned `ProjectSettings` (base, `remote` = detected remote or `origin`, provider + azure). 
  - direct: `publish.publish_direct(main, settings=..., plan=..., message=..., store=store_or_None, materialize=True)`.
  - `--pr`: `publish.publish_pr(..., provider=get_provider(settings, main), prefix="factory-init/", body=<file list + digest>)`; base and the checkout stay untouched; nothing written to the working tree.
  - New `materialize` flag in `publish_direct` → `_advance` → `_stage_matching`: when set, a planned file whose disk path is absent, or whose bytes equal `old_content` (unchanged base version, e.g. clean `.gitignore`), gets the planned content written (mkdir parents) **after the push, inside `_advance`, just before `update-ref`**, then staged. Anything else keeps today's "changed after the plan" warning. Default `False` keeps `config commit` unchanged. Without a remote there is no push; the commit + advance path is the same.
  - After a successful publish (direct or PR) write `data.exclude.lines` to `info/exclude` with `run.gitops.ensure_excluded`. Never before.
  - `ProviderError` → its code (`push_failed`, `base_moved`, ...) with `data` = plan; `RuntimeError` → `commit_failed`. A rejected push must leave refs, index and working tree exactly as before (test it).
- **D12 Foreign content warnings.** For each of backlog, specs and docs dirs: if it exists (base tree or disk) and contains files other than `.gitkeep`, warning `foreign_content` ("backlog/ already has 12 file(s); factory will use them as they are"). Warning only.
- **D13 Warnings shape.** The envelope `warnings` stay strings (messages). `data.warnings` is a list of `{code, message}` (`harness_missing`, `gitignore_dirty`, `foreign_content`, M7 notes as `code: "remote_note"`, invalid library items as `invalid_item`).

## Files

1. `aifactory/src/aifactory/library/detect.py` (new): `RemoteInfo`, `parse_remote_url`, `detect(root) -> Detected` (D3), `to_json`.
2. `aifactory/src/aifactory/library/install.py`: extract `_choice(...)` (names, bindings, settings, azure, dirs, validation) and `_render(...)` from `init_repo`; `init_repo` keeps its signature (add keyword args `azure`, `backlog_dir`, `specs_dir`, `docs_dir`; `provider` literal gains `"azure"`) and behaviour. Keep `_refuse` for legacy mode. Move `_Source` listing support for `available` (D4) here or in the new module.
3. `aifactory/src/aifactory/library/install_commit.py` (new): `InitPlan` dataclass (wrapping `PublishPlan` + `detected`, `available`, `choice`, `exclude`, `warnings`, `validation`, `source`, `library`, `manifest`), `plan_init(path, *, base, provider, azure, agents, bindings, workflows, backlog_dir, specs_dir, docs_dir, pr, environ) -> InitPlan`, `commit_init(..., expect, message) -> InitCommitResult`, `InitError(code, message, data, issues)` (or reuse `LibraryStoreError` which already carries `data`/`issues` and is handled by `cli._library_fail` — prefer reuse). Module docstring lists the codes.
4. `aifactory/src/aifactory/providers/publish.py`: `Blocker.fix`, `plan_contents`, shared `direct_blockers`, optional `store`, `materialize`. Update its docstring.
5. `aifactory/src/aifactory/config/commit.py`: use `direct_blockers`; behaviour unchanged.
6. `aifactory/src/aifactory/config/source.py`: `OverlaySource`.
7. `aifactory/src/aifactory/harness/check.py`: `installed_path(name)`.
8. `aifactory/src/aifactory/cli.py`: `_add_init_command` (new options, updated description mentioning modes, blockers, digest), `_init` dispatches legacy / preview / commit; `--json` output `_emit_ok(plan.to_json(), [w.message ...])`; commit refusal via `_library_fail` (exit 2). Human output for preview: one line per file (`create .factory/config.yaml`), blockers (`blocked: code: message`), warnings, `digest <sha>`, `next: factory init --commit --expect <digest>`; for commit: commit sha, pushed/advanced or PR url.
9. `aifactory/src/aifactory/skill/codes.py`: add `config_not_committed`, `dirty_paths`, `invalid_plan`; update `already_installed`/`existing_config` meanings to cover both modes; reuse existing `plan_changed`, `push_failed`, `not_on_base`, `run_in_progress`, `base_behind`, `base_diverged`, `fetch_failed`, `commit_failed`, `base_moved`, `conflicting_options`, `unknown_base`. `tests/test_skill.py` scans string literals at raise sites — run it.
10. `aifactory/src/aifactory/skill/skill.md`: new procedure `### Install` (after `### Check`): 1) `factory check --json` → `data.install: none`; 2) `factory init --dry-run --json [options]`, review `data.files`, `blockers`, `warnings`, `detected`, `available`; explain options and per-agent `--bind`; 3) show the user the plan and the `digest`; 4) `factory init --commit --expect <digest> [-m TEXT] --json`; 5) `plan_changed` → preview again; 6) `push_failed` → ask the user, and only with their consent repeat with `--commit --pr --expect <digest>`; 7) blockers and what each fix is (`factory update`, `factory onboard`, `factory config commit`, `dirty_paths`: move/commit the files), warnings `harness_missing`, `gitignore_dirty`, `foreign_content`; 8) legacy mode one line. Check that `tests/test_skill.py` (e.g. `test_every_command_is_in_skill`, option coverage) passes.
11. Tests (D below).

## Tests

New `aifactory/tests/library/test_library_detect.py`:
- table test of `parse_remote_url`: github https / https with user / ssh:// / scp; azure dev.azure.com https (with and without `user@`), ssh.dev.azure.com scp and `ssh://`, `{org}.visualstudio.com` with and without `DefaultCollection`, vs-ssh; percent-decoded project; gitlab/other host, local path → `local`.
- `detect`: base from `refs/remotes/origin/HEAD` (set via `git remote set-head origin <b>` or `git symbolic-ref`), fallback to current branch; harnesses via a temp bin dir on PATH with fake `claude` only (monkeypatch `PATH`, unset `CODEX_PATH` etc.).

New `aifactory/tests/library/test_library_install_commit.py` (reuse `home`, `repo`, `library` style fixtures from `test_library_install.py`, `_identity` and the bare-remote pattern of `tests/config/test_config_publish.py`, `run_json` from `cli_json.py`; put the trace DB outside the repo or rely on D10):
- preview writes nothing: snapshot of refs, index and working tree (like `_snapshot` in `test_config_publish.py`) equal before/after; `$HAIFA_HOME` unchanged; data has files incl. `.factory/manifest.yaml` with content, `digest`, `detected`, `available` (seed without library; library items with library).
- commit + push: with bare remote, `--commit --expect <digest>` → `committed`, `pushed`, `advanced`; bare `main` == commit; parent == old base; working tree has the files; `git status --porcelain` clean.
- rejected push changes nothing: make the bare remote reject (e.g. `receive.denyCurrentBranch`/a pre-receive hook that exits 1) → `push_failed`, snapshot unchanged (no files on disk).
- PR via fake `gh` (`install_fake_gh`, `prepare_shared_gh` fixture as in `test_config_publish.py`; remote URL must be a bare path but provider forced with `--provider github`): branch `factory-init/1` on the bare remote, `data.pr.url`, local `main` and checkout unchanged.
- `plan_changed`: preview, change something (e.g. commit a new file to main that changes `base_sha`, or `--bind` differently), commit with old digest → `plan_changed`.
- `dirty_paths`: write `.factory/prompts/planner/system.md` with other content (untracked, no manifest/config on disk) → the only blocker is `dirty_paths`, the path is in its message; `--commit` refuses with `dirty_paths` and changes nothing. Same file with exactly the planned content → no blocker.
- dirty `.gitignore`: modify `.gitignore` uncommitted → plan has no `.gitignore` file, `data.exclude.lines` == missing runtime lines, warning `gitignore_dirty`; after `--commit` the lines are in `.git/info/exclude` and the working-tree `.gitignore` still has the user's edit.
- azure from URL: remote `https://dev.azure.com/contoso/Proj/_git/repo` (only set URL; no push needed — use `--dry-run`, and note `remote_state` fetch would hit the network: for azure/github URL tests use `--dry-run --pr` so no fetch happens, or set `pushurl`/`url` per test so that nothing contacts a network; never fetch a real URL) → `detected.provider == "azure"`, planned config has `git_provider: azure` and `azure:` section.
- builder on codex, others on claude: `--bind builder=codex` → agents.yaml builder `harness: codex` without the claude model; others `harness: claude`; with no `codex` on PATH → warning `harness_missing`, no blocker.
- `existing_config` with an sssf fixture (`adws/adw_sssf_config/sssf.config.yaml` committed) → blocker and commit refused.
- `already_installed` (after a successful commit, preview again) and `config_not_committed` (legacy `init` first, then preview).
- After install: `run_check(repo, machine=FakeMachine())` (see `tests/check/test_factory_check.py`) has no `severity == "error"` finding; `factory config items --json` → every item `state == "synced"`.
- `--specs-dir docs/specs --docs-dir docs/app` → planner/documenter `writes` use them; `--backlog-dir work/backlog` → `.gitkeep` there; existing `backlog/` with files → warning `foreign_content` and no `.gitkeep`.
- option conflicts → `conflicting_options`.
- Legacy tests in `test_library_install.py` stay green.

## Verification

```bash
just test
just typecheck
just lint
uv run pytest aifactory/tests/library aifactory/tests/config aifactory/tests/providers aifactory/tests/test_skill.py -q   # or the repo's pytest invocation via just
```
Also run by hand in a temp repo: `factory init --dry-run --json` then `factory init --commit --expect <digest> --json`.

## Out of scope

`factory update` (M9), onboarding of existing configuration (O2, O4), installing tools (`gh`, `az`, harnesses), the dashboard.
