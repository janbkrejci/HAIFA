# HAIFA-S06-T04 (O4): Převod instalace sssf při onboardingu

Design reference: `docs/design/library-onboarding-distribution.md` §7 AR30–AR36 (the conversion table is AR32), §11 V13. The O2 spec `specs/HAIFA-S06-T03-jednorazovy-onboarding-factory-onboard-a.md` describes the plan/commit machinery this task reuses. Read both before you start.

Allowed paths: `aifactory/`, `justfile`, this spec, `app_docs/HAIFA-S06-T04-…md`. Do NOT touch `vendor/`, `prototype/`, `adws/`, `.factory/`, `.claude/`, `CLAUDE.md`, `docs/`. Stock data is **copied** from `vendor/sssf/templates/` into the package; `vendor/` itself stays as it is.

## 0. What exists and gets reused

| Need | Existing code |
|---|---|
| plan / commit / digest / blockers / remote check | `onboard/onboard.py` (`plan_onboard`, `run_onboard`, `_state_blocker`, `_short_plan`, `_library_blockers`, `_check_remote`, `_check_invariant`, `_stable`, `onboard_digest`, `report_text`, `_commit_repo`) |
| report rows, `Extraction`, linking, naming | `onboard/extract.py` (`ReportRow`, `Extraction`, `REPORT_CODES`, `slug`, `_library_heads`, `_link`, `_new_name`, `_check_options`) |
| repo state, `rosters`, `alternate_rosters` | `onboard/state.py` `repo_state(root, base=None)` |
| base tree reading (ls-tree, cat-file --batch) | `library/tree.py` `tree_files(root, sha, paths)` → `TreeFile(path, mode, blob)`, `read_blobs(root, blobs)` |
| detection (M8) | `library/detect.py` `detect(root)` → `Detected(remote, base, info.provider, info.azure, …)` |
| settings | `library/install.py` `project_settings(...)`, `_Source`, `_workflow_agents(item)`, `_git_out`, `_now`; `library/agent.py` `roster_entry(item, settings)`; `config/settings.py` `ProjectSettings`, `check_timeout`, `split_command` |
| validation | `library/install_commit.py` `_validate`, `_gitignore`, `_dirty`, `_store`, `EXCLUDE_PSEUDO_PATH`; `library/config_edit.py` `_missing_harnesses()` |
| versions | `library/version.py` `agent_version`, `tree_version`, `workflow_version` |
| library writes | `library/store.py` `SeedItem`, `NewFile`, `import_items`, `LibraryStoreError`; `library/load.py` `library_path` |
| library agent defaults | `library/model.py` `AgentDefaults` (has `extensions`), `check_name`; `harness.canonical` (`claude_code` → `claude`) |
| manifest | `config/manifest.py` `Onboarding(source="sssf")` already allowed, `ManifestItems(extensions=…)` |
| test helpers | `tests/onboard/onboard_repo.py` (`stamp_sssf`, `init_repo`, `commit_all`, `bare_origin`, `reject_pushes`, `worktree_snapshot`, `git_state`, `write`), `tests/onboard/test_onboard.py` (fixtures `identity`, `library_remote`, `_onboard`, `_rows`, `_codes`), `tests/cli_json.py` `run_json` |

