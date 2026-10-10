# HAIFA-S01-T14: `factory update` z knihovny s migracemi — plán

Design: `docs/design/library-onboarding-distribution.md` AR23 (stavy), AR24 (update po souborech), AR25 (migrace), D20, D26. Paths below are relative to `aifactory/src/aifactory/` unless they start with `aifactory/` or `tests/` (= `aifactory/tests/`).

## 0. What already exists (reuse, do not reimplement)

- `library/config_edit.py` (L7): `RepoState` (`read_state(root, "worktree"|"base")`, `.files`, `.executable`, `.blobs`, `.manifest`, `.roster_entry()`, `.item_paths()`, `.apply()`), `Change`, `_diff`, `_item_files`, `_edit_agents`, `_with_manifest`, `_manifest_set`, `_new_entry`, `_check_type`, `plan_config` (builds `PublishPlan`, blockers `run_in_progress` / `dirty_paths` / `invalid_plan` / direct blockers, digest), `run_config` (dry run, `--expect` → `plan_changed`, blockers → error, `_write_repo` = worktree / `publish_direct` / `publish_pr`), `ConfigPlan`, `ConfigResult`, `_subject`.
- `library/config_transfer.py` (L8): `library_version(source, environ, kind, item_name, version)` → `(Item, commit)` for the head (`version=None`) or a version from history; raises `LibraryStoreError("unknown_version")` when the version is not in the history (also for the seed) and `unknown_item` when the item is not there. `_text()`, `_file_diffs()` pattern with `difflib`. `_connect()` (manifest `library` ref + `library_mismatch` warning).
- `library/install.py`: `_Source(environ)` (library HEAD or the seed; `.library` = `LibraryRef`), `_repo_root`, `GITIGNORE_LINES`.
- `library/install_commit.py`: `_append_lines`, `_committed`-like helpers, `validate_source`.
- `library/state.py`: `item_states`, `library_side`, `extract_factory`, `repo_version`.
- `library/load.py`: `validate_item(item)` → issues.
- `config/manifest.py`: `parse_manifest` raises `ConfigError(code="format_unsupported")`; `MANIFEST_FILE`.
- `config/yamledit.py`: `edit_yaml(text, fn)` ruamel round trip (comments + flow style kept).
- Tests helpers to copy: `tests/library/test_library_config_transfer.py` (`home` fixture, `make_repo`, `repo` fixture = library on bare remote + `init --commit`, `advance_library`, `commit_all`, `manifest`, `states`, `write`, `snapshot`), skill library fixture in `tests/library/test_library_config_edit.py` (lines ~85–95, `skills/lint/...`).

## 1. Refactor `library/config_edit.py` (small, behaviour-preserving)

1. `Command = Literal["add", "set", "remove", "export", "revert", "update"]`.
2. Split `plan_config` into the change computation and a new public
   `finish_plan(command, root, target, state, change, source, environ, *, type, name, slot) -> ConfigPlan`
   containing everything from `files = _planned_files(state, change)` to the `ConfigPlan(...)` return (blockers, validation, harness warnings, library plan, digest). `plan_config` calls it; existing tests must stay green.
3. Split `run_config` into `plan_config(...)` + new public
   `execute_plan(plan, *, dry_run, expect, message, environ) -> ConfigResult` (dry run, `plan_changed`, first blocker raised, no-op when unchanged, `_write_library`, `_write_repo`). `run_config` = `execute_plan(plan_config(...), ...)`.
4. `_subject(plan)`: for `update` use `plan.change.detail["update"]["subject"]` (built by the update module, see 2.8).
5. `_write_repo`: `command=f"config {command}"` → for update pass `"update"` (`command if command == "update" else f"config {command}"`); the worktree warning text says `factory config commit` — keep it.
6. Export new names in `__all__`.

## 2. New module `library/update.py`

Module docstring describes AR24 + the modes (copy style of `config_edit`). Public API:

```python
def plan_update(path: Path, *, take: Sequence[str] = (), merge: Sequence[str] = (),
                migrate: Sequence[str] = (), commit: bool = False, pr: bool = False,
                environ: Mapping[str, str] | None = None) -> ConfigPlan
def run_update(path: Path, *, take=(), merge=(), migrate=(), dry_run=False, commit=False,
               pr=False, expect=None, message=None, environ=None) -> ConfigResult
```
`run_update` = `execute_plan(plan_update(...), ...)`. `ConfigPlan(command="update", type="", name="", slot=None)`.

### 2.1 Refusals (before anything else, in this order)

