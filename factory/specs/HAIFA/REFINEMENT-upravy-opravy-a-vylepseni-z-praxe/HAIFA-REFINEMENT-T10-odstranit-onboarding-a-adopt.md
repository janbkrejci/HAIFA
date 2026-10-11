# Plan: HAIFA-REFINEMENT-T10 Remove onboarding (sssf, pre_library) and `factory adopt`

All paths are relative to the worktree root. Python lives in `aifactory/src/aifactory/`, tests in `aifactory/tests/`, Vue in `aifactory/web/src/`.

Do not touch `.factory/`, `vendor/`, `prototype/`, `CLAUDE.md`, `AGENTS.md`, `docs/decisions.md`. Leave comments in `engine/`, `harness/config.py` (`SSSFConfig`), `pyproject.toml`, `defaults/workflows/simple-sdlc.yaml` (its first-line comment mirrors `.factory/workflows/simple-sdlc.yaml`, which is protected) and the frontend "Port of the sssf visualizer" comments as they are. The word "adopt" in `providers/`, `review/`, `run/` and `cli.py` `task publish` help means "adopt an existing PR" and stays.

## D1. New repo state

New module `aifactory/src/aifactory/config/repo_state.py` replaces `onboard/state.py`. Keep it read-only like the old one (`git ls-tree`, `git cat-file` through `aifactory.config.source.git`, file-system checks for the working tree).

States, first match wins, read from the tree of `base`:

| state | condition | action |
|---|---|---|
| `installed` | `.factory/manifest.yaml` in base | `None` |
| `unsupported` | `.factory/config.yaml` or `.factory/agents.yaml` in base (no manifest), or any entry under `adws/` in base | `None` |
| `uncommitted` | `.factory/manifest.yaml`, `.factory/config.yaml` or `.factory/agents.yaml` only in the working tree | `config_commit` |
| `none` | none of these | `init` |

```python
RepoStateName = Literal["installed", "unsupported", "uncommitted", "none"]
RepoAction = Literal["init", "config_commit"]
REPO_STATES: tuple[RepoStateName, ...] = ("installed", "unsupported", "uncommitted", "none")
STATE_ACTIONS: dict[RepoStateName, RepoAction | None] = {
    "installed": None, "unsupported": None, "uncommitted": "config_commit", "none": "init",
}

@dataclass(frozen=True)
class RepoState:
    repo: str
    base: str
    commit: str | None
    state: RepoStateName
    config_in_base: bool          # config.yaml or agents.yaml (or manifest) committed in base
    manifest: Manifest | None = None
    manifest_error: str | None = None

    action -> STATE_ACTIONS[state]
    onboarding / library properties: unchanged (manifest blocks)
    to_json(): repo, base, commit, state, action, onboarding, library, manifest_error
```

`config_in_base` is true for `installed` and for `unsupported` when `.factory/config.yaml` or `.factory/agents.yaml` is in base. It is false for an sssf-only repo. It is not part of `to_json()`.

Keep `resolve_base(root, base)` and `repo_state(root, base=None)` with the same signatures. `_base_paths` lists `.factory/` and `adws/` only (drop `adws/adw_sssf_config/`). Remove `sssf_leftover`, `alternate_rosters`, `rosters`, `_is_roster`, `SSSF_CONFIG_DIR`. The module docstring documents the table above and says HAIFA does not take over a repo in state `unsupported`.

## D2. Delete

1. `aifactory/src/aifactory/onboard/` (whole package incl. `sssf_stock/`).
2. `aifactory/src/aifactory/web/sssf_cleanup.py`.
3. `aifactory/web/src/components/factory/OnboardingPanel.vue`, `OnboardingPanel.test.ts`, `aifactory/web/src/lib/onboarding.ts`.
4. `aifactory/tests/onboard/` (whole directory incl. `golden/`).
5. `aifactory/tests/e2e/test_onboarding_browser.py`, `aifactory/tests/e2e/test_team_onboarding_browser.py`, `aifactory/tests/e2e/team_flow_e2e.py`.
6. `docs/sssf/` (whole directory, at the repo root).