Facts verified on this worktree (stock vendor templates):
- Stock roster `vendor/sssf/templates/sssf.config.yaml`: defaults `coding_agent: pi`, `thinking: medium`, `harness_engineering: []`, `tools`, `protected_files` (`adws/adw_modules/`, `adws/adw_sssf_config/`, `adws/adw_*.py`), `data_dir`; top-level `observability`. Agents planner (pi, `thinking: high`, `harness_engineering: [adws/adw_data/harness_engineering/subagents.ts]`, `writes: [specs/]`), builder (claude_code, opus, high, no writes), scout (pi, subagents.ts, `writes: []`), reviewer (claude_code, opus, `writes: []`), documenter (pi, `writes: [app_docs/, docs/, "**/*.md", "*.md"]`). Prompt paths `adws/adw_data/prompt_engineering/<agent>/{system,user}.md`.
- sssf stock purposes differ from the seed purposes (e.g. planner "Turn a request into a plan…" vs seed "Turn the task into a short plan…").
- Seed prompts differ from sssf stock prompts by small edits (builder/system.md: seed appends 2 lines at the end; reviewer/system.md: seed inserts one line after "Your spec is…" and one after "Not your job…").
- Stock chain blob ids (`git hash-object vendor/sssf/templates/adws/<f>`): `adw_plan.py` 07e5bfe41fac422063e6f3ddbfa2763e42e97fc4, `adw_plan_build.py` 7e0a35bf063004ee2b886076b6b1741fae0ca4f8, `adw_plan_build_test.py` 962fae110bd4983107c72707b27a4a57c348c3a6, `adw_simple_sdlc.py` a6a5c4c1c4be7fb2bf3de4c80cdb798c8df23ffc (second stock version 3f5d48378a8daefb7e9dfa79af8279454db42d34, not reproducible here — constant only), `adw_document.py` 96789aa53f64904bab5984ace733edef234ada86, `adw_scout.py` 39a008f8eda63c783b942f47a5ff33ddd3a347f7. Other stock scripts (no HAIFA workflow): `adw_build.py`, `adw_build_test.py`, `adw_build_review.py`, `adw_compose.py`, `adw_models.py`, `adw_plan_build_test_quality.py`, `adw_prompt.py`, `adw_quality.py`.
- Library workflows in the seed (`defaults/workflows/`): `plan`, `plan-build`, `plan-build-test`, `simple-sdlc`, `document`, `scout` (+ internal `resolve*`).
- `quality.py` stock: `test` block `argv=["just","test"]`, `timeout_seconds=600`; `lint` `argv=_placeholder("lint")`; `typecheck` `["just","typecheck"]`; `build` `["just","build"]`.
- `harness_engineering/subagents.ts` imports `./themeMap.ts` (`import { applyExtensionDefaults } from "./themeMap.ts";`).
- HAIFA `agents.yaml` does not accept `prompt_engineering`; the engine loads pi extensions from `harness_engineering` (paths relative to the repo root, cwd = repo) and refuses `harness_engineering` on non-pi agents. `config_edit.reasons` recognises an extension binding as a `harness_engineering` entry under `.factory/extensions/<name>/`. There is no `extensions:` key read from `agents.yaml`. **So the repo binding "extensions" is written as `harness_engineering: [.factory/extensions/<name>/<name>.ts]`, and new library agent items carry `defaults.extensions: [<name>]`.**

## 1. Package data `aifactory/src/aifactory/onboard/sssf_stock/`

Copy (bytes identical) from `vendor/sssf/templates/`:
```
sssf_stock/
  prompts/<agent>/system.md, user.md      # 10 files, agents planner builder scout reviewer documenter
  quality.py.txt                          # adws/adw_modules/quality.py (not .py: no lint/mypy/import)
  stock.yaml
```
`stock.yaml` (write by hand, blob ids via `git hash-object`):
```yaml
# Stock sssf (vendor/sssf/templates) as factory onboard knows it; a machine without vendor/ can convert.
agents:          # roster purpose and prompt blob ids of every stock agent
  planner: {purpose: "Turn a request into a plan the builder can implement without asking questions.", system: <blob>, user: <blob>}
  builder: {...}
  scout: {...}
  reviewer: {...}
  documenter: {...}
chains:          # blob id of a stock chain -> library workflow
  07e5bfe4…: plan
  7e0a35bf…: plan-build
  962fae11…: plan-build-test
  a6a5c4c1…: simple-sdlc
  3f5d4837…: simple-sdlc
  96789aa5…: document
  39a008f8…: scout
chain_files:     # file name of a convertible chain -> workflow (a different blob = modified chain)
  adw_plan.py: plan
  adw_plan_build.py: plan-build
  adw_plan_build_test.py: plan-build-test
  adw_simple_sdlc.py: simple-sdlc
  adw_document.py: document
  adw_scout.py: scout
scripts:         # other stock top-level adws/adw_*.py: file -> blob id
  adw_build.py: <blob>
  …
modules:         # adws/adw_modules/<file> -> stock blob id (quality.py included, handled by ast)
  __init__.py: <blob>
  …
```
Use full 40-char ids. Hatch already ships all files under `src/aifactory` (verify with `uv build` or by checking `pyproject.toml` `packages = ["src/aifactory"]`; no change expected).

### `onboard/stock.py` (new)
- `@functools.cache def stock() -> Stock` reads `sssf_stock/stock.yaml` and the prompt files once (path from `Path(__file__).parent / "sssf_stock"`).
- `Stock` dataclass: `agents: dict[str, StockAgent(purpose, system: bytes, user: bytes, system_blob, user_blob)]`, `chains: dict[blob, workflow]`, `chain_files: dict[file, workflow]`, `scripts: dict[file, blob]`, `modules: dict[file, blob]`, `quality_source: str`.
- `SSSF_ROSTER = "adws/adw_sssf_config/sssf.config.yaml"`.

## 2. Pure helpers

