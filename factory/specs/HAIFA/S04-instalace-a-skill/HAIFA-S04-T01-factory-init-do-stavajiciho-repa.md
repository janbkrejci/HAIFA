# HAIFA-S04-T01: `factory init` into an existing repo from the library

## Goal

New command `factory init` writes a working `.factory/` into a git repo that has no factory yet. Items (agents, workflows) come from the library in the home directory (`$HAIFA_HOME/library`, `HAIFA_LIBRARY` overrides) or, when there is no library, from the seed in the package. `.factory/manifest.yaml` records the origin and version of every item. Nothing is committed, nothing is written to the library or `$HAIFA_HOME`.

## Decisions

- D1 "Installed" means the manifest is committed. `already_installed` fires when `.factory/manifest.yaml` exists in the commit of `HEAD` or of the resolved base branch (`git cat-file -e <ref>:.factory/manifest.yaml`; skip refs that do not resolve, e.g. an unborn branch). A manifest only in the working tree is an earlier uncommitted `init`: the run continues and existing files are skipped (or overwritten with `--force`). This is the only reading that satisfies both "refuse a repo with a manifest" and "a second run skips everything" from the task. `--force` never bypasses `already_installed` or `existing_config`.
- D2 `existing_config`: no `.factory/manifest.yaml` in the working tree, and at least one of `.factory/config.yaml`, `.factory/agents.yaml` (working tree) or the directory `adws/adw_sssf_config/` exists. Message advises `factory onboard`. Check D1 first, then D2.
- D3 Library or seed: the library is used when `library_root()/.git` exists and `HEAD` resolves (same rule as `library.state.library_side`). Otherwise the seed. Never mix: an item missing in the library is `unknown_item`, not a seed fallback.
- D4 `--bind AGENT=HARNESS[:MODEL[:THINKING]]` sets the harness (canonicalised with `aifactory.harness.canonical`). MODEL and THINKING given in the bind replace the item defaults. When the bind changes the harness and omits MODEL or THINKING, that key is dropped from the entry (the default model of another harness is meaningless). When the harness is unchanged, omitted keys keep the item defaults. Empty MODEL/THINKING parts (`codex::high`) mean "omitted".
- D5 Add `--repo PATH` (default: cwd), like every other repo command. Tests need it, and `test_every_command_is_in_skill` already covers options automatically.
- D6 The backlog directory gets an empty `<backlog_dir>/.gitkeep` so it survives the commit (git does not track empty directories). Verify the backlog loader ignores non-`.md` files (it must, `factory backlog check` has to pass); if it does not, report it instead of changing the loader.
- D7 Errors reuse `LibraryStoreError(code, message, issues=..., data=...)` from `library/store.py`. It is already in `ERROR_CLASSES` of `tests/test_skill.py` and handled by `cli._library_fail` (exit 2).
- D8 `config.yaml` gets no `test_command` (detecting it is out of scope). Runs fall back to `just test` or the task's own `test`.

## Files

1. `aifactory/src/aifactory/library/install.py` (new): all logic.
2. `aifactory/src/aifactory/library/remote.py`: add a public `remote_url(root: Path) -> str | None` that returns `_remote(root)` (redacted `origin` URL). Use it from `install.py`.
3. `aifactory/src/aifactory/cli.py`: subcommand `init`.
4. `aifactory/src/aifactory/skill/codes.py`: codes `already_installed`, `existing_config`.
5. `aifactory/src/aifactory/skill/skill.md`: fix the one sentence in "### Check" item 2 that says `init` is not a CLI command (now: `init` is `factory init`, `update` is still a dashboard name). No new procedure section (that is HAIFA-S04-T02).
6. `aifactory/tests/library/test_library_install.py` (new): tests.

`aifactory/src/aifactory/config/settings.py` and `loader.py` need no change unless the builder finds a real need. Do not touch `.factory/`, `vendor/`, `prototype/`, `justfile` (no recipe needed).

## `library/install.py`

Public API:

```python
GITIGNORE_LINES = (".factory/data/", ".factory/worktrees/", ".factory/local.yaml", ".factory/trace.db*")
DEFAULT_AGENTS = ("planner", "builder", "reviewer", "documenter")
DEFAULT_WORKFLOWS = ("simple-sdlc",)
SSSF_CONFIG_DIR = "adws/adw_sssf_config"

@dataclass(frozen=True)
class Binding:  # parsed --bind
    agent: str
    harness: str
    model: str | None
    thinking: str | None

def parse_binding(text: str) -> Binding  # LibraryStoreError("invalid_value") on bad form, harness or thinking level

def init_repo(
    path: Path,
    *,
    base: str | None = None,
    provider: Literal["local", "github"] = "local",
    agents: Sequence[str] | None = None,       # None -> DEFAULT_AGENTS
    bindings: Sequence[Binding] = (),
    workflows: Sequence[str] | None = None,    # None -> DEFAULT_WORKFLOWS
    force: bool = False,
    environ: Mapping[str, str] | None = None,
) -> InitResult
```

`InitResult.to_json()` returns:

```
repo, base, provider,
source: "library" | "seed",
library: {id, name, remote} | null,
agents: [names in roster order], workflows: [names],
added_agents: [agents added because a workflow needs them],
files: [{path, action: "created" | "skipped" | "overwritten"}],
gitignore: {path: ".gitignore", added: [lines]},
manifest: <manifest.to_json()>
```

and `warnings`: one entry `"<n> existing file(s) skipped; use --force to overwrite"` when any file was skipped.

Steps of `init_repo`, in this order; steps 1 to 6 write nothing:

1. Repo root: `git rev-parse --show-toplevel` from `path`; failure -> `LibraryStoreError("not_a_repository", ...)`. Use `aifactory.config.source.repo_root` and map its `ConfigError`, or call git directly.
2. Base: `base` or the current branch (`git symbolic-ref --quiet --short HEAD`). Detached HEAD without `--base` -> `invalid_value` ("HEAD is detached; pass --base").
3. Refusals D1 and D2 (`already_installed` with `data={"fix": "factory update"}`, `existing_config` with `data={"fix": "factory onboard", "found": [paths]}`).
4. Validate names: every agent and workflow name with `library.model.check_name`, duplicates removed keeping order; bad name -> `invalid_value`.
5. Load items (D3):
   - Library: `root = store.library_root(environ)`, `head = git.rev_parse(root, "HEAD")`, `meta = store.read_meta(root, head)`, items via `tree.read_items(root, head, keys)`. Missing item (empty files) -> `unknown_item`. Item `None` or issues -> `invalid_item` with `issues=[...]`. `LibraryRef(id=str(meta["id"]), name=str(meta["name"]), remote=remote_url(root))`; missing `id`/`name` -> `invalid_library` (already a known code; check `codes.py`, otherwise use `invalid_item`).
   - Seed: agents `load_library_item(SEED_DIR, "agent", name)`, workflows `load_library_item(SEED_WORKFLOWS_ROOT, "workflow", name)`; missing -> `unknown_item` (check existence with `seed_agent_names()` / `seed_workflow_names()` first), `LibraryError` -> `invalid_item`. Library ref `None`.
   - Load workflows first. For each workflow parse its YAML (`yaml.safe_load` of the file bytes) with `workflow.parse.parse_workflow(raw, load_roles())`, walk `workflow.model.walk(wf.steps)`, and for every `RoleStep` take `step.role.agent`. Append agents missing from the requested list in workflow order (record them in `added_agents`). Then load all agents.
6. Bindings: each `Binding.agent` must be in the final agent list, else `invalid_value`. Duplicate bind for one agent: last wins.
7. Build the content (all as bytes/str in memory):
   - `settings = ProjectSettings(base=base, git_provider=provider)` (defaults give `backlog_dir`, `specs_dir`, `docs_dir`).
   - `.factory/config.yaml`: a short comment header, then `yaml.safe_dump` of `{base, git_provider, backlog_dir, specs_dir, docs_dir}` with `sort_keys=False`.
   - `.factory/agents.yaml`: comment header, then `{"agents": [entry, ...]}` where `entry = library.agent.roster_entry(item, settings)` (purpose, harness/model/thinking/tools/writes/color from `defaults`, `$specs_dir/`/`$docs_dir/` expanded) with the binding applied (D4). Key order: name, purpose, harness, model, thinking, then the rest. No top-level `defaults:` block.
   - `.factory/prompts/<agent>/system.md` and `user.md`: the exact bytes of the item files (`item.file("system.md").data`).
   - `.factory/workflows/<name>.yaml`: the exact bytes of the workflow item file. Byte equality is what makes `factory config items` report `synced`.
   - `.factory/manifest.yaml` via `config.manifest.dump_manifest(Manifest(...))`: `written_by=__version__`, `library` as above, `onboarding=Onboarding(source="init", source_commit=<HEAD sha or None>, at=<UTC ISO 8601 with Z, seconds precision>, by=<git config user.name or None>, factory=__version__, library_commit=<library head or None>)`, `items=ManifestItems(agents={slot: ManifestEntry(item=name, version=item.version)}, workflows={...})`. Slot = item name.
   - `<backlog_dir>/.gitkeep`: empty (D6).