Before deleting `onboard/`, record the error codes raised there (step A8 needs them):
`grep -rhoE '"[a-z_]+"' aifactory/src/aifactory/onboard/*.py | sort -u > /tmp/t10_onboard_literals.txt`

## A. Backend changes

A1. `config/manifest.py`
- `OnboardingSource = Literal["init"]` (what HAIFA writes).
- `LegacyOnboardingSource = Literal["sssf", "pre_library"]` with a comment: written by the removed `factory onboard`, still read so older manifests load.
- `Onboarding.source: OnboardingSource | LegacyOnboardingSource`. Docstring: "Written once by factory init and never changed after."
- Module docstring: drop "onboarding mark" wording if it implies onboard; keep the rest.

A2. `check/model.py`
- Import `RepoAction`, `RepoStateName` from `aifactory.config.repo_state`. Fix the comment that points to `aifactory.onboard.state`.
- `Action = Literal["init", "update", "export", "config_commit", "config_pull"]` (drop `onboard`, `adopt`).
- Remove `sssf_leftover` and `alternate_rosters` from `CheckReport` (fields and `to_dict`/JSON).

A3. `check/context.py`
- Import from `aifactory.config.repo_state`.
- Line ~108: `state.state != "onboarded"` becomes `!= "installed"`.
- `committed` returns `self.state.config_in_base` (old: state in onboarded/pre_library, which is the same set of repos).
- `installed` returns `self.committed or self.state.state == "uncommitted"`.

A4. `check/__init__.py`: drop `sssf_leftover=` and `alternate_rosters=` when building `CheckReport` (both the in-repo and outside-repo constructors if present).

A5. `check/repo_rules.py`, function `install`:
- `none`: `factory_missing` unchanged.
- `uncommitted` (was `working_tree`): `config_not_committed` unchanged.
- `unsupported`: one finding `repo_unsupported`, scope `repo`, action `None`.
  - `config_in_base` true: severity `info`, message `f".factory/ in {ctx.base} has no manifest.yaml; HAIFA does not take over a configuration it did not install"`, fix `"HAIFA will not convert it; install factory into a repository without .factory/ with factory init"`.
  - `config_in_base` false (sssf `adws/`): severity `error`, message `f"{ctx.base} has an sssf installation in adws/ and no .factory/; HAIFA does not run or convert sssf"`, fix as above.
- `installed`: finding `repo_installed` (renamed from `repo_onboarded`), severity `info` or `error` on manifest error as today, fix `None`, action `None`. Rename `_onboarded_message` to `_installed_message`; text `f"installed from {block['source']} at {block['at']}{who} (factory {block['factory']})"`.
- Delete the `sssf_leftover` and `alternate_rosters` findings. Replace "onboarding state" in the docstring with "repo state".
- Line ~227: `ctx.state.state == "working_tree"` becomes `"uncommitted"`. Line ~471: `"onboarded"` becomes `"installed"`.
- `item_unknown` (~line 592): fix `f"the library does not know the version of {what}; export it with factory config export"`, action `"export"`.

A6. `cli.py`
- Remove the `onboard` and `adopt` entries from the command table (~lines 47-53), the dispatch at ~116-119 and ~3476-3479, and `_add_onboard_command`, `_onboard_conflict`, `_onboard_key`, `_onboard`, `_add_adopt_command`, `_adopt`. Drop imports that become unused.
- Module docstring line 8: drop `onboard`, `adopt`.
- `factory check` help (~146-153): states `installed, unsupported, uncommitted or none`, actions `config_commit or init` (or null), no flags, findings' action list without `onboard`, `adopt`.
- `factory init` help (~451): `existing_config (HAIFA does not take over existing configuration)`.
- ~1179 and ~1483-1484: `not_onboarded` fix text without `factory onboard` (see A7).
- `web/factory.py` imports `_onboard_key` from `cli`; that import goes away with A9.