### `onboard/merge.py` (new) — prompt merge (AR32)
```python
MergeKind = Literal["stock", "same", "clean", "union", "conflict"]
@dataclass(frozen=True)
class MergeResult: kind: MergeKind; text: bytes; quote: str | None = None
def merge_prompt(base: bytes, ours: bytes, theirs: bytes) -> MergeResult
def quote_change(base: bytes, ours: bytes, limit: int = 20) -> str  # difflib.unified_diff base->ours, n=0, labels "sssf"/"repo", max `limit` lines + "… (N more lines)"
```
- `ours == base` → `stock`, text = theirs.
- `ours == theirs` → `same`, text = ours.
- Else write `ours.md`, `base.md`, `theirs.md` into a `tempfile.TemporaryDirectory()` and run `git merge-file -p --diff3 --marker-size=13 -L repo -L sssf -L library ours.md base.md theirs.md` (via `providers.git.run_bytes(tmp, [...])`; `git merge-file` touches no repository). Exit 0 → `clean` (stdout). Exit 1..127 → parse stdout conflict blocks (lines starting with 13×`<`, 13×`|`, 13×`=`, 13×`>`); when **every** block has an empty base section (`|||` … `===` has no lines) the conflict comes only from insertions → rerun with `--union` (same labels, no `--diff3`) → `union` with that stdout. Otherwise → `conflict`, text = theirs, `quote = quote_change(base, ours)`. Exit ≥128 or negative → `RuntimeError` (programming/environment error).

### `onboard/quality.py` (new) — `quality.py` via `ast`, nothing runs
```python
@dataclass(frozen=True)
class QualityBlock: name: str; argv: tuple[str, ...] | None; placeholder: bool; timeout: int | None; literal: bool
def parse_quality(source: str) -> tuple[dict[str, QualityBlock], str | None]   # blocks by `name=` keyword, error text when unparseable
def same_as_stock(source: str, stock_source: str) -> bool
```
- `ast.parse`; walk every `ast.Call` whose func is `Name("QualityCheckSpec")` (or attribute ending in it); `name` keyword must be a str Constant (else skip). `argv`: `ast.List`/`ast.Tuple` of str Constants → tuple (`literal=True`); `Call(func=Name("_placeholder"))` → `placeholder=True`; anything else → `literal=False`. `timeout_seconds`: int Constant (not bool) → value; absent → None; non-literal → `literal=False`.
- Validate a literal argv with `config.settings.split_command` and the timeout with `check_timeout` (ValueError → treat as non-literal).
- `same_as_stock`: parse both, replace the values of the `argv` and `timeout_seconds` keywords of every `QualityCheckSpec` call with `ast.Constant(None)`, compare `ast.dump(tree)` (comments/formatting ignored). Syntax error → False.

### TS imports (in `onboard/sssf.py`)
`_ts_closure(entry: str, files: Mapping[str, bytes]) -> tuple[list[str], str | None]`: BFS over the entry `.ts` file; regex over the text for `from\s+["'](\.{1,2}/[^"']+)["']`, `import\s+["'](\.{1,2}/[^"']+)["']`, `import\(\s*["'](\.{1,2}/[^"']+)["']\s*\)`; resolve with `posixpath.normpath(posixpath.join(dirname, spec))`, try as is, then `+ ".ts"`, then `/index.ts`. A target outside the entry's directory or missing in base → error text (the extension becomes `manual`). Returns the paths (entry first, then sorted).

## 3. The converter `onboard/sssf.py` (new)

```python
@dataclass
class SssfConversion:
    extraction: Extraction
    settings: ProjectSettings
    roster: list[dict[str, Any]]      # the agents.yaml entries (for harness warnings)
    workflows: list[str]              # workflow files planned into .factory/workflows/
    source_paths: list[str]           # base paths the converter read (for source_not_committed)

def extract_sssf(root, base, base_sha, source: _Source, environ, *, detected: Detected,
                 keep_local=set(), names={}, workflows=False, sssf_leftover=False,
                 rosters: tuple[str, ...]) -> SssfConversion
```
Reads base only: `tree_files(root, base_sha, ["adws/", ".claude/skills/sssf/", "justfile", ".env", ".env.sample"])` and `read_blobs` for the files it needs (roster, prompt files named by the roster, `harness_engineering/*.ts` reached from the roster, `adw_modules/quality.py`). Symlinks/submodules (mode not 100644/100755) are not read (`manual` row when such a path is one it needs).

Errors: roster `adws/adw_sssf_config/sssf.config.yaml` missing in base, not YAML, not a mapping, or `agents` not a list of mappings with `name` → raise `LibraryStoreError("sssf_roster_invalid", "<path>: <problem>; only this roster is converted")`. `plan_onboard` turns it into a short plan blocker (see §4). Every other roster in `rosters` → report `not_converted` row (subject the path, "only adws/adw_sssf_config/sssf.config.yaml is converted") and warning `alternate_rosters: …`.

