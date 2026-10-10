# HAIFA-S06-T03: Jednorázový onboarding (`factory onboard`) pro `.factory/` z doby před knihovnou

Design reference: `docs/design/library-onboarding-distribution.md` §7 (AR30, AR31, AR33, AR34, AR36), §11 V13. Decision 8 and D30 in `docs/decisions.md`.

Allowed paths: `aifactory/`, `justfile`, this spec, `app_docs/HAIFA-S06-T03-…md`. Do NOT touch `.factory/`, `vendor/`, `prototype/`, `adws/`, `CLAUDE.md`, `docs/`.

## 0. What exists and gets reused (read these first)

| Need | Existing code |
|---|---|
| repo state (`pre_library`, `onboarded`, …) | `onboard/state.py` `repo_state(root)` → `RepoState(state, base, commit, …)` |
| take over onboarded repo | `onboard/adopt.py` (`_roster`, `_settings`, `_library_files` build library files of a repo agent incl. `agent.yaml` with `purpose` + `defaults` from the roster) |
| base / worktree view of shared `.factory/` | `library/config_edit.py` `read_state(root, "base"|"worktree")` → `RepoState(files, executable, blobs, base, base_sha, settings, roster, workflows(), materialized())`; `_base_tasks(state)` = (task id, effective workflow) of the backlog in base |
| item version of a repo copy | `library/load.py` `check_repo_item(dir, type, name)` (→ `Item` with `.version`, issues) |
| library | `library/install.py` `_Source(environ)` (`root`, `head`, `library: LibraryRef`, `load(type, names)`); `library/store.py` `library_root`, `require_library`, `_dirty`, `current_branch`, `remote_tip`, `behind_error`, `diverged_error`, `import_items(items, source, subject, dry_run=, environ=, expect_head=)` (lock, dirty, fetch, behind/diverged, commit, push without force, `push_failed`), `LibraryPlan.digest`; `library/history.py` `history(root, type, name, environ)` → revisions with `.version`; `library/tree.py` `tree_files`, `item_paths`, `item_versions` |
| repo commit without checkout (M7) | `providers/publish.py` `PlannedFile`, `Blocker`, `PublishPlan`, `plan_contents`, `plan_digest`, `direct_blockers`, `run_blocker`, `publish_direct(materialize=True)`, `publish_pr` |
| init plan helpers (M8) | `library/install_commit.py` `_gitignore(root, base_sha, contents, warnings)` (`.gitignore` lines or `info/exclude`), `_dirty`, `_validate(root, base, base_sha, contents, workflows, missing)` (load_config + preflight), `_stable_manifest`, `_store`, `InitWarning`, `EXCLUDE_PSEUDO_PATH`; `library/install.py` `_now`, `_git_out` |
| export digest | `library/config_transfer.py` `combined_digest(repo, library)` |
| manifest | `config/manifest.py` `Manifest`, `LibraryRef`, `Onboarding(source="pre_library", …)`, `ManifestItems`, `ManifestEntry`, `dump_manifest`, `MANIFEST_FILE` |
| CLI patterns | `cli.py` `_add_adopt_command`/`_adopt`, `_init_conflict`, `_init_plan`, `_library_fail`, `_emit_ok` |
| error-code registry | `skill/codes.py` (`_CODES`, `ISSUE_CODES`), checked by `tests/test_skill.py` |
| test helpers | `tests/onboard/onboard_repo.py` (`init_repo`, `copy_haifa_factory`, `commit_all`, `git`, `write`, `snapshot`, `git_state`), `tests/onboard/test_adopt.py` (two machines = two `HAIFA_HOME`, bare library remote, identity fixture), `tests/cli_json.py` `run_json` |

Facts verified on this worktree (tests must not hard-code them, compute instead):
- HAIFA `.factory/` agents planner, builder, documenter equal the seed; `reviewer` differs (its `user.md` lacks the `test_result` block added in S03-T12). `build-test-review` is a workflow in `.factory/workflows/` that the seed does not have.
- HAIFA backlog names workflows `simple-sdlc`, `plan-build-test`, `build-test-review` (and `null`). The first two are not in `.factory/workflows/` → onboarding adds them from the library.

## 1. New module layout