A7. `library/`
- `install.py`: module docstring (lines ~9-11): "a repo with factory or sssf configuration but no manifest is refused (`existing_config`); HAIFA does not take it over". `_refuse`: keep detection (incl. `SSSF_CONFIG_DIR`), message `f"the repo has factory configuration without a manifest ({', '.join(found)}); HAIFA does not take over existing configuration"`, `data={"found": found}` (no `fix`).
- `install_commit.py`: docstring line ~20-21 same wording; `_state_blocker` `existing_config` blocker: same message, `fix=None` (check `Blocker` accepts it; it is optional elsewhere).
- `config_edit.py` (~150-163, docstring ~43): `not_onboarded` with manifest only in the working tree keeps fix `factory config commit`, message drops `(or factory onboard)`. No manifest at all: message `f"the repo has no {MANIFEST_FILE}; install factory with factory init"`, `data={"fix": "factory init"}`.
- `update.py` (~36-37, ~110-131): docstring and the `not_onboarded` error: with an existing `.factory/` the message says HAIFA does not take over a configuration without a manifest and data has no `fix` key (or `fix: None`); without `.factory/` `fix` stays `factory init`.
- `library/__init__.py` line 4 only names a design doc; leave it.

A8. `skill/codes.py`
- `ISSUE_CODES["repo_state"] = ("installed", "unsupported", "uncommitted", "none")`, `ISSUE_CODES["repo_action"] = ("config_commit", "init")`.
- Remove `ISSUE_CODES` keys `onboard_report`, `onboard`, `adopt_item`, `adopt`.
- `ISSUE_CODES["check"]`: remove `sssf_not_onboarded`, `pre_library_config`, `repo_onboarded`, `sssf_leftover`, `alternate_rosters`; add `repo_unsupported`, `repo_installed` (same position).
- Error codes: remove every code that was raised only by `onboard/` or the onboard/adopt API. After the deletions run, from `aifactory/`:
  ```sh
  uv run python -c "
  import re, pathlib
  from aifactory.skill.codes import ERROR_CODES
  src = [p for p in pathlib.Path('src/aifactory').rglob('*') if p.suffix in {'.py','.md'} and p.name not in {'codes.py','skill.md'}]
  text = ''.join(p.read_text('utf-8') for p in src)
  print([c for c in ERROR_CODES if f'\"{c}\"' not in text])"
  ```
  Remove each printed code that is in `/tmp/t10_onboard_literals.txt` or whose meaning mentions onboard/adopt/sssf (expected: `already_onboarded`, `sssf_roster_invalid`, `onboarded_in_remote`, `onboarding_pending`, `remote_unchecked`, the name-collision code at ~318, `not_installed` if only onboard used it, the uncommitted-`.factory/` onboard code at ~296). Leave codes unrelated to this task even if unused. Keep `not_onboarded` (still raised by `config_edit`, `update`) and rewrite its meaning without adopt/onboard: "the repo has no .factory/manifest.yaml in base (data.fix: factory init, or factory config commit when it is only in the working tree)".
- Rewrite meanings that mention onboard/adopt: `existing_config` (~244: "... HAIFA does not take it over"), `library_missing` (~173: drop the `factory adopt` clause), the lock/plan-changed text at ~146, `already_installed` if it mentions adopt.

A9. `web/factory.py`
- `ACTIONS` without `onboard`, `adopt`; drop their entries in the options map (~67-68) and status map entries for removed codes (`already_onboarded`, `onboarded_in_remote`, `onboarding_pending`, `sssf_roster_invalid`, and any other code removed in A8). Keep `not_onboarded: 409`.
- Delete `onboarding_hint` and its use in the report (~309). Line ~293-298: import `repo_state` from `aifactory.config.repo_state`.
- Delete the onboard/adopt branches in plan/apply (~347, ~414-437, ~578-676). Module docstring: drop "onboard and adopt".
- `web/app.py`: docstring ~96 and ~111-112 without onboard/adopt; line ~1320 `if req.action in ("export",)` becomes `req.action == "export"`.