`root = _repo_root(path)`; `base = worktree_base(root)`; base sha via `git.rev_parse(root, f"refs/heads/{base}")` (`unknown_base` as `read_state`).
1. Manifest in base: `git.blob_at(root, base_sha, MANIFEST_FILE)`.
   - absent and `(root / MANIFEST_FILE).is_file()` → `LibraryStoreError("config_not_committed", ".factory/manifest.yaml is in the working tree but not in <base>; run factory config commit", data={"fix": "factory config commit"})`.
   - absent otherwise → `LibraryStoreError("not_onboarded", "... has no .factory/manifest.yaml in <base>; run factory onboard (existing .factory/ or adws/) or factory init (no factory yet)", data={"fix": "factory onboard" if .factory/config.yaml or adws/adw_sssf_config exists in base/worktree else "factory init"})`.
2. Parse the base manifest with `parse_manifest`; and in worktree mode also the working-tree manifest. `ConfigError` with `exc.code == "format_unsupported"` → `LibraryStoreError("format_unsupported", str(exc), data={"fix": "factory upgrade"})`; other `ConfigError` → `invalid_config`. (Do this here because `RepoState.manifest` maps every `ConfigError` to `invalid_config`.)
3. Validate selectors (2.5) → `invalid_value` / `unknown_item` / `conflicting_options`; unknown `--migrate` id → `invalid_value` listing known ids.

Then `state = read_state(root, "base" if commit else "worktree")`, `source = _Source(environ)`.

### 2.2 Units (one file = one unit)

Represent a unit value as `tuple[bytes, bool] | None` (content, executable; `None` = absent).
- agent `SLOT`: units `purpose` (bytes = purpose UTF-8, exe False; ours from `state.roster_entry(SLOT)["purpose"]`, None when no roster entry), `system.md`, `user.md` (ours from `.factory/prompts/SLOT/<f>`). Other files in the prompts dir are ignored (never deleted).
- workflow `NAME`: one unit named `NAME.yaml` (`.factory/workflows/NAME.yaml`).
- skill `NAME`: every relative path under `.claude/skills/NAME/` (ours, with `state.executable`), union with paths of base and theirs items (`Item.files[].path`, `.executable`). The mirror `.agents/skills/NAME/` is never read as ours; it is rewritten as an exact copy of the result whenever the skill changes (via `_item_files`, which writes both roots, plus deletion of stale paths).
- extension `NAME`: every relative path under `.factory/extensions/NAME/`.

Base = `library_version(source, environ, kind, entry.item, entry.version)[0]` ; `unknown_version` → no base (item is `unknown`). Theirs = `library_version(source, environ, kind, entry.item, None)[0]`; `unknown_item`/`invalid_item` at head → item action `absent`: keep ours, manifest entry unchanged, warning `item_not_in_library: <type>/<name> (<item>) is not in <library|the seed>; kept`.
Shortcut: R (`state.version`) == L (head version) → no unit work (action `same`), only the manifest moves if M ≠ L.

### 2.3 Rule per unit (b, o, t)

Item has a base:
| condition (in order) | status | result |
|---|---|---|
| R is None (state `missing`) and o is None and t is not None | `restore` | t |
| o == t | `same` | o |
| o == b | `take` | t |
| t == b | `keep` | o |
| selector `--take` covers the unit | `taken` | t |
| selector `--merge` covers the item | `merged` | merge result (2.4) |
| otherwise | `conflict` | o (plan shows `ours_diff` b→o and `theirs_diff` b→t) |

Item without a base (`unknown`): `restore` as above; o == t → `same`; `--take` → `taken`; else `unknown` (keep o, plan shows `diff` o→t). `--merge` on an unknown item → `LibraryStoreError("invalid_value", "<type>/<name> has no base version (state unknown); use --take")`.
`--take` applies to every unit of the selector where o ≠ t (also `keep` units): "vezme theirs". Text is never merged without `--merge`.

### 2.4 `--merge TYP/JMÉNO`

For each `conflict` unit of the item: if b, o or t is None or any is not UTF-8 → `merge_conflict`. Otherwise write the three texts to a temp dir (outside the repo, `tempfile.TemporaryDirectory`) and run `git merge-file -p -L repo -L base -L library ours base theirs` (via `subprocess.run`, cwd = temp dir; for `purpose` add a trailing `\n` and strip it after). Return code 0 → merged text; >0 or <0 → `LibraryStoreError("merge_conflict", "<type>/<name>:<unit>: git merge-file left N conflict(s); keep the repo copy or --take", data={"type","name","file","conflicts": N})`. Executable bit of a merged unit: by the 3-way rule on the bit alone. After all units: build the merged `Item` and run `validate_item(item)`; issues → `merge_conflict` with `issues=`. (Whole-plan `invalid_plan` still applies afterwards.)