```
aifactory/src/aifactory/onboard/
  __init__.py      # export the new API, update the module docstring (onboard is here now)
  state.py         # unchanged
  adopt.py         # unchanged except: reuse its helpers (no behaviour change)
  extract.py       # NEW: the pre_library extractor (O4 adds an sssf extractor next to it)
  onboard.py       # NEW: plan, blockers, remote check, digest, commit
```

### 1.1 `onboard/extract.py` — report codes, extraction result, pre_library extractor

```python
ReportCode = Literal["linked", "converted", "carried_over", "changed_meaning",
                     "not_converted", "manual", "left_in_place"]
REPORT_CODES: tuple[ReportCode, ...] = (... in this order ...)

@dataclass(frozen=True)
class ReportRow:
    code: ReportCode
    subject: str            # "agent/builder", "workflow/simple-sdlc", ".factory/config.yaml", "adws/"
    message: str            # one human sentence
    item: str | None = None # library item the slot is connected to
    version: str | None = None
    def to_json(self) -> dict[str, Any]

@dataclass
class Extraction:            # the interface O4 will also fill for sssf
    library_items: list[SeedItem]              # new library items/versions to write (library layout)
    entries: dict[ItemType, dict[str, ManifestEntry]]  # manifest items by type, key = slot
    files: dict[str, bytes]                    # files to ADD to the repo (never existing paths)
    report: list[ReportRow]
    warnings: list[str]
    added_workflows: list[str]                 # workflows added from the library
```

`extract_pre_library(state: config_edit.RepoState, source: _Source, environ, *, keep_local: set[tuple[ItemType,str]], names: dict[tuple[ItemType,str], str]) -> Extraction`

Items considered: every agent slot of the roster (`state.roster`, names in order) and every `.factory/workflows/<name>.yaml` (`state.workflows()`). Skills/extensions do not exist in pre_library repos — ignore.

For each item (`kind`, `slot`), with the repo copy read through `state.materialized()` + `check_repo_item(tmp, kind, slot)`:
1. Copy invalid (item None or issues) → no manifest entry (stays `local`), report `manual` ("not a valid item: …issues"), nothing written to the library.
2. `R = item.version`. Library lookup (library root/head from `source`):
   - **linked via own history**: `R in {r.version for r in history(root, kind, slot, environ)}` → entry `ManifestEntry(item=slot, version=R)`, report `linked`.
   - **linked via another item's head**: precompute once per type `heads = item_versions(root, head, item_paths(tree_files(root, head, [<type dir>/])))` filtered to the type; the first (sorted) item name whose head version == R → entry `(item=that, version=R)`, report `linked` (message names the item).
   - **`--keep-local kind/slot`** (only when not linked): library must have item `slot` at head (else raise `LibraryStoreError("unknown_item", …)`); entry `(item=slot, version=<head version of slot>)`, nothing written to the library, repo copy stays → item state later `modified`. Report `carried_over` ("the repo copy differs from library item X; the difference stays in the repo").
   - **new item** (D30): name = `names[(kind, slot)]` when given via `--name`, else `slot` when the library has no item of that type and name at head (`item_versions` None and no files), else `f"{slot}-{slug}"` where `slug = _slug(state.root.name)` (lowercase, every run of chars outside `[a-z0-9]` → `-`, strip `-`; empty → `"repo"`; result must pass `library.model.check_name`, else `invalid_value`). If the chosen name exists in the library with other content → blocker-level error `LibraryStoreError("name_taken", …, data={"type","name","item","fix": "--name TYP/JMÉNO=NOVÉ"})`. Library files: agents via `adopt._library_files(item, name, adopt._roster(copy), adopt._settings(copy), slot)` (purpose + defaults from the roster, `$specs_dir/`/`$docs_dir/` unexpanded); workflows the single file. Append `SeedItem(kind, name, R, files)`; entry `(item=name, version=R)`; report `converted` ("new library item <name>").
   - `--keep-local` and `--name` naming items that do not exist in the repo, or both given for the same item, → `LibraryStoreError("invalid_value"|"conflicting_options", …)`.