A10. `web/repos.py`
- Import `repo_state` from `aifactory.config.repo_state`; drop `onboarding_hint` and `installation_paths` imports; fix the docstring at line ~13.
- `_factory(root)`: return `repo_state(root).to_json()` (drop the `inspect_only` parameter and its call-site argument).
- Remove `"sssf_paths"` from `inspect_repo`.
- Status: `not_installed` when `state == "none"` or (`state == "unsupported"` and not `config_in_base`); `uncommitted` when `state == "uncommitted"`; else as today. `_factory` returns JSON without `config_in_base`, so compute status from a `RepoState` (call `repo_state` once and keep the object, convert with `to_json()`). Replace `NOT_INSTALLED_STATES` accordingly.

A11. `web/overview.py`
- Import from `aifactory.config.repo_state`.
- `LOADABLE` check becomes `st.config_in_base`; `installed` becomes `st.config_in_base or st.state == "uncommitted"`. Remove the `NOT_INSTALLED`/`LOADABLE` constants if unused.
- `factory_state` values are now the new state names.

## B. Frontend changes (`aifactory/web/src/`)

B1. `lib/api.ts`
- `FactoryState = 'none' | 'uncommitted' | 'unsupported' | 'installed'`.
- `OnboardingSource = 'init' | 'sssf' | 'pre_library'` stays as a read type only if older manifests must display; simpler: `source: string` in `Onboarding`, and drop the `OnboardingSource` type. Pick one and keep `lib/repos.ts` consistent.
- `RepoFactory` and the report type at ~477-486: remove `onboarding_state`, `onboarding_pr`, `sssf_leftover`, `alternate_rosters`, `rosters`.
- `InspectResult`: remove `sssf_paths`.
- Remove `previewOnboarding`, `applyOnboarding` and the `./onboarding` import. Remove onboarding from the comment at ~525.

B2. `lib/repos.ts`
- `FACTORY_STATE_TEXT`: `none: 'Bez factory'`, `uncommitted: 'konfigurace jen v pracovním stromu (necommitnutá)'`, `unsupported: 'Nepodporováno: HAIFA tuto konfiguraci nepřevezme'`, `installed: 'Nainstalováno'`.
- `factoryStateText(state)`: drop the `prId` parameter and the two onboarding branches.
- `onboardingText`: `Nainstaloval ${by ?? 'neznámo'} ${time} z ${source}`; `ONBOARDING_SOURCE_TEXT` keeps only `init: 'factory init'`, unknown sources print raw.

B3. `lib/factory.ts`: remove `onboarded_in_remote` and `onboarding_pending` texts. `lib/overview.ts` ~105: `'working_tree'` becomes `'uncommitted'`.

B4. `views/FactoryView.vue`: remove the `OnboardingPanel` import and element (~174), the `sssf_leftover`/`alternate_rosters` warnings (~166-171), `onboarding_state`/`onboarding_pr` in the state cell (~137). Rename the `Onboarding` label (~158) to `Instalace`. Header comment ~3: drop "onboarding". If `operationBusy` existed only for the panel, keep it only if other code uses it.

B5. `components/repos/InspectCard.vue`: state cell without `onboarding_state`/PR link (~69); `openHref` uses `'installed'`; comment ~26 says "installed". `components/factory/PlanView.vue` comment ~2: drop "onboarding".

B6. Tests and fixtures: `test/factoryFixtures.ts`, `test/overviewFixtures.ts`, `App.test.ts` (~91, ~535), `views/FactoryView.test.ts`, `views/ReposAddView.test.ts`, `lib/factory.test.ts` (~20), `components/factory/FactoryOperation.test.ts` (keep `not_onboarded`, it still exists). Replace state names, remove dropped fields, delete the adopt mock (~42 FactoryView.test), the `onboarded_in_remote`/`onboarding_pending` case (~443 ReposAddView.test) and the sssf onboarding text expectations. Add:
- `FactoryView.test.ts`: an `installed` report renders no onboarding panel and no adopt/onboard button (`wrapper.text()` contains neither `Onboard` nor `Adopt`), and an `unsupported` report shows `Nepodporováno`.
- `ReposAddView.test.ts`: `it.each(['none', 'unsupported', 'uncommitted', 'installed'])` replaces the old state list.