8. Write: for every file above, if the path exists and not `force` -> action `skipped`; exists and `force` -> `overwritten`; else `created`. Create parent dirs. Text files UTF-8, `\n` line ends.
9. `.gitignore` at the repo root: read it (missing = empty), add each line of `GITIGNORE_LINES` not already present as a stripped line, keep existing content, add a newline before the appended block when the file does not end with one. Never removes or duplicates lines; not affected by `--force`. Report `added`.
10. No git command that writes (no `add`, no `commit`). No write under `library_root()` or `haifa_home()`. Do not call `library.history` (it writes a cache under `$HAIFA_HOME`) and do not call `store.write_lock` (it creates `$HAIFA_HOME/library.lock`).

## CLI (`cli.py`)

- `SUBCOMMANDS`: add `("init", "install factory into this repository from the library (or the seed)")`.
- `_add_init_command(parser)`: description summarising what is written, the refusals and that nothing is committed. Options: `--repo PATH`, `--base BRANCH`, `--provider {local,github}` (default `local`), `--agents LIST` (comma separated), `--bind AGENT=HARNESS[:MODEL[:THINKING]]` (`action="append"`, default `[]`), `--workflows LIST` (comma separated), `--force`, `--json`. Help texts state the defaults.
- `_init(args)`: split comma lists (strip, drop empties), parse bindings, call `init_repo`, catch `LibraryStoreError` and `ProviderError` -> `_library_fail(exc, args.json, "factory init")`. JSON: `_emit_ok(result.to_json(), result.warnings)`. Text: one line per file `"{action:<11} {path}"`, the `.gitignore` additions, the source (`library <name>` or `seed`), then `next: review, commit .factory/ <backlog_dir>/ .gitignore to <base>`.
- `_dispatch`: `if command == "init": return _init(args)`.

## `skill/codes.py`

Add with exit `"2"`:
- `already_installed`: "factory init: .factory/manifest.yaml is committed; the repo is installed, run factory update"
- `existing_config`: "factory init: the repo has factory configuration without a manifest (.factory/ or adws/adw_sssf_config/); run factory onboard"

Any other new code literal raised in `install.py` must be registered too (`test_error_codes_complete` scans for them).

## Tests: `aifactory/tests/library/test_library_install.py`

Fixtures: `HAIFA_HOME` is already a temp dir per test (conftest). Set `HAIFA_LIBRARY` unset/empty via monkeypatch so the library is `$HAIFA_HOME/library`. Temp repo: `git init -b main`, user name/email, `commit.gpgsign=false`, one commit with `README.md`. Call `cli.main([... "--json"])` through `cli_json.run_json` (envelope rules checked) for most cases; call `init_repo` directly where simpler. Library: create with `store.init_library("team")` (needs git identity: set `GIT_AUTHOR_NAME/EMAIL`, `GIT_COMMITTER_NAME/EMAIL` via monkeypatch), modify `agents/builder/system.md` in the library working tree and commit it with git.

Helper `snapshot(home)`: sorted list of (relative path, bytes) under `$HAIFA_HOME`; assert unchanged around every `init` call that uses a library.

Cases (one test each):