3. **Workflows named by the backlog in base and missing in the repo** (AR33): `{wf for _, wf in config_edit._base_tasks(state) if isinstance(wf, str)}` minus `state.workflows()` minus `{"resolve"}` (internal, D32). For each, sorted: `source.load("workflow", [wf])` from the library head; add `files[f".factory/workflows/{wf}.yaml"] = item.files[0].data`, entry `(item=wf, version=item.version)`, report `linked` ("added from the library; the backlog uses it"), append to `added_workflows`. When the library does not have it (`unknown_item`) → report `manual` + warning `unknown_workflow: tasks name workflow X; neither the repo nor the library has it` (no blocker; validation decides). Agents of an added workflow are not added (the roster already defines them; `invalid_plan` catches a missing one).
4. `left_in_place` rows: every other shared file of `.factory/` in base that is not an item file (`config.yaml`, `agents.yaml` — note bindings stay in the repo, `roles.yaml`, anything else), and `adws/` when `state`'s repo has `sssf_leftover` (message: "sssf adws/ stays; delete it in a separate commit"). One row per path/dir.

Keep the ordering deterministic (agents in roster order, then workflows sorted, then backlog workflows, then left_in_place) — the report goes into the digest-stable commit message and golden assertions.

### 1.2 `onboard/onboard.py` — plan and commit

```python
ONBOARDING_BRANCH = "factory-config/onboarding"
OnboardTarget = Literal["direct", "pr"]

@dataclass
class OnboardPlan:
    root: Path; repo: RepoState (onboard.state); target: str
    settings: ProjectSettings | None
    library: dict[str, Any] | None   # {"path","head","id","name","remote","digest"}
    extraction: Extraction | None
    manifest: Manifest | None
    publish: PublishPlan             # files may be empty when a state blocker short-circuits
    library_plan: LibraryPlan | None # dry run of import_items (None when nothing to write)
    exclude: dict[str, Any] | None   # info/exclude lines (as init)
    remote: dict[str, Any]           # {"name","url","checked": bool,"tip": sha|None,"branch_exists": bool|None}
    issues: list[Issue]; warnings: list[str]
    blockers -> publish.blockers; digest -> publish.digest
    def to_json(self) -> dict  # repo, base, base_sha, state, target, digest, files, blockers,
                               # issues, warnings, report[], items (manifest items json),
                               # manifest (json), library, library_plan, remote, exclude, message
@dataclass(frozen=True)
class OnboardResult:
    plan; dry_run; committed=False; commit=None; pushed=False; advanced=False; branch=None;
    pr=None; library_commit=None; extra_warnings=()
    warnings -> plan.warnings + extra; to_json -> {**plan.to_json(), dry_run, committed, commit,
                pushed, advanced, branch, pr{id,url,branch}, library_commit}
```

`plan_onboard(path, *, pr=False, keep_local=(), names=(), environ=None) -> OnboardPlan` — writes nothing to the repo, its index, refs other than remote-tracking/`FETCH_HEAD`, or the library:

1. `root = install._repo_root(path)` (`not_a_repository`/as init). `rs = repo_state(root)`.
2. **State blockers** (short-circuit: return a plan with this single blocker, no files, no network):
   - `onboarded` → `already_onboarded` (fix `factory adopt`; message includes `rs.onboarding` who/when)
   - `none` → `not_installed` (fix `factory init`)
   - `working_tree` → `config_not_committed` (fix `factory config commit`)
   - `sssf` → `sssf_not_supported` ("sssf conversion comes with O4")
   Digest of such a plan = `plan_digest(base, sha or "", [])`.