B7. Run `just web-build` so `aifactory/src/aifactory/web/static` matches the source.

## C. Python tests (`aifactory/tests/`)

C1. New `tests/config/test_repo_state.py` (temp git repos, no network): `installed` (manifest committed; `onboarding`/`library` in JSON; a broken manifest sets `manifest_error`), `uncommitted` (config only in working tree, action `config_commit`), `none` (empty repo, action `init`), `unsupported` with `.factory/config.yaml` no manifest (`config_in_base` true, action None), `unsupported` with only `adws/adw_sssf_config/sssf.config.yaml` (`config_in_base` false), installed wins over `adws/` next to a manifest, `to_json()` keys exactly `repo, base, commit, state, action, onboarding, library, manifest_error`, nothing written (`git status --porcelain` empty and index mtime unchanged, as the old test did if helpful). Reuse helpers from `tests/check/factory_check_repo.py` or `tests/web/multi_repo.py`.

C2. `factory check` over each state, in `tests/check/test_factory_check.py`:
- `make_check_repo` repos are now `unsupported` with config: replace `pre_library_config` with `repo_unsupported` (`info`, action None), `report.state == "unsupported"`, `action is None`. Lines ~57-69, ~214, ~307, ~358.
- `uncommitted` (~84-92, ~113, ~318): state name `uncommitted`.
- Add `test_sssf_repo_is_unsupported`: only `adws/adw_sssf_config/x.yaml` committed gives `repo_unsupported` `error`, no repo rules that need install run.
- Assert JSON has no `sssf_leftover`/`alternate_rosters`.
- `tests/check/test_factory_check_items.py`: `_onboarded` becomes `_installed`, state `installed`, `repo_installed`; `item_unknown` expects action `export`; ~127 expects `unsupported`; delete `test_sssf_leftover` (~186) and replace with a test that a manifest repo with `adws/` is `installed` and reports no sssf finding.
- `tests/check/test_factory_check_cli.py`, `test_factory_check_machine.py`: update state names/codes where they appear.