1. Seed without library: defaults. Assert files exist: config.yaml (`base: main`, `git_provider: local`), agents.yaml with planner, builder, reviewer, documenter in that order (planner `writes: [specs/]`, documenter `writes: [app_docs/]`), 8 prompt files, `workflows/simple-sdlc.yaml` byte-equal to `DEFAULT_WORKFLOWS_DIR / "simple-sdlc.yaml"`, `backlog/.gitkeep`, manifest with `format: 1`, `written_by == __version__`, `library: None`, `onboarding.source == "init"`, items versions equal to `seed_items()` versions. `data.source == "seed"`. `git status --porcelain` shows only untracked files (no commit happened: `git rev-list --count HEAD == 1`). No prompt contains `haifa-validate`.
2. Library with modified builder: manifest `items.agents.builder.version` equals the modified library version (≠ seed version), `library.id`/`name` equal `library.yaml`, `onboarding.library_commit` equals library HEAD, written `builder/system.md` equals the modified bytes. Add an `origin` remote `https://user:secret@example.com/lib.git` to the library before init; manifest `library.remote` is `https://example.com/lib.git` (no `secret`, no `user`). `$HAIFA_HOME` snapshot unchanged.
3. `--bind builder=codex:gpt-5.5:high`: builder entry has `harness: codex`, `model: gpt-5.5`, `thinking: high`; other agents keep claude defaults. Plus `--bind builder=nope` -> `invalid_value`, and `--bind scout=claude` without scout in the roster -> `invalid_value`.
4. `--workflows scout` (with default `--agents`): agents.yaml contains `scout`, `data.added_agents == ["scout"]`, prompts for scout exist, `workflows/scout.yaml` exists.
5. Second run skips: run init twice without commit; second run exit 0, every file action `skipped`, a skip warning, files byte-identical to after the first run, `gitignore.added == []`.
6. `--force` overwrites: after the first run change `prompts/builder/system.md` and `config.yaml`; `init --force` -> actions `overwritten`, content restored.
7. `.gitignore` without duplicates: pre-existing `.gitignore` with `node_modules` (no trailing newline) and `.factory/local.yaml`; after init each `GITIGNORE_LINES` entry appears exactly once, `node_modules` kept on its own line; second run adds nothing.
8. `already_installed`: init, commit everything, init again (also with `--force`) -> exit 2, `error.code == "already_installed"`, working tree unchanged (`git status --porcelain` empty).
9. `existing_config`: three parametrised variants (`.factory/config.yaml`, `.factory/agents.yaml`, `adws/adw_sssf_config/sssf.config.yaml`) -> `existing_config`, no other file created, `.gitignore` untouched.
10. Valid result: init (seed), commit all; `factory config show --json`, `factory backlog check --repo` -> exit 0; `factory config items --repo R --json` -> every item `state == "synced"`. Repeat `config items` with the library case (2) to cover the library path.
11. Run with the fake harness: init with defaults, write a backlog (project, step and task `index.md`/task file like `tests/run/run_repo.py` `files()`, task with `workflow: simple-sdlc`, `writes: [src/app/]`, `test: "true"` so no `just` is needed), commit, then `run_task(repo, task_id)` under `fake_env` (import from `tests/run/run_repo.py`; mirror its `sys.path` handling or use `workflow_fakes.install_fake_harnesses`). Script envelopes: planner writes the spec (`script.on` + `ok(changed_files=..., commit_message=...)`), builder writes a file under `src/app/`, reviewer `ok(approved=True, findings=[...])`, documenter writes the doc. Assert the run result is successful (follow the assertions used in `tests/run/test_task_run.py`). If the provider `local` path needs more (merge, base), copy the pattern from `tests/run/test_auto_merge.py`. No model is called (fake harnesses raise if a real one is reached).

If case 11 makes the file slow, keep it in this file but consider whether `tests/tiers.py` `SLOW_FILES` should list it; `tiers.py` is test infrastructure, so only add it if the fast tier would otherwise exceed its usual time.

Also: `tests/test_skill.py` must stay green (new command appears in the rendered skill with all its options, has `--json`, codes registered).

## Verification

Run from the repo root:

1. `just test` (or `uv run pytest aifactory/tests/library/test_library_install.py aifactory/tests/test_skill.py` first for speed).
2. `just typecheck`
3. `just lint`

Manual smoke (optional, in a temp dir with a temp `HAIFA_HOME`): `git init`, commit, `factory init --json`, `git add -A && git commit`, `factory config items --json`.

## Out of scope

Preview and commit to base (M8), test command detection, Azure DevOps, tool installation, onboarding (`factory onboard`), install procedure in the skill (HAIFA-S04-T02), any change to `.factory/` of this repo, `vendor/`, `prototype/`.