3. `state = config_edit.read_state(root, "base")` (do not touch `state.manifest` — it raises `not_onboarded`). Settings: `state.settings` (`invalid_config` raised as error).
4. **`source_not_committed`**: `wt = read_state(root, "worktree")`; paths under `.factory/` where `wt.files`/executable differ from `state.files` (either side) → blocker with the sorted path list (fix "commit or discard the changes of .factory/ first").
5. **Library**: `source = _Source(environ)`. `source.root is None` → blocker `library_missing` (fix `factory library init` / `factory library clone URL`) and short-circuit like step 2. Otherwise blockers (not short-circuit): `store._dirty(root)` → `library_dirty`; last fetched remote tip (`store.remote_tip(root, store.current_branch(root))`, no fetch) vs head: behind → `library_behind`, diverged → `library_diverged` (use `behind_error`/`diverged_error` messages, fix `factory library pull`).
6. **Remote check (the only network step)** `_check_remote(root, settings.remote, base, base_sha) -> (blockers, warnings, info)`:
   - no remote (`git.has_remote` false) → warning `no_remote: the repo has no remote <name>; onboarding is a local commit only` and skip.
   - `git.fetch(root, remote, base)`; `ProviderError` → blocker `remote_unchecked` (stop remote checks).
   - `tip = git.remote_tip(root, remote, base)`; when `tip` has `.factory/manifest.yaml` (`git.blob_at(root, tip, MANIFEST_FILE)`) → blocker `onboarded_in_remote` (fix `factory config pull, then factory adopt`).
   - `git.remote_branch_exists(root, remote, ONBOARDING_BRANCH)` (new, §2) → `None` → `remote_unchecked`; `True` → `onboarding_pending` (fix: merge or close the PR / delete branch `factory-config/onboarding`). Also a local `refs/heads/factory-config/onboarding` → `onboarding_pending`.
   - direct target only: compare `tip` with `base_sha` exactly like `publish.remote_state` (refactor: split `remote_state` into `fetch` + `compare_remote(root, remote, base, base_sha, tip)` so no second fetch) → `base_behind`/`base_diverged` blockers, ahead note as warning.
7. **M7 blockers**: direct → `direct_blockers(root, remote=…, base=…, base_sha=…, store=_store(root), check_remote=False)` (`not_on_base`, `run_in_progress`); pr → none. Close the store.
8. **Extraction** `extract_pre_library(state, source, environ, keep_local=…, names=…)`.
9. **Manifest**: `Manifest(written_by=__version__, library=source.library, onboarding=Onboarding(source="pre_library", source_commit=base_sha, at=_now(), by=_git_out(root,"config","user.name"), factory=__version__, library_commit=source.head), items=ManifestItems(agents=…, workflows=…))`. `contents = {**extraction.files, MANIFEST_FILE: dump_manifest(manifest)}`; `exclude = install_commit._gitignore(root, base_sha, contents, init_warnings)` (adds `.gitignore` with the runtime lines, or info/exclude + warning `gitignore_dirty`). `files = plan_contents(root, base_sha, contents)`.
10. **Invariant** (fixed constraint): every `PlannedFile` is `create` under `.factory/`, except `.gitignore` (`create`/`modify`, and its new content must start with the old bytes). Violation → `RuntimeError` (programming error, not a user code).
11. `dirty = install_commit._dirty(root, files)` → blocker `dirty_paths`.
12. **Validation**: workflows = all names in `state.workflows()` + `extraction.added_workflows`; `issues = install_commit._validate(root, base, base_sha, {**{f".factory/workflows/{n}.yaml": d for n, d in state.workflows().items()}, **contents}, workflows, missing_harnesses)` (`missing` from `config_edit._missing_harnesses()`); issues → blocker `invalid_plan`; harness warnings like config_edit (`harness_missing`).
13. **Library plan**: when `extraction.library_items`: `import_items(items, source_str, subject, dry_run=True, environ=environ)` → `library_plan`, warnings appended. `source_str = f"onboard {root} {base}@{base_sha[:12]}"`, subject `f"library: onboard {len(items)} item(s) from {root.name}"`.
14. **Digest** (covers both parts): repo part = `plan_digest(base, base_sha, digest_files)` where `digest_files` = files with the manifest content replaced by `_stable(manifest)` (onboarding `at=""` AND `library_commit=""`; write a local helper, don't change init's) plus the `:info/exclude` pseudo file as in `plan_init`. Library part = `library_plan.digest` if any else `plan_digest("library", source.head, [])` (sha of head). `digest = combined_digest(repo_part, library_part)` — same function as export, or a dedicated `sha256("aifactory-onboard-v1\0…")`; pick the dedicated one so onboard and export digests never collide.
15. Blocker order: state, `source_not_committed`, library blockers, remote blockers, M7 blockers, `dirty_paths`, `invalid_plan`.