### 2.5 Selectors

`--take` value `TYP/JMÉNO[:SOUBOR]`, `--merge` value `TYP/JMÉNO` (both repeatable, `action="append"`). Parse with `_check_type`; malformed → `invalid_value`. The name must be in the manifest → else `unknown_item`. SOUBOR must be a unit name of that item (2.2) → else `invalid_value`. Same item in `--take` and `--merge` → `conflicting_options`. `--merge` with `:SOUBOR` → `invalid_value`.

### 2.6 Writing an item's result

If any unit result ≠ ours: build `files = dict.fromkeys(paths of the item that are units/mirror)` then `files.update(_item_files(state, result_item, name))` (same as `plan_revert`) — for agents only the two prompt paths (not `dict.fromkeys(state.item_paths)` — extra prompt files stay); skills: stale paths in both `.claude/skills/NAME/` and `.agents/skills/NAME/` → None. Purpose changed → `files[AGENTS_FILE] = _edit_agents(state, lambda d: roster_set(d, slot, {"purpose": p}))`; no roster entry → `roster_add(doc, _new_entry(theirs_item, slot, state.settings, None, None, None))` with the result purpose. Apply to a running `current = current.apply(files, exe)` so later edits of `agents.yaml` see earlier ones.

### 2.7 Also in the same plan

1. **Missing prompts of declared agents**: every roster slot in `agents.yaml` that is not in the manifest and lacks `system.md` or `user.md`: if the library/seed has an agent of that name at head, write only the missing prompt files from it (status `restore`, manifest unchanged); otherwise warning `prompt_missing: agent <slot> has no <file> and the library has no agent <slot>`. Agents in the manifest are covered by the `restore` rule.
2. **`.gitignore`**: before planning put the current `.gitignore` into `state.files[".gitignore"]` (worktree: disk bytes; base: `git.blob_at` + `read_blob`, also `state.blobs`), so the planned file is `modify`, not `create`. Missing `GITIGNORE_LINES` (stripped-line compare) are appended with `install_commit._append_lines`. Report `gitignore: {"added": [...]}`.
3. **Manifest**: every entry with a theirs → `ManifestEntry(item=entry.item, version=<head version>)`; `written_by = aifactory.__version__`; `library` via `config_transfer._connect` semantics (set when None; warning `library_mismatch` on another id). Write with `_with_manifest` only if it differs.
4. **Migrations** (2.9): detected on the state after the item changes; listed always, applied only when in `--migrate`.

Then `_diff(state, current, change)`; `change.warnings` collected; `change.detail = {"update": {...}}`; `return finish_plan("update", root, target, state, change, source, environ, type="", name="", slot=None)`.

### 2.8 `data.update` JSON (inside `ConfigPlan.to_json()` via `change.detail`)

```json
{"subject": "factory: update 2 item(s) from the library team",
 "items": [{"type","name","item","state","manifest_version","library_version","repo_version",
            "action": "same|update|keep|conflict|unknown|restore|absent",
            "files": [{"file","status","binary","ours_diff","theirs_diff","diff"}]}],
 "conflicts": ["agent/builder:system.md"],
 "gitignore": {"added": []},
 "migrations": [{"id","title","path","diff","selected": bool, "applied": bool}],
 "manifest": {"changed": bool, "written_by": "<version>"}}
```
Item action: `same` (nothing to do), `update` (some unit taken/restored/merged), `conflict` (some unit conflict, kept), `unknown` (no base, kept), `keep` (only repo changes), `restore`, `absent`. `state` = AR23 state (`item_state(...)` from `library/state.py`). Each remaining conflict/unknown unit adds a warning `update_conflict: <type>/<name>:<file> kept the repo copy; --take <type>/<name>:<file> or --merge <type>/<name>` (unknown: `update_unknown: ...; --take ...`). Every detected-but-not-selected migration adds `migration_available: <id> <title>; run with --migrate <id>`. A `--migrate ID` that is not detected adds `migration_not_needed: <id>`.
Subject: `factory: update N item(s) from the library <name>` / `from the seed`, `+ migrations m001` when applied; `N` = items with action `update`/`restore`.

### 2.9 New module `library/migrations.py`

