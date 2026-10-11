# `factory task resolve` a workflow `resolve`

Krok 6 sekce „Běh úkolu“ (riziko R2): PR, který nejde mergovat kvůli konfliktu s `base`, se dá příkazem převést na aktuální `base`. Automaticky se nespouští.

## Co se změnilo

**Nový příkaz** `factory task resolve <task-id>` (`cli.py`, podporuje `--json` a `--repo`) volá `review.resolve_task`. Ta ověří otevřený PR (`_checked_pr`), uvolní worktree jeho větve (`_free_branch` – logika vytažená z `return_task`, odmítne špinavý worktree nebo větev v hlavním checkoutu), dožene `base` z remote a spustí `run_task(..., branch=<větev PR>, resolve_onto=<sha base>)`. Neexistující base → chyba `unknown_base`.

**`task approve` při `conflict`** nyní v hlášce doporučí `factory task resolve <task-id>` (`review/flow.py`, `_approve`).

**Workflow** `defaults/workflows/resolve.yaml`: `rebase` → `resolve` (jen `when: rebase.conflict`) → `test`; `accept: test.passed`.

**Registr rolí** (`engine/defaults/roles.yaml`, `engine/role_registry.py`):
- role `resolve` (agent `builder`, `BuildOutput`, gate `diff_matches_claims`, 1 retry),
- code step `rebase` (owner `git`), přidán do `CODE_ACTIONS`; pole výsledku `REBASE_FIELDS`.

**Code step `rebase`** (`workflow/rebase.py`, `rebase_onto`):
1. `onto` už je předek HEAD → nic.
2. `git rebase <onto>` projde → čistý výsledek, historie zůstane, agent se nevolá.
3. Jinak `rebase --abort`, reset na `onto`, `git merge --squash <before>` → všechny konflikty s markery ve stromu najednou; výstup `RebaseOutput(conflict=True, files=[...], squashed=True)`. Squash bez konfliktu se rovnou commitne.
Pomocné `unmerged_files` a `conflict_markers` (hlídá `<<<<<<<`/`>>>>>>>`, ne `=======`). `EngineCodeRunner.rebase` bere cíl z prompt proměnné `rebase_onto`; bez ní chyba odkazující na `factory task resolve` (`workflow/interpreter.py`).

**Běh** (`run/resolve.py`, `run/task.py`):
- `run_task` s `resolve_onto` použije workflow `resolve` (musí obsahovat krok `rebase`, jinak `invalid_workflow`), prompt `resolve_prompt` (sekce `## Resolve`), nevyžaduje `writes` a jako `fork_sha` bere `resolve_onto`.
- `ConflictWriteGuard`: scope zápisu = přesně soubory v konfliktu (zafixováno při prvním snapshotu); bez konfliktu nesmí agent měnit nic.
- `finish_resolve` po workflow: žádné zbylé markery, `git add` konfliktních souborů, žádné unmerged cesty, commit `"<task>: rebase onto <base> <sha>, resolve conflicts in ..."`.
- Při jakékoli chybě (accept nesplněn, markery, porušení scope, přerušení) `restore` udělá `rebase/merge --abort`, `reset --hard <before>`, `clean -fd` a ověří HEAD. Běh je `failed`, PR se nepublikuje.

**Push a PR**: `GitProvider.push` / `git.push` / `LocalProvider.push` mají parametr `lease` → `--force-with-lease=refs/heads/<branch>:<before>`. `publish` ho předá a u existujícího PR zapíše nový `base_sha`.

**Řádek `## Běhy` při approve** (`_done_entry`) uvádí workflow posledního úspěšného běhu, který není `resolve`.

## Soubory

- CLI: `aifactory/src/aifactory/cli.py`
- Workflow/registr: `defaults/workflows/resolve.yaml`, `engine/defaults/roles.yaml`, `engine/role_registry.py`
- Workflow engine: `workflow/rebase.py` (nový), `workflow/interpreter.py`, `workflow/__init__.py`
- Běh: `run/resolve.py` (nový), `run/task.py`, `run/__init__.py`
- Review/providery: `review/flow.py`, `review/publish.py`, `review/__init__.py`, `providers/base.py`, `providers/git.py`, `providers/local.py`
- Testy: `tests/run/test_task_resolve.py` (nový), `tests/workflow/test_rebase.py` (nový), `tests/workflow/test_default_workflows.py`, `tests/engine/test_role_registry.py`, `tests/workflow/workflow_fakes.py` (`FakeCodeRunner.rebase`)
- Plán: `specs/89c73e8f_task-resolve-workflow.md`

## Použití

```bash
factory task approve T02      # exit 2, conflict: "... run `factory task resolve T02` ..."
factory task resolve T02      # nový běh workflow resolve na větvi PR
factory task approve T02      # teď projde
```

Neúspěšný resolve skončí s exit 1 a větev zůstane na původním tipu.

## Ověření

```bash
just test && just typecheck && just lint
```

Klíčové testy (provider `local`, falešný harness, bez modelu):
- `test_task_resolve.py::test_conflict_resolve_then_approve` – dva tasky mění stejný řádek, první se mergne, approve druhého dá `conflict`, `resolve` zavolá builder jednou, pak approve merguje.
- `test_clean_rebase_skips_agent` – bez konfliktu se builder nevolá.
- `test_unresolved_conflict_restores_branch`, `test_red_suite_restores_branch`, `test_clean_rebase_red_suite_restores_branch`, `test_resolver_outside_conflict_is_breach` – větev vrácena do stavu před rebase.
- `test_resolve_force_pushes` – force-with-lease push na remote.
- `test_rebase.py` – chování `rebase_onto`, `conflict_markers`, `EngineCodeRunner.rebase` bez cíle.