`_check_options`: slots = the agent names of the roster; `--keep-local`/`--name` for `workflow/…` or unknown agents → `invalid_value` (reuse `extract._check_options` with a small adapter or copy its rules).

Library heads: generalise `extract._library_heads(source, types=EXTRACT_TYPES)` and call it with `("agent", "workflow", "extension")`. Share `planned`/`by_version` naming state with O2 (`_new_name`, `_link`) — same D30 rules, same `name_taken`.

### 3.1 Settings → `.factory/config.yaml`
- `remote = detected.remote or "origin"`; `provider = detected.provider`; `azure = detected.info.azure` when provider is azure; `base` = the base the plan reads (§4).
- `protected_files = [".factory/", *defaults.protected_files]` (order kept, duplicates dropped; non-list or non-str entries → `manual` row, ignored).
- From `quality.py` (§3.6): `test_command`, `test_timeout`.
- Build with `ProjectSettings.model_validate({...})` (`invalid_value` on failure, like `install.project_settings`).
- Render like `install.render_files` (reuse its `_yaml`): header `# factory project settings, converted by factory onboard from sssf (adws/) in <base>@<sha12>\n`, keys in order `base`, `remote` (only when the repo has a remote), `git_provider`, `azure`, `backlog_dir`, `specs_dir`, `docs_dir`, `test_command` (list), `test_timeout`, `protected_files`.
- Report: `converted .factory/config.yaml` "base <b>, remote <r>, provider <p> detected; protected_files .factory/ plus the sssf defaults.protected_files".