`run_onboard(path, *, dry_run=False, commit=False, pr=False, expect=None, message=None, keep_local=(), names=(), environ=None) -> OnboardResult`:
1. `plan = plan_onboard(...)`. Without `commit` (or with `dry_run`) → `OnboardResult(plan, True)`. Nothing is written.
2. `--commit`: `expect` given and ≠ `plan.digest` → `plan_changed` (data = plan json). Any blocker → raise the first (`issues` for `invalid_plan`, data = plan json, `fix` in data when the blocker has one). The plan was just recomputed — that *is* the "plan se přepočítá".
3. **Library first** (when `plan.library_plan` has files): `import_items(items, source, subject, environ=environ, expect_head=plan.library["head"])`. Any `LibraryStoreError` (`push_failed`, `library_behind`, `plan_changed`, …) propagates; the repo is untouched. `library_commit = written.commit or head`.
4. **Manifest rebuild**: `onboarding.library_commit = library_commit` (head when nothing was written); replace the manifest `PlannedFile.content` in a new `PublishPlan` (same base/base_sha/blockers/digest; `dataclasses.replace`).
5. **Repo**: message = `(message or default subject)` + `"\n\n"` + `_report_text(plan)` (report rows `- <code> <subject>: <message>`, file list, `Plan digest: <digest>`, `Library commit: <sha>`). Default subject `f"factory: onboard {root.name} (pre_library) with the library {library.name}"`. Direct → `publish.publish_direct(root, settings=…, plan=…, message=…, store=_store(root), materialize=True, command="onboard")`. PR → `publish.publish_pr(..., message=subject, body=report text, prefix=…, branch=ONBOARDING_BRANCH)`. After success apply `plan.exclude` with `gitops.ensure_excluded` as `commit_init` does.
6. Repo failure after a library commit → re-raise as `LibraryStoreError(exc.code, f"{msg}; the library already has the new versions ({sha[:12]}); run factory onboard again, it connects them", data={…plan json, "library_commit": sha, "fix": "factory onboard --dry-run"})`. Map `ProviderError` → `LibraryStoreError(code)`, `RuntimeError` → `commit_failed`, like `config_edit._write_repo`.