C3. Other tests to update:
- `tests/config/test_config_manifest.py`: `sample()` uses `source="init"`; add a test that a manifest text with `source: sssf` and with `source: pre_library` still parses; `source: other` still fails (~106).
- `tests/web/multi_repo.py`: `Onboarding(source="init")`; drop `SSSF_ROSTER` if unused after C3 (or keep for the unsupported test). Helper `onboard()` may be renamed `install()`; update its users (`test_web_repos.py`, `test_obs_cli.py`) if renamed.
- `tests/web/test_web_repos.py` (~209-227, ~335-365): sssf repo is `unsupported` with action None and status `not_installed`; `.factory/` without manifest is `unsupported` with status `ok`; manifest repo is `installed` with action None. Inspect JSON has no `sssf_paths`, `onboarding_state`.
- `tests/web/test_web_factory.py`: ~484 `installed`, ~494 `unsupported`; delete `test_dashboard_onboarding_hint_uses_known_refs` and `test_onboarding_preview_links_pending_pr` (~560-600). Add a test that `POST /factory/plan` with action `onboard` and with `adopt` is rejected as an unknown action (use the existing invalid-action helper; ~218-222 in test_web_factory_items shows the shape).
- `tests/web/test_web_factory_items.py`: delete the `onboard_repo` import (~34-36), `test_onboard_sssf_and_remote_blocker`, `test_adopt_digest_import_and_noop`; in the invalid-request table (~218-222) turn the onboard/adopt rows into "unknown action" cases.
- `tests/library/test_library_install.py` (~278-288): message no longer contains `factory onboard`; assert `"factory onboard" not in message` and `"fix" not in data`.
- `tests/library/test_library_install_commit.py` (~399-409): blocker `fix` is None.
- `tests/library/test_library_config_edit.py` (~398-401): fix `factory init`.
- `tests/library/test_library_update.py` (~466): adjust if it asserts the fix.
- `tests/library/test_library_seed.py`: remove `VENDOR_SCOUT` and the final `remaining == vendor` comparison in `test_scout_prompts_adapted_from_vendor`; keep the `adw_id` and inserted-line assertions, rename the test to `test_scout_prompts_have_handoff_and_git_lines`.
- `tests/validation/test_agent_prompts_handoff_dir.py` (~15, ~28-29) and `tests/validation/test_validation_template.py` (~251-252): drop the `sssf_stock` exclusion.
- `tests/test_skill.py`: rewrite `test_skill_installation_and_onboarding_procedures` (~157-190) into `test_skill_installation_procedure`: the skill contains `factory init`, the four state names and `repo_unsupported`, and contains none of `factory onboard`, `factory adopt`, `pre_library`, `sssf_leftover`. ~223 keeps manifest wording checks that still hold.
- `tests/test_smoke.py` (~35): drop `"onboard"`, `"adopt"` from `setup`.
- `tests/e2e/test_f3_browser.py` (~549-553): fixture state `unsupported`, drop the removed fields.
- `tests/e2e/test_factory_install_browser.py`: no change needed (dashboard install replaces `.factory/`, no onboarding). Leave it unless it fails.

C4. Final guard (no test needed, run by hand): from the worktree root
`grep -rnE "aifactory\.onboard|vendor/sssf|sssf_stock|factory onboard|factory adopt|pre_library|sssf_leftover|alternate_rosters" aifactory --exclude-dir=node_modules --exclude-dir=static --exclude-dir=.venv`
must print only `engine/` port comments, `pyproject.toml` comments, `defaults/workflows/simple-sdlc.yaml` line 1, and the `LegacyOnboardingSource` line in `config/manifest.py` plus its test.

## E. Skill text (`skill/skill.md`)

- State table at the top (~28-35): rows `none` (`init`), `uncommitted` (`config_commit`), `installed` (no action; run `factory update` for items), `unsupported` (no action; HAIFA does not take over `.factory/` without a manifest or sssf `adws/`). No adopt/onboard sentences.
- Check section (~445-518): new state and action lists, findings `factory_missing`, `config_not_committed`, `repo_unsupported`, `repo_installed`; no flags; action list without `onboard`, `adopt`; `item_unknown` action `export`; remove `sssf_leftover` from ~501.
- ~269: drop "(or retain the configuration converted by `factory onboard`)".
- Init blockers (~557-559): `already_installed` says run `factory update`; `existing_config` says HAIFA does not take over existing configuration.
- Manifest (~867-868): `source` is `init`; older manifests may carry `sssf` or `pre_library` and still load.
- ~926 and ~1011: `not_onboarded` fix `factory init`.
- Delete the whole "Onboarding and adopt" section (~1017 to the end of the sssf description) and any table-of-contents/section-list entry for it; `test_skill_sections` lists required sections, update it if it names that section.
- Every code in `ERROR_CODES`/`ISSUE_CODES` must still appear in the skill (`test_skill_lists_error_codes`).

## Verification

From the worktree root:
1. `just test` (frontend typecheck, vitest, pytest).
2. `just typecheck` and `just lint` (`cd aifactory && uv run ruff format .` if format fails).
3. `just web-build`, then `git status` shows `aifactory/src/aifactory/web/static` updated.
4. C4 grep.
5. `cd aifactory && uv run factory --help` lists neither `onboard` nor `adopt`; `uv run factory --skill | grep -c "factory onboard\|factory adopt"` prints 0.
6. `just e2e` if Chrome is available (the deleted onboarding browser tests must not be referenced).