```python
@dataclass(frozen=True)
class Migration:
    id: str; title: str; path: str
    detect: Callable[[bytes], bool]
    apply: Callable[[str], str]
MIGRATIONS: tuple[Migration, ...]
def detected(files: Mapping[str, bytes]) -> list[Migration]
def known_ids() -> list[str]
```
`m001` (`levels: module -> project`), path `.factory/config.yaml`: `detect` = YAML loads to a mapping whose `levels` is a list containing `"module"` and not `"project"`; `apply` = `edit_yaml(text, fn)` where `fn` replaces the item in place by index (`seq[i] = "project"`) so the `CommentedSeq`, flow style and comments stay. The detector makes it idempotent (after apply it no longer matches); the manifest records nothing. Diff = unified diff of the file before/after (`fromfile=a/<path>`, `tofile=b/<path>`).

## 3. CLI `cli.py`

- `SUBCOMMANDS`: add `("update", "update the repo's items from the library (or the seed) file by file; repo changes stay without --take or --merge")` after `adopt`.
- `_add_update_command(parser)`: description explaining AR24 rules, unknown, migrations, modes, refusals (`not_onboarded`, `config_not_committed`, `format_unsupported`), `merge_conflict`, data keys. Options: `--take TYP/JMÉNO[:SOUBOR]` (append, default []), `--merge TYP/JMÉNO` (append), `--migrate ID` (append), `--dry-run`, `--commit`, `--pr`, `--expect DIGEST`, `-m/--message TEXT`, `--json`, `--repo PATH`. Every option string must appear in the help/description (`tests/test_skill.py::test_every_command_is_in_skill`).
- `_update(args)`: `_config_edit_conflict(args)` (reuse), then `run_update(...)`; `LibraryStoreError`/`ProviderError` → `_library_fail(exc, args.json, "factory update")`. JSON: `_emit_ok(result.to_json(), result.warnings)`. Text: one line per item (`action type/name M→L short`), for conflict units print `ours_diff` and `theirs_diff`, unknown units `diff`, migrations with diff and `(run with --migrate ID)`, planned files `action path`, blockers, `digest`, `next:` hint as `_config_edit`; written → `next: factory config commit`; commit/PR lines as `_config_edit`.
- `_dispatch`: `if command == "update": return _update(args)`.

## 4. `factory check`: `update_available` (`check/repo_rules.py`)

New rule `update(ctx)` added to `REPO_GROUP` after `gitignore` as `Rule("update", update)`. Only when `ctx.state.state == "onboarded"` and `ctx.commit` and no manifest error. Read-only, no network: extract base `.factory/` with `library.state.extract_factory(ctx.main, ctx.commit, tmp)` into a `tempfile.TemporaryDirectory`, `read_manifest(tmp)`, `side = library_side()`, `heads = side.heads(...)`, R via `repo_version(tmp, ...)` — do not call `side.history` (no cache writes). Item is updatable when R is None (missing) or (L is not None and L ≠ M and R ≠ L). Also `migrations.detected(...)` on base `config.yaml`. If any → one `Finding("update_available", "repo", "info", "<n> item(s) can be updated from the library|the seed: agent/builder, ...; migrations: m001", "review factory update --dry-run, then factory update --commit", "update")` (list ≤ `_LIST_MAX` names, then `+N`). Add `update_available` to `ISSUE_CODES["check"]`. Check `tests/check/` expectations that list exact findings for onboarded repos still pass (the seed versions equal the installed ones, so no finding there).

## 5. Skill `skill/codes.py` and `skill/skill.md`

- `_CODES`: new `("merge_conflict", "2", "factory update --merge: git merge-file left conflicts or the merged item is not valid; the repo copy stays (keep it or --take)")`. Extend meanings: `not_onboarded` (+ `factory update`: no manifest in base, data.fix `factory onboard` or `factory init`), `config_not_committed` (+ `factory update`: manifest only in the working tree), `format_unsupported` already generic, `dirty_paths`/`invalid_plan`/`plan_changed`/`run_in_progress`/`unknown_item`/`invalid_value` mention `update` where they list commands.
- `ISSUE_CODES`: add `"update_item": ("same","update","keep","conflict","unknown","restore","absent")`, `"update_file": ("same","take","keep","conflict","unknown","taken","merged","restore")`, `"update": ("update_conflict","update_unknown","migration_available","migration_not_needed","item_not_in_library","prompt_missing","library_mismatch")`, `"migration": ("m001",)`; `"check"` + `update_available`. Every code must appear as `` `code` `` in skill.md (`test_skill_lists_error_codes`).
- `skill.md`: new procedure section `### Update from the library` after "Repo and library: config export / revert / diff": commands (`factory update --dry-run --json`, `--expect`, `--take agent/builder:system.md`, `--merge workflow/solo`, `--migrate m001`, `--commit [--pr]`), the per-file rule table, unknown, restore of missing files/prompts/.gitignore, manifest to head + `written_by`, migrations listed with diff and run only with `--migrate`, refusals, warnings, never overwrites without consent → ask the user before `--take`/`--merge`. In the "Check" procedure mention `update_available` → action `update`. Mention item/file status values in backticks.