Re-running after a failed repo push: the library now has the versions (own history or another item's head) → all `linked`, library plan empty, digest differs only in the library head → user re-runs `--dry-run` and `--commit --expect`.

## 2. Small changes outside `onboard/`

- `providers/git.py`: add `remote_branch_exists(root, remote, branch) -> bool | None` (`git ls-remote --heads <remote> refs/heads/<branch>`; None on non-zero exit; True when a line ends with `\trefs/heads/<branch>`). No other network calls.
- `providers/publish.py`:
  - `publish_pr(..., branch: str | None = None)`: with `branch`, use it instead of `git.next_numbered_branch` (a local ref that already exists makes `update-ref … ""` fail → `commit_failed`). Callers unchanged.
  - split `remote_state` into `fetch` + `compare_remote(root, remote, base, base_sha, theirs)`; `remote_state` keeps its signature and behaviour (calls both).
- `providers/base.py`: no change needed unless you want `find_open_pr` for the onboarding branch — not required (the remote branch check covers an open PR).
- `cli.py`:
  - `SUBCOMMANDS`: add `("onboard", "extract this repo's own factory configuration once into the library and a committed .factory/ with a manifest")` after `init`; module docstring list; `build_parser` → `_add_onboard_command`; `_dispatch` → `_onboard`.
  - `_add_onboard_command`: `--repo PATH`, `--dry-run`, `--commit`, `--pr`, `--expect DIGEST`, `-m/--message TEXT`, `--keep-local TYP/JMÉNO` (`action="append"`, default `[]`), `--name TYP/JMÉNO=NOVÉ` (append), `--json`. Description in the style of `_add_adopt_command`: the procedure, blockers and report codes (the skill generator lists it).
  - `_onboard_conflict`: `--dry-run` with `--commit`; `--expect`, `-m` or `--pr` without `--commit` (allow `--pr --dry-run`, as init) → `conflicting_options`.
  - Parse `TYP/JMÉNO` (type in `agent|workflow`, valid name) and `TYP/JMÉNO=NOVÉ` → `invalid_value` on bad syntax.
  - `_onboard`: `run_onboard`; errors via `_library_fail(exc, args.json, "factory onboard")`; `--json` → `_emit_ok(result.to_json(), result.warnings)`; text: report rows (`{code:<14} {subject}  {message}`), `library:` plan files, repo files (`{action:<7} {path}`), exclude lines, blockers, `digest`, and `next: factory onboard --commit [--pr] --expect <digest>` when no blockers; after commit the commit/PR line like `_init_plan`.
- `skill/codes.py`: add to `_CODES` (exit `"2"`): `already_onboarded`, `not_installed`, `sssf_not_supported`, `source_not_committed`, `onboarded_in_remote`, `onboarding_pending`, `remote_unchecked`, `name_taken` (check existing ones first: `config_not_committed`, `library_missing`, `library_dirty`, `library_behind`, `library_diverged`, `plan_changed`, `push_failed`, `dirty_paths`, `invalid_plan`, `not_on_base`, `run_in_progress`, `base_behind`, `base_diverged`, `unknown_item`, `invalid_value`, `conflicting_options` already exist — don't duplicate). Add `ISSUE_CODES["onboard_report"] = REPORT_CODES` order and `ISSUE_CODES["onboard"] = ("no_remote", "gitignore_dirty", "harness_missing", "unknown_workflow")` (warnings).
- `skill/skill.md` § "Onboarding and adopt": a numbered procedure for `factory onboard`:
  1. `factory check --json` → state `pre_library`, action `onboard`.
  2. `factory onboard --dry-run --json` (optionally `--keep-local`, `--name`, `--pr`); the plan fetches `<remote> <base>` and lists the onboarding branch (the only network step).
  3. Show the user `data.report` (codes), `data.files`, `data.library_plan.files` and `data.digest`; resolve blockers (list each code with its fix).
  4. Only with consent: `factory onboard --commit [--pr] --expect <digest> [-m TEXT] --json`; library first, then repo; `plan_changed` → back to 2; failure after the library push → run again.
  5. Next machines: `factory adopt`. Never onboard twice.
  Mention the report codes and what each means, and that existing `.factory/` files stay byte-identical.
- `onboard/__init__.py`: export `plan_onboard`, `run_onboard`, `OnboardPlan`, `OnboardResult`, `REPORT_CODES`, `ReportRow`, `Extraction`, `ONBOARDING_BRANCH`; docstring no longer says "not here yet".
- `justfile`: no change needed (`just factory onboard …` already passes through).

Typing: mypy strict as the rest of the package; no `Any` leaks in public signatures beyond `to_json`. Ruff format.

## 3. Tests — `aifactory/tests/onboard/test_onboard.py` (+ helpers in `onboard_repo.py`)

No model, no network: bare remotes in `tmp_path`, `HAIFA_HOME` per "machine" (copy fixtures from `test_adopt.py`: `identity`, `_machine`, library `remote`). Set `git config user.name` in the repo (for `by`). Repo remote = a bare repo `origin.git` with `main` pushed. Use `git_provider: local` in tests that exercise `--pr` (rewrite config.yaml in the copy before committing; HAIFA's is `github`).

Helpers to add in `onboard_repo.py`:
- `haifa_backlog(repo)`: a minimal valid backlog in `backlog/` whose tasks name `simple-sdlc` and `plan-build-test` (and one `build-test-review`) — copy the shape of an existing fixture backlog (search `tests/backlog` / `repo_templates.py` for a writer) so `_base_tasks` loads it with HAIFA's `config.yaml` (`levels: [project, step, task]`).
- `bare_origin(repo, tmp)`: create bare remote, `git remote add origin`, push main.
- `sandbox_factory(repo)`: HAIFA copy with modified prompts of all 4 agents and of `simple-sdlc` workflow added to `.factory/workflows/` with a modified validation rule (just change text that keeps the workflow valid), simulating haifa-sandbox.
- `library_with_versions(items)`: on top of `store.init_library`, `store.import_items` of the repo copies whose version is not in the seed (so a library "seeded earlier" has HAIFA's reviewer version in its history), then re-import the seed version so the head is the seed again. Compute dynamically from `repo_version` vs `packaged_seed()`.

Cases (each asserts JSON envelope via `run_json` where useful, plus git state):
1. **HAIFA copy** (`copy_haifa_factory` + backlog + origin; library prepared by `library_with_versions` incl. `build-test-review`): `--dry-run` → no blockers; every agent/workflow row `linked`; `library_plan` is None/empty; files = manifest + `.factory/workflows/simple-sdlc.yaml` + `.factory/workflows/plan-build-test.yaml` + `.gitignore`; `left_in_place` rows for `config.yaml`, `agents.yaml`, `adws/`; working tree `snapshot` and `git_state` unchanged except remote-tracking refs (compare `refs/heads/*` and index). Then `--commit --expect <digest>` → committed and pushed to origin; library HEAD unchanged; manifest in base has `onboarding.source == "pre_library"`, `source_commit` = old base sha, `by` = user.name, `library_commit` = library head, items for all 4 agents + 3 workflows; `repo_state(...)` now `onboarded`.
2. **Bytes of the source unchanged**: in case 1, for every path in old base under `.factory/`, `git rev-parse <new>:<path>` == `<old>:<path>`; `git diff --name-status old new` has only `A` under `.factory/` and `M`/`A` `.gitignore`, and the `.gitignore` diff only adds lines.
3. **haifa-sandbox copy** (library fresh from seed): modified agents → report `converted`, library gets new items named `<slot>-<slug>` (seed has `planner` … so the name is taken; slug from the repo folder name, e.g. folder `haifa-sandbox` → `planner-haifa-sandbox`); `simple-sdlc` modified → `simple-sdlc-haifa-sandbox`; one library commit pushed to the library remote **before** the repo commit (assert library remote has it). `--name agent/builder=builder-x` → that name. A workflow absent from library → new item `<name>` (name free).
4. **haifa-sandbox with `--keep-local`** for the 4 agents and `workflow/simple-sdlc` → report `carried_over`, no library write, manifest entries point to `planner` … with the library head version; after commit `factory config items` (or `library.state.item_states`) shows them `modified`.
5. **`already_onboarded`**: after case 1 run `onboard --dry-run --json` again → `data.blockers[0].code == "already_onboarded"`; `--commit` → exit 2, `error.code == "already_onboarded"`; repo and library unchanged ("druhý onboard po úspěchu").
6. **`onboarded_in_remote`**: clone A and clone B of the same origin; onboard + commit from A; B (stale, still `pre_library` locally) `--dry-run` → blocker `onboarded_in_remote` with fix mentioning `factory config pull` and `factory adopt`.
7. **`onboarding_pending`**: push a branch `factory-config/onboarding` to origin → blocker. Also: `--commit --pr` success creates that branch on origin (local provider), a second plan from another clone shows `onboarding_pending`.
8. **`remote_unchecked`**: origin URL set to a non-existent path → blocker `remote_unchecked`; **`no_remote`**: repo without remote → warning `no_remote`, commit works locally (base advanced, not pushed).
9. **Library push rejected**: library bare remote with an executable `hooks/pre-receive` that `exit 1` (sandbox case, so there are items to write) → `--commit` exit 2 `push_failed`; repo `refs/heads/main`, origin `main`, working tree and index unchanged; library HEAD unchanged.
10. **Repo push rejected after library push, then retry**: origin with rejecting `pre-receive` → `--commit` fails `push_failed`, `data.library_commit` set, library remote has the new items; remove the hook; `--dry-run` again → all agents `linked` (to the pushed `…-<slug>` items), library plan empty; `--commit --expect` succeeds; the manifest points to the new items.
11. **Other blockers**: `source_not_committed` (edit `.factory/agents.yaml` in the working tree after commit), `library_missing` (no library in `HAIFA_HOME`), `library_dirty` (untracked file in library), `sssf_not_supported` (`stamp_sssf` repo), `not_installed` (plain repo), `config_not_committed` (config only in working tree), `plan_changed` (`--expect` wrong digest), `conflicting_options` (`--expect` without `--commit`).
12. **Digest**: same inputs → same digest across two `--dry-run`s (time excluded); a new library commit (e.g. import an unrelated item) changes the digest.

Mark nothing `slow` unless a test takes >2 s; keep fixtures small. `tests/test_skill.py` must stay green (new codes registered, `onboard` documented, `--json` present).

## 4. Verification

```bash
just test tests/onboard tests/test_skill.py tests/providers   # focused
just test                                                       # whole suite
just typecheck
just lint
```
Also manually (no commit): `cd <tmp copy of HAIFA> && uv run --project aifactory factory onboard --dry-run --json` must leave the copy's working tree unchanged. Never run `factory onboard --commit` in this repo or its main checkout (HAIFA onboards the engineer).

## 5. Out of scope
sssf conversion (O4; only `sssf_not_supported` + the `Extraction` interface), dashboard/API, deleting `adws/`, backlog conversion (F6), `factory check` changes.