### 3.2 Bindings → `.factory/agents.yaml`
Effective sssf entry = roster `defaults` inherited keys (`coding_agent`, `model`, `thinking`, `color`, `tools`, `writes`, `disallowed_commands`, `harness_engineering`) overlaid by the agent. Per agent write a flat entry (no `defaults:` block), key order `name`, `purpose`, `harness`, `model`, `thinking`, `tools`, `writes`, `color`, `harness_engineering`, `disallowed_commands` (only keys that are set):
- `harness = harness.canonical(coding_agent or "pi")` (sssf's engine default is pi). Unknown → `manual` row for the agent, agent dropped from the conversion.
- `thinking`: `auto` → `medium` + row `changed_meaning agent/<slot>/thinking` ("sssf auto: claude ran on medium, pi got auto; HAIFA uses medium"). A value outside `THINKING_LEVELS` → dropped + `manual` row. Others copied.
- `model`, `tools`, `color`, `writes`, `disallowed_commands` copied. `writes` containing `**/*.md` → row `changed_meaning agent/<slot>/writes` ("writes **/*.md lets the agent edit every markdown file, also protected ones such as .factory/prompts/").
- `harness_engineering` entries → extensions (§3.4); binding `harness_engineering: [".factory/extensions/<name>/<name>.ts", …]`. On a non-pi agent the binding is dropped with row `not_converted agent/<slot>/harness_engineering` ("pi extensions are pi's").
- `purpose` = the purpose of the item content chosen in §3.3.
- File header: `# agents of this repo, converted by factory onboard from the sssf roster adws/adw_sssf_config/sssf.config.yaml (<base>@<sha12>)\n`, then `{"agents": [...]}` via `_yaml`.
- Report: `converted .factory/agents.yaml` "bindings of N agents from adws/adw_sssf_config/sssf.config.yaml: coding_agent → harness (claude_code → claude), model, thinking, tools, color, writes; pi model ids are checked by factory check against this machine's catalogue".
- `defaults.data_dir` and top-level `observability` (when present) → rows `not_converted adws/adw_sssf_config/sssf.config.yaml:data_dir` / `:observability` ("runtime data and the tracer live in .factory/ and factory obs").

### 3.3 Agent content (per roster agent, roster order)
Let `slot = name`, `S = stock().agents.get(slot)`, `L = library head agent slot` (`source.load("agent", [slot])`, `unknown_item`/`invalid_item` → None). Repo texts `sys_r`, `usr_r` from the roster's `prompt_engineering.system/user` paths in base (missing → `manual` row "prompt <path> missing", agent dropped).
- **Stock template and L exist**:
  - `m = merge_prompt(S.system, sys_r, L.system)`; system = `m.text`. Rows: `union` → `carried_over agent/<slot>/system.md` ("the changes to stock sssf system.md were insertions next to the library's; both kept (git merge-file --union)"); `conflict` → `manual agent/<slot>/system.md` ("the change conflicts with the library text; the library text is used, port the change by hand") with `detail = m.quote`; `clean` noted in the item row message.
  - user = `L.user`; `usr_r != S.user` → `manual agent/<slot>/user.md` ("sssf names outputs by adw_id and HAIFA returns them (R25); the library text is used") with `detail = quote_change(S.user, usr_r)`.
  - purpose = `L.purpose` when the roster purpose equals `S.purpose` (or is empty), else the roster purpose (mention in item row).
- **No stock template, or L missing**: system/user/purpose from the repo unchanged; row `manual agent/<slot>` ("no stock sssf template: the prompts are taken over unchanged; check them by hand").
- Version `V = agent_version(purpose, system, user)`; then exactly O2's decision: `_link` (history of the same name or head of another item) → `linked`; same version planned earlier this run → `linked`; `--keep-local agent/<slot>` → entry `(slot, head)`, `carried_over`; else `_new_name` → `SeedItem("agent", name, V, files)` with files `agents/<name>/agent.yaml` (`purpose` + `defaults` built from the converted bindings: harness, model, thinking, tools, writes un-expanded with `adopt._unexpand`, color, `extensions` names; validate with `AgentDefaults`, drop `defaults` on `ValidationError`), `system.md`, `user.md`; row `converted` ("new library item <name>; system.md merged cleanly" etc.).
- Repo files `.factory/prompts/<slot>/system.md`, `user.md` = the chosen content. Entry `entries["agent"][slot]`.

### 3.4 Extensions (`harness_engineering`)
Entry points = every distinct path named in the effective `harness_engineering` of any agent (roster order). For each: `name = Path(path).stem`; `check_name(name)` false or `_ts_closure` error → `manual extension/<name or path>` row, the binding is dropped from the agents that named it. Files = closure, item-relative to the entry's directory (`subagents.ts`, `themeMap.ts`), executable bit from the tree mode. `V = tree_version(files)`; link/new item like agents (`SeedItem("extension", name, V, NewFile("extensions/<name>/<rel>"…))`); repo files `.factory/extensions/<name>/<rel>`; entry `entries["extension"][name]`; row `linked` or `converted` ("…; imports themeMap.ts"). Every other `.ts` under `adws/adw_data/harness_engineering/` that no entry reaches → `not_converted <path>` ("no agent loads it").

### 3.5 Chains and workflows
For every base file `adws/adw_*.py` (top level of `adws/`), sorted:
- blob in `stock.chains` → workflow `W`. `W == "simple-sdlc"` or `workflows` flag → planned (below); else row `not_converted <path>` ("stock chain; the library workflow W replaces it: factory onboard --workflows or later factory config add workflow W").
- file name in `stock.chain_files`, other blob → `manual <path>` ("differs from stock sssf; the library workflow W is the stock version, port the change by hand").
- file in `stock.scripts` with the stock blob → `not_converted <path>` ("no HAIFA workflow"); with another blob, or an unknown `adw_*.py` → `manual <path>`.
- every file under `adws/adw_recipes/` except `README.md` → `not_converted <path>` ("recipes are not converted").

Planned workflows: `simple-sdlc` always (first), then the `--workflows` ones sorted. For each: `source.load("workflow", [W])` → file `.factory/workflows/W.yaml` = library bytes, entry `(W, version)`, row `linked workflow/W` ("added from the library"). `unknown_item` → `manual` row + warning `unknown_workflow: …` (as O2). Agents of each added workflow (`install._workflow_agents(item)`) missing in the converted roster → load from the library, roster entry `library.agent.roster_entry(item, settings)`, prompts from the item, entry `(agent, version)`, row `linked agent/<a>` ("added from the library; workflow W needs it"); missing in the library → `manual` row (validation then reports `invalid_plan`).

### 3.6 `adws/adw_modules/`
- `quality.py`: `parse_quality(text)`. Block `test`: literal argv → `test_command`, timeout → `test_timeout`; row `converted adws/adw_modules/quality.py:test` ("test_command [just, test], test_timeout 1800"). Placeholder → nothing set, row `not_converted …:test` ("placeholder; set test_command in .factory/config.yaml"). Non-literal → `manual`. Blocks `lint`, `typecheck`, `build` (any other name too) → `not_converted adws/adw_modules/quality.py:<name>` with the argv (or "placeholder") in the message. `same_as_stock(text, stock.quality_source)` false → `manual adws/adw_modules/quality.py` ("changes beyond the QualityCheckSpec literals are engine code (EX7)").
- every other file under `adws/adw_modules/` whose blob differs from `stock.modules` or is not in it → `manual <path>` ("differs from stock sssf; engine code, not converted (EX7)"). Deleted stock files: ignored.

### 3.7 `left_in_place`
One row each, when present in base: `adws/` ("stays unchanged; delete it in a separate commit"), `.claude/skills/sssf/`, `justfile`, `.env`, `.env.sample`.

### 3.8 Report order and `ReportRow.detail`
Order: agents (roster order, item row then its sub-rows; then library-added agents), extensions (entry order), `.factory/agents.yaml`, workflows (simple-sdlc, then sorted), chains/recipes (path order), `.factory/config.yaml`, `quality.py` rows, roster leftovers (`data_dir`, `observability`, alternate rosters), `adw_modules` manual rows, `left_in_place`.

Add `detail: str | None = None` to `ReportRow` (in `to_json`). `report_text` prints a detail indented by 4 spaces under its row; the CLI text output too.

`source_paths` = every base path under `adws/adw_sssf_config/`, the prompt files read, `adws/adw_data/harness_engineering/`, `adws/adw_modules/`, `adws/adw_*.py`, `adws/adw_recipes/`.

## 4. `onboard/onboard.py` changes

- `_state_blocker`: drop the `sssf` branch (`sssf_not_supported` disappears everywhere: `onboard.py` docstring, `skill/codes.py`, `cli.py` description, `skill.md`, tests).
- Base for repos without a factory config: `rs = repo_state(root)`; when `rs.state in ("sssf", "none")` and `.factory/config.yaml` is not a file in the working tree, `detected = detect(root)`; if `detected.base` and it differs from `rs.base`, `alt = repo_state(root, detected.base)`; use `alt` when `alt.state == "sssf"`. Keep `detected` for §3.1.
- New parameter `workflows: bool = False` on `plan_onboard` / `run_onboard`; on a `pre_library` repo → `LibraryStoreError("conflicting_options", "--workflows is only for sssf repos")`.
- Split the body: after the state blocker, `pre_library` keeps today's code (`_plan_pre_library`), `sssf` goes to `_plan_sssf`. Factor the shared tail (library blockers, remote check, M7 blockers, manifest, `.gitignore`, `plan_contents`, `_check_invariant`, `dirty_paths`, validation, library plan, digest) into one helper so both paths use it unchanged.
- `_plan_sssf`:
  1. `base_sha = rs.commit`. Library source / `library_missing` short plan as today.
  2. `extract_sssf(...)`; `LibraryStoreError("sssf_roster_invalid")` → `_short_plan(root, rs, target, Blocker("sssf_roster_invalid", msg, fix="fix adws/adw_sssf_config/sssf.config.yaml and commit it"))`. `invalid_value`, `conflicting_options`, `unknown_item`, `name_taken` propagate as in O2.
  3. `source_not_committed`: compare each path of `conversion.source_paths` with the working tree (bytes, executable bit, missing) and list untracked files on disk in the same directories (skip `__pycache__/` and `*.pyc`), no `git status` (no index refresh). Blocker as O2 with the sorted list.
  4. Remote check, library and M7 blockers with `settings = conversion.settings`.
  5. Manifest `Onboarding(source="sssf", source_commit=base_sha, …)`, `ManifestItems(agents=…, workflows=…, extensions=…)`; contents = `extraction.files` + manifest. Same `.gitignore`/exclude handling. `_check_invariant` must hold (all `.factory/` creates + `.gitignore` append).
  6. Validation: `install_commit._validate(root, base, base_sha, contents, conversion.workflows, _missing_harnesses())`. Harness warnings from `conversion.roster` (existing `_harness_warnings`).
  7. `OnboardPlan.settings = conversion.settings`; add `source: "sssf" | "pre_library"` to `OnboardPlan` and to `to_json`.
- O2 path: `ManifestItems` also passes `extensions` (empty there); `Extraction.entries` default gains `"extension": {}`.
- Commit subject: `f"factory: onboard {root.name} ({plan.source}) with the library {name}"`.
- Module docstring: the sssf conversion (AR32) and the new blocker list.

`onboard/__init__.py`: export `extract_sssf`, `SssfConversion`, `merge_prompt`, `MergeResult`, `parse_quality`; update the docstring. `onboard/extract.py` docstring: "The sssf extractor (`onboard/sssf.py`) fills the same Extraction."

## 5. CLI, skill, codes

- `cli.py` `_add_onboard_command`: add `--workflows` (`store_true`, "sssf: also add the library workflows of every other recognised stock chain"); pass to `run_onboard`. Rewrite the description: pre_library and sssf; the AR32 conversion in short (roster bindings, prompts by merge with the stock sssf text, user.md from the library, extensions from harness_engineering, stock chains by blob id → workflows, simple-sdlc always, quality.py → test_command/test_timeout, adws/ stays byte for byte); report codes; blockers without `sssf_not_supported`, plus `sssf_roster_invalid`. Text output prints `detail` lines.
- `skill/codes.py`: remove `sssf_not_supported`; add `("sssf_roster_invalid", "2", "factory onboard: adws/adw_sssf_config/sssf.config.yaml is missing or not a valid roster; fix it and commit")`; `ISSUE_CODES["onboard"]` add `"alternate_rosters"`.
- `skill/skill.md` § Onboarding and adopt: replace the "sssf repos are sssf_not_supported" sentence; add a numbered sssf procedure (check → `factory onboard --dry-run --json [--workflows]` → show `data.report` incl. `detail`, files, library plan, digest → `--commit --expect`), and a table/list of what is extracted from sssf and with which code (the AR32 table in short, incl. `changed_meaning` for `thinking: auto` and `writes: **/*.md`, `not_converted` for `data_dir`, `observability`, lint/typecheck/build, recipes, other chains; `manual` for modified chains, user.md, conflicting system.md, `adw_modules` changes, agents without a stock template; `left_in_place` for `adws/`, `.claude/skills/sssf`, justfile, `.env`). Every code in `ERROR_CODES` and `ISSUE_CODES` must appear in backticks (`tests/test_skill.py`).
- `config/settings.py`: no change expected (reuse `split_command`, `check_timeout`). `justfile`: no change.

## 6. Tests (pytest, no model, no network)

Determinism: in every sssf test monkeypatch `aifactory.library.config_edit._missing_harnesses` to return `frozenset({"pi", "codex"})` so preflight never asks a real pi for its catalogue (`harness_missing` warnings then appear for pi agents — assert or ignore them).

### Helpers in `tests/onboard/onboard_repo.py`
- `sssf_repo(tmp, name, *, origin: bool)`: `init_repo(tmp/name)`, `git config user.name/email`, `stamp_sssf`, `.env.sample` from `SSSF_TEMPLATES/env.sample`, optional `bare_origin`, commit. Folder names: `omnibus`, `jsst`, `amber-swiss-clock` (they give the slugs).
- `patch_omnibus(repo)`: roster with every agent `coding_agent: claude_code`, `model: opus`, no `harness_engineering`, no `subagent_*` tools; `defaults.thinking: auto` (scout and documenter inherit it); `quality.py` test block `timeout_seconds=1800`, lint `argv=["just", "lint"]` (textual replace of the stock lines).
- `patch_jsst(repo)`: builder `system.md` gets rule lines appended at the end (insertion next to the seed's appended lines → union); reviewer `system.md` gets a rule inserted where it merges cleanly with the seed (e.g. after the "Break the spec…" line; verify with `merge_prompt`). pi roster unchanged.
- `patch_amber(repo)`: builder `system.md` gets a rule inserted near the top (after `## Instructions`), clean merge.
- `patch_modified_chain(repo)`: one changed line in `adws/adw_plan.py`, an extra recipe `adws/adw_recipes/demo.json`, an extra agent `tester` (prompts under `adws/adw_data/prompt_engineering/tester/`) in the roster, planner `system.md` changing the line the seed changes (real conflict → `manual` with detail), planner `user.md` edited (`manual`), one changed line in `adws/adw_modules/utils.py`, and a second roster `adws/adw_sssf_config/alt.yaml`.
Tell-tale: when choosing patch positions, assert in a unit test that `merge_prompt` gives exactly `union` / `clean` / `conflict` for them, so the fixtures cannot drift silently.

### `tests/onboard/test_sssf_parts.py` (unit, fast)
- `stock()` equals vendor: every prompt byte-equal to `vendor/sssf/templates/prompt_engineering/…`, `quality.py.txt` equals vendor, every blob id in `stock.yaml` equals `git hash-object` of the vendor file (chains, scripts, modules, prompts), purposes equal the vendor roster; `3f5d4837…` and `a6a5c4c1…` both map to `simple-sdlc`.
- `merge_prompt`: stock, same, clean, union (insert-only conflict), conflict (same line changed; text = theirs, quote contains the repo line).
- `parse_quality`: stock source → test `("just","test")`/600, lint placeholder; 1800 + `just lint`; non-literal argv → `literal=False`; `same_as_stock` true for literal-only edits, false for an added statement.
- `_ts_closure`: `subagents.ts` → `[subagents.ts, themeMap.ts]`; import outside the dir → error.

### `tests/onboard/test_sssf.py` (integration; reuse `identity`, `library_remote` from `test_onboard.py` — move them to a `conftest.py` in `tests/onboard/` or duplicate)
Golden reports: `tests/onboard/golden/sssf_<case>.txt`, one line per report row `"<code> <subject> <item or ->"` (no versions/messages, so a seed change does not churn them). Compare exactly; assert key message substrings separately.
1. **Omnibus** (origin, seed library): `--dry-run` → no blockers, `validation.ok`; 5 agents `linked` to the same names; `library_plan` is None; `changed_meaning` for `agent/scout/thinking`, `agent/documenter/thinking`, `agent/documenter/writes`; `converted adws/adw_modules/quality.py:test`; `not_converted` lint (message contains `just lint`), typecheck, build, `data_dir`, `observability`; `linked workflow/simple-sdlc`; stock chains `not_converted`; `left_in_place adws/`, `justfile`, `.env.sample`. Planned `config.yaml` parses with `test_command == ("just","test")`, `test_timeout == 1800`, `protected_files` starts with `.factory/` then the three sssf entries, `base: main`, `git_provider: local`. `agents.yaml` header names `adws/adw_sssf_config/sssf.config.yaml`; every agent `harness: claude`, `thinking` of scout/documenter `medium`. Then `--commit --expect` → committed and pushed; manifest `onboarding.source == "sssf"`, `source_commit` = old base; `load_config(CommitSource(repo, "main", new))` succeeds and `install_commit.validate_source(…, {"simple-sdlc": …})` is `[]`; `git rev-parse old:adws == new:adws`, `git diff --name-status old new` only `A .factory/…` and `A|M .gitignore`; working tree `adws/` bytes unchanged (snapshot before/after); second `--dry-run` → blockers `["already_onboarded"]`, `--commit` → exit 2 `already_onboarded`.
2. **JSST** (no remote, seed library): warning `no_remote`; `converted agent/builder -> builder-jsst` with `carried_over agent/builder/system.md` (union: the planned prompt contains both the seed's lines and the inserted rules); `converted agent/reviewer -> reviewer-jsst` (clean merge); planner/scout/documenter `linked`; `converted extension/subagents` (library files `extensions/subagents/subagents.ts` and `themeMap.ts`); `agents.yaml` planner and scout have `harness: pi` and `harness_engineering: [.factory/extensions/subagents/subagents.ts]`, builder/reviewer `harness: claude`; `.factory/extensions/subagents/{subagents.ts,themeMap.ts}` planned; library items `builder-jsst` and `reviewer-jsst` have `defaults.harness == "claude"`. (A new library agent item of a pi agent with an extension carries `defaults.extensions == ["subagents"]`; cover that in test 4 with the `tester` agent bound to `subagents.ts`.) `--commit` → library commit pushed to the library remote first, repo commit local only (base advanced, not pushed); manifest `items.extensions.subagents.item == "subagents"`.
3. **amber** (origin): after the JSST onboarding of test 2 on the same machine (same library), amber `--dry-run` → `linked extension/subagents`, `converted agent/builder -> builder-amber-swiss-clock` (clean merge), others `linked`; commit succeeds.
4. **Modified chain** (origin): `manual adws/adw_plan.py`, `not_converted adws/adw_recipes/demo.json`, `manual agent/tester` + `converted agent/tester -> tester`, `manual agent/planner/system.md` with `detail` quoting the changed line and the planned `system.md` == library text, `manual agent/planner/user.md`, `manual adws/adw_modules/utils.py`, `not_converted adws/adw_sssf_config/alt.yaml` + warning `alternate_rosters`. With `--workflows` the stock chains `plan-build`, `plan-build-test`, `document`, `scout` become `linked workflow/…` with `.factory/workflows/*.yaml`; `plan` is not added because `adw_plan.py` is modified (it stays `manual`).
5. **Blockers**: roster missing (only `alt.yaml`) → `sssf_roster_invalid`; uncommitted edit in `adws/adw_data/prompt_engineering/builder/system.md` → `source_not_committed`; `--workflows` on the HAIFA copy (pre_library) → `conflicting_options`; base detection: an sssf repo on branch `master` (no `main`) is planned with `base: master`.
6. Update `test_onboard.py::test_state_blockers`: the stamped sssf repo now has no `sssf_not_supported` blocker (assert the report is non-empty and no blocker other than possibly `no_remote`-related warnings).

Mark nothing slow unless a test takes > 2 s; if you must, add the file to `SLOW_FILES` in `tests/tiers.py`.

## 7. Verification

```bash
just test tests/onboard tests/test_skill.py      # focused
just test                                         # whole suite
just typecheck
just lint
```
Manually (no commit): copy `vendor/sssf/templates` into a temp repo with `stamp_sssf`-like steps and run `uv run --project aifactory factory onboard --repo <tmp> --dry-run` with a temp `HAIFA_HOME` after `factory library init`; the temp repo's working tree must stay unchanged. Never run `factory onboard --commit` against this repo or its main checkout.

## 8. Out of scope
Backlog conversion (F6), workflows of type `script`, recipe conversion, deleting `adws/`, dashboard/API, `factory check` changes, an `extensions:` key in `agents.yaml` read by the run.