## 6. Tests `tests/library/test_library_update.py` (new; pytest, no model, no network)

Copy the fixtures/helpers of `test_library_config_transfer.py` (`home`, `make_repo`, `repo`, `advance_library`, `commit_all`, `manifest`, `states`, `write`, `snapshot`, `run_json`). Helper `upd(capsys, repo, *args)` → `run_json(capsys, ["update", *args, "--repo", str(repo), "--json"])`. Cases:
1. `test_outdated_is_replaced`: `advance_library("agents/builder/system.md", ...)` → update → repo file = library text, manifest version = head, `written_by == __version__`, `states` → `synced`.
2. `test_repo_change_is_kept`: edit `SYSTEM` in repo (commit), library unchanged → update: file unchanged, status `keep`, no conflict.
3. `test_conflict_kept_then_take`: both changed → `--dry-run` shows `conflict` with `ours_diff` and `theirs_diff`, warning `update_conflict`; update without options keeps repo bytes; manifest moved to head → state `modified`. Then repeat setup (new library change) and `--take agent/builder:system.md` → library text.
4. `test_merge_clean_and_conflict`: library changes line 1, repo changes a distant line of a multi-line prompt → `--merge agent/builder` → both edits present, status `merged`. Same line edited on both sides → `--merge` → exit 2 `merge_conflict`, repo untouched (snapshot).
5. `test_unknown_item`: replace manifest version with `sha256:` + `0`*64 (commit), library advanced → `unknown`, `diff` shown, kept by default; `--take agent/builder` takes; `--merge agent/builder` → `invalid_value`.
6. `test_missing_prompt_restored`: delete `.factory/prompts/builder/user.md`, commit → update restores it (status `restore`).
7. `test_skill_added_and_deleted_files`: library with skill `lint` (as in config_edit test: `SKILL.md`, `bin/run.sh` exe), `factory config add skill lint --commit`; library adds `docs/extra.md` and deletes `bin/run.sh` → update: `.claude/skills/lint/docs/extra.md` and `.agents/skills/lint/docs/extra.md` created, `bin/run.sh` gone in both, exe bits right.
8. `test_m001_keeps_comments`: commit a `config.yaml` with `# levels comment\nlevels: [module, step, task]  # inline\n` → `--dry-run` lists `m001` with a diff, plain update does not touch `config.yaml`; `--migrate m001` → `levels: [project, step, task]` with both comments intact; second `--dry-run` lists no migration.
9. `test_second_update_no_change`: after an update, `--dry-run` → `changed` false and plain update writes nothing (snapshot equal).
10. `test_commit_with_bare_remote`: library advanced → `--dry-run --commit` digest → `--commit --expect <digest>` → bare remote `main` has the commit (`git -C bare log`), checkout updated, `committed` true; wrong `--expect` → `plan_changed`.
11. `test_refusals`: plain `make_repo` → `not_onboarded` (data.fix `factory init`); manifest only in working tree (init without `--commit`) → `config_not_committed`; manifest committed with `format: 99` → `format_unsupported`.
12. `test_gitignore_lines_added`: remove a GITIGNORE line from `.gitignore`, commit → update re-adds it.
13. `test_check_reports_update_available`: library advanced → `factory check --repo R --offline --json` `data.findings` contains code `update_available` with action `update`; after `update --commit` it is gone.
14. Unit tests for `library/migrations.py` (detect/apply/idempotent) and the 3-way rule function (pure function, table-driven) are welcome in the same file.

Not in `tests/tiers.py` `SLOW_FILES`.

## 7. Verify

`just test` (or at least `cd aifactory && uv run pytest tests/library tests/check tests/test_skill.py -q`), `just typecheck`, `just lint`. Then `just check-scoped`.

## Constraints

- Allowed paths: `aifactory/`, `justfile`, this spec, `app_docs/HAIFA-S01-T14-...md`. Never change `.factory/`, `vendor/`, `prototype/`, `docs/`.
- A repo copy changed in the repo is never overwritten without `--take`/`--merge`; no automatic text merge.
- Out of scope: `--repos` (L9), seed → library (L10), dashboard.
