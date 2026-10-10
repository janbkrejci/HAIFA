# Plan: workflow `resolve` a `factory task resolve <task-id>`

Krok 6 „Běh úkolu“ v `docs/product-brief.md` (PR nejde mergovat kvůli konfliktu), riziko R2.
Pracuje se jen v `aifactory/`. `vendor/`, `prototype/` a `docs/product-brief.md` se nemění. Testy nevolají model.

## Shrnutí návrhu

`factory task resolve T` = nový běh (řádek v `task_runs`, workflow `resolve`) na větvi otevřeného PR tasku:

1. `review.flow.resolve_task` zkontroluje PR (otevřený, task neběží), uvolní větev (stejně jako `return_task`: odmítne dirty worktree, odstraní staré worktree větve), dorovná lokální `base` s remote (`_catch_up_base`) a vezme `onto = rev_parse(refs/heads/<base>)`.
2. Zavolá `run_task(..., branch=row.branch, force=True, resolve_onto=onto)`. Běh vytvoří worktree na větvi PR a spustí workflow `resolve`:
   ```yaml
   steps:
     - rebase                      # nový code step: rebase na onto
     - resolve: {when: rebase.conflict}   # nová role, agent builder
     - test
   accept: test.passed
   ```
3. Když rebase projde čistě, `rebase.conflict` je false, takže se agent nevolá. Pak běží test.
4. Při konfliktu smí agent měnit jen soubory s konfliktem (`ConflictWriteGuard`). Po workflow kód ověří, že v nich nezůstaly konfliktní značky, a commitne je (`git add` + `git commit`).
5. Když běh selže (breach, gate, zbylé značky, červený test, accept), větev se vrátí na původní tip (`reset --hard before`, abort rebase/merge, `clean -fd`). Při úspěchu následuje `publish` s **force-with-lease** push, PR se aktualizuje a `task_prs.base_sha` se nastaví na `onto`.

### Proč rebase se squash fallbackem

Workflow běží v jednom průchodu, takže vícenásobné zastavení `git rebase` (jeden konflikt na commit) do něj nejde vložit. Proto:
- nejdřív `git rebase <onto>`. Když projde, historie se zachová a agent se nevolá;
- když skončí konfliktem: `git rebase --abort`, `git reset --hard <onto>` a `git merge --squash <before>`. Změny větve se tak přehrají jako jediný commit na `onto` a všechny konflikty jsou najednou ve stromu se značkami. Agent je vyřeší v jednom kroku a kód je commitne jako jeden commit. Merge strategie je stejně výchozí squash (D9).
- vzácný případ, kdy rebase konfliktuje, ale squash merge projde čistě: `rebase_onto` squash rovnou commitne a vrátí `clean=True` (`squashed=True`), takže se agent nevolá.

## Změny po souborech

### 1. `aifactory/src/aifactory/engine/role_registry.py`
- `CODE_ACTIONS = ("test", "quality", "commit", "changes", "command", "rebase")`.
- Přidej `REBASE_FIELDS: frozenset[str]` s poli výsledku rebase (viz `RebaseOutput` níže, včetně `status`, `summary` a dalších polí `EnvelopeBase`). Kvůli cyklu importů ho nedefinuj přes import z `workflow`. Musí se rovnat `set(RebaseOutput.model_fields)`, což ohlídá test.
- `result_fields`: `elif name == "rebase": fields = set(REBASE_FIELDS)`.

### 2. `aifactory/src/aifactory/engine/defaults/roles.yaml`
- Nová role:
  ```yaml
  resolve:
    agent: builder
    output_type: BuildOutput
    gates: [diff_matches_claims]
    description: Resolve the conflicts a rebase onto base left, editing only the conflicted files
    retries: 1
  ```
- Nový code step:
  ```yaml
  rebase:
    owner: git
    description: Rebase the branch onto base and leave any conflicts in the tree for the resolver
  ```
  Obě description musí projít `check_description` (nesmí jen opakovat jméno).

### 3. `aifactory/src/aifactory/workflow/rebase.py` (nový)
Čistý git přes `subprocess` (`gitops` z `run` sem neimportuj, aby workflow nezáviselo na run). Každý git příkaz spouštěj s `GIT_EDITOR=true` a `-c core.editor=true` a s `--no-autostash` tam, kde to jde.
- `class RebaseOutput(dt.EnvelopeBase)` (`dt` = `aifactory.engine.data_types`, nebo načtený stejně jako jinde ve workflow), pole: `onto: str`, `before: str`, `clean: bool`, `conflict: bool`, `files: list[str]`, `squashed: bool = False`. `status="success"`, `summary` čitelně, např. `rebased onto abc1234: conflicts in src/app/model.py` nebo `rebased onto abc1234 cleanly`.
- `unmerged_files(root) -> list[str]`: `git diff --name-only --diff-filter=U`, seřazené a bez duplicit.
- `conflict_markers(root, files) -> list[str]`: soubory, které obsahují řádek začínající `<<<<<<< ` nebo `>>>>>>> ` (nebo přesně `<<<<<<<` / `>>>>>>>`). `=======` nekontroluj, dává falešné poplachy v markdownu. Neexistující soubor (smazaný při řešení) není chyba.
- `rebase_onto(root, onto) -> RebaseOutput`:
  1. `before = HEAD`. Když `onto` je předek `HEAD` (`merge-base --is-ancestor onto HEAD`), vrať clean (nic nedělej).
  2. `git rebase -q onto`. Při exit 0 vrať clean.
  3. Jinak `git rebase --abort`, `git reset --hard -q onto`, `git merge --squash before` (exit != 0 se čeká).
  4. `files = unmerged_files(root)`. Když je prázdné, squash commitni (`git commit -q -m "Rebase onto <onto7> (squash of <before7>)"`) a vrať `clean=True, squashed=True`. Jinak vrať `conflict=True, files=files, squashed=True` a strom nech se značkami.
  Chybu gitu mimo očekávaný konflikt (např. neznámé `onto`) vyhoď jako `RuntimeError`.

### 4. `aifactory/src/aifactory/workflow/interpreter.py`
- Do `CodeRunner` Protocol přidej `def rebase(self, run: Any) -> Any: ...  # -> RebaseOutput`.
- `EngineCodeRunner.rebase(run)`: `onto = (run.prompt_variables or {}).get("rebase_onto")`. Když chybí: `RuntimeError("the rebase step needs a target: run the resolve workflow through `factory task resolve`")`. Jinak `rebase_onto(Path(run.repo_root), onto)`.
- `_Interpreter.code_step`: větev `elif step.action == "rebase":` volá `self.code.rebase(self.run)`, pak `ph.log(onto=…[:7], clean=…, conflict=…, files=", ".join(files))` a `self.store(step.key, result)`. Envelope se tak stane `previous` pro agenta `resolve`, který v promptu dostane seznam souborů.
- Aktualizuj docstring modulu (seznam code steps).
- `workflow/__init__.py`: exportuj `RebaseOutput`, `rebase_onto`, `unmerged_files`, `conflict_markers`.

### 5. `aifactory/src/aifactory/defaults/workflows/resolve.yaml` (nový)
```yaml
# Konflikt PR (krok 6 "Běh úkolu"): factory task resolve <task-id>.
# Phases: engineer(request) -> git(rebase) [-> builder(resolve), jen při konfliktu] -> code(test)
# Commit a push dělá kód až po workflow: jen bez konfliktních značek a se zeleným testem.
name: resolve
description: Bring a conflicting pull request up to date with base and prove the suite is still green
steps:
  - rebase
  - resolve:
      when: rebase.conflict
      description: Settle every conflict in the files the rebase reported, keeping both sides' intent
  - test:
      description: Re-run the suite on the rebased branch before it is pushed
accept: test.passed
```
Musí projít `factory workflow check` bez chyb i warningů. Uprav description, pokud je check odmítne.

### 6. `aifactory/src/aifactory/run/resolve.py` (nový)
- `RESOLVE_WORKFLOW = "resolve"`.
- `@dataclass(frozen=True) class ResolveSpec: onto: str; before: str; base: str`.
- `resolve_prompt(task, worktree, base, onto) -> str`: hlavička jako v `task_prompt` (id, title, předci, working directory). Pak sekce `## Resolve` (anglicky, jako ostatní prompty):
  - „Branch was rebased onto `<base>` (`<onto7>`). The previous step's report lists the files with conflicts.“
  - „Resolve every conflict in exactly those files: keep what this task intended and what is now in base; remove all conflict markers.“
  - „Change no other file. Do not run git add, commit, rebase, merge, reset or checkout; code stages and commits the result.“
  - Na konec `## Task` s `task.body`.
- `class ConflictWriteGuard(TaskWriteGuard)`: v `__init__(main_root, worktree, task_id, main_ignored)` volá super s prázdným `TaskScope(task_id, (), ())`. `snapshot(run)` při prvním volání, kdy `unmerged_files(worktree)` není prázdné, zafixuje `self.scope = TaskScope(task_id, tuple(files), ())` (kešuj, aby retry po `git add` agenta scope nezúžil). Pak volá `super().snapshot(run)`. Bez konfliktu zůstane scope prázdný, takže agent nesmí nic.
- `finish_resolve(worktree, wf, task_id, spec) -> str | None` vrací text chyby nebo None:
  - `r = wf.results.get("rebase")`. Když chybí: `"workflow resolve has no rebase step"`.
  - Když `r["conflict"]`: `left = conflict_markers(worktree, r["files"])` → `f"conflict markers left in: {', '.join(left)}"`. Jinak `git add -A -- <files>`. Když je pak `git ls-files -u` neprázdné, vrať `"unresolved paths: …"`. Pak `git commit -q -m f"{task_id}: rebase onto {base} {onto7}, resolve conflicts in {', '.join(files)}"`.
  - Při čistém rebase nedělej nic.
- `restore(worktree, before) -> None`, best-effort: `git rebase --abort` a `git merge --abort` (chyba nevadí), `git reset --hard -q before`, `git clean -fdq` (bez `-x`). Nakonec ověř `HEAD == before`, jinak `RuntimeError`.

### 7. `aifactory/src/aifactory/run/task.py`
- Z `resolve_workflow` vytáhni `named_workflow(name, config, task_id) -> Workflow` (`.factory/workflows/` v base, jinak packaged; stejné chybové kódy). `resolve_workflow` ho volá s `effective_workflow(task)`.
- `run_task(..., resolve_onto: str | None = None)`, interní parametr stejně jako `branch`. Vyžaduje `branch`, jinak `TaskRunError("unknown_branch", …)`. Pokud je zadaný:
  - `fork_sha = resolve_onto` (ne `existing_pr.base_sha`); `before = rev_parse(refs/heads/<branch>)`;
  - kontrola `no_writes` se přeskočí (scope tvoří soubory s konfliktem);
  - `workflow = named_workflow(RESOLVE_WORKFLOW, rc.config, task_id)` + kontrola, že obsahuje `CodeStep` s `action == "rebase"`, jinak `TaskRunError("invalid_workflow", "workflow resolve needs a rebase step")`;
  - `prompt = resolve_prompt(task, worktree, rc.base, resolve_onto)`;
  - `_Job(..., resolve=ResolveSpec(onto, before, rc.base))`.
- `_Job` dostane `resolve: ResolveSpec | None = None`.
- `_execute`:
  - guard = `ConflictWriteGuard(main, worktree, row.task_id, ignored)` pro resolve, jinak `TaskWriteGuard`;
  - `variables["rebase_onto"] = job.resolve.onto` pro resolve;
  - po workflow pro resolve: když `error is None`, nastav `error = finish_resolve(...)`, přičemž výjimku (RuntimeError/OSError) převeď na text. Když `error is not None`, zavolej `restore(worktree, job.resolve.before)`. Selhání restore připoj k chybě, nevyhazuj;
  - v `except BaseException` pro resolve nejdřív best-effort `restore` (v `contextlib.suppress(Exception)`), pak původní chování;
  - `store.finish(..., gitops.head(worktree), error)` až po restore, aby `head_sha` odpovídal větvi;
  - `publish(..., lease=job.resolve.before if job.resolve else None)`.

### 8. Push s force-with-lease
- `providers/git.py`: `push(cwd, remote, branch, lease: str | None = None)`. S `lease` přidej `--force-with-lease=refs/heads/<branch>:<lease>`.
- `providers/base.py`: `GitProvider.push(self, worktree, branch, lease: str | None = None)` předává dál.
- `providers/local.py`: override `push` se stejnou signaturou. Bez remote se nic nepushuje.
- GitHub/Azure push nepřepisují, takže nic dalšího (ověř `grep "def push"`). Uprav i fake providery v testech, pokud `push` přepisují.

### 9. `aifactory/src/aifactory/review/publish.py`
- `publish(..., lease: str | None = None)` → `provider.push(worktree, branch, lease=lease)`.
- U existujícího PR: `store.update_pr(row.branch, body=body, state=OPEN, base_sha=row.base_sha)`. U return je to stejná hodnota, u resolve nový `onto`.

### 10. `aifactory/src/aifactory/review/flow.py`
- Z `return_task` vytáhni helper `_free_branch(ctx, row)`: kontrola main checkoutu, dirty worktree a odstranění worktree větve. Použij ho v `return_task` i `resolve_task`.
- Nová `resolve_task(repo, task_id, *, provider=None, code=None) -> TaskRunResult`:
  - `_checked_pr` (stav `mergeable` i `conflict` je v pořádku; resolve při `mergeable` jen aktualizuje větev na base);
  - `_free_branch`;
  - `warnings = _catch_up_base(ctx)`, `onto = pgit.rev_parse(main, f"refs/heads/{base}")`. Když je None: `ReviewError("unknown_base", …)`;
  - ProviderError a RuntimeError převeď na ReviewError jako v `return_task`, v `finally` zavři store;
  - `result = run_task(repo, task_id, force=True, code=code, provider=ctx.provider, branch=row.branch, resolve_onto=onto)`, pak `result.warnings = (*result.warnings, *warnings)`.
- `_approve`: při `CONFLICT` hlášku změň na
  `f"PR {row.url} does not merge into {row.base}; run `factory task resolve {task_id}` to rebase it onto {row.base}"` (kód `conflict` zůstává).
- `_done_entry`: workflow pro řádek `## Běhy` ber z nejnovějšího úspěšného běhu, který **není** `resolve`, s fallbackem na jakýkoli úspěšný běh.
- Aktualizuj docstring modulu.
- `review/__init__.py`: export `resolve_task` a zmínka v docstringu.
- `run/__init__.py`: docstring zmíní resolve. Export není nutný.

### 11. `aifactory/src/aifactory/cli.py`
- Parser `resolve`: help `"rebase the task's pull request onto base and resolve conflicts"`. Description: nový běh na větvi PR, rebase na aktuální base, při konfliktu agent upraví jen soubory s konfliktem, pak test, force-push a aktualizace PR. Při selhání zůstane větev tak, jak byla před rebase. Argument `task_id`, přidat do smyčky `--json/--repo`.
- `_task_resolve(args, root)` → `_run_output(args, lambda: resolve_task(root, args.task_id))`. Dispatch v `_task`.
- `TASK_EPILOG`: sekce `task approve / return / resolve / clean`; u `conflict` poznámka „approve: run `task resolve`“, přidej `unknown_base`. Uprav i řádek 5 docstringu (seznam příkazů).

## Testy (`aifactory/tests/`)

### Úpravy existujících
- `tests/workflow/workflow_fakes.py`: `FakeCodeRunner.rebase(self, run)` vyhodí `AssertionError("no scripted rebase")` (splní Protocol).
- `tests/workflow/test_default_workflows.py`: přidej `"resolve"` do `NAMES` (případně přejmenuj test na „every packaged workflow“). `test_default_workflow_passes_check` pak pokryje resolve.yaml. Přidej `test_resolve_structure`: kroky `rebase` (CodeStep), `resolve` (RoleStep s `when.source == "rebase.conflict"`, agent builder), `test`; accept `test.passed`.
- `tests/engine/test_role_registry.py`: extra role `{"revise", "resolve"}`, extra code steps `{"command", "rebase"}`. Doplň aserci, že `result_fields("rebase") == frozenset(RebaseOutput.model_fields) | {"ran"}`. Uprav i inline `CODE_STEPS` fixture, pokud registr vyžaduje všechny `CODE_ACTIONS` (řádek ~257 v role_registry).
- `tests/run/test_task_pr_flow.py` a další: pokud nějaký fake provider přepisuje `push`, doplň `lease`.

### Nové: `tests/workflow/test_rebase.py` (čistý git v tmp repu)
- čistý rebase: `clean=True, conflict=False`, `onto` je předek `HEAD`, historie větve zachována (počet commitů);
- větev už stojí na onto: no-op, HEAD beze změny;
- konflikt na stejném řádku: `conflict=True`, `files == ["x.txt"]`, `HEAD == onto`, `conflict_markers` soubor najde;
- `conflict_markers` ignoruje `=======` v markdownu a smazaný soubor;
- `EngineCodeRunner().rebase(run)` bez `rebase_onto` vyhodí RuntimeError (stačí jednoduchý objekt s `prompt_variables={}` a `repo_root`).

### Nové: `tests/run/test_task_resolve.py` (provider `local`, falešný harness přes `run_repo.fake_env`)
Setup: `make_run_repo`, commitni `src/app/model.py` s `VALUE = 0\n` na `main`. Helper `ResolveCode(FakeCodeRunner)` s reálným `rebase` (`EngineCodeRunner().rebase(run)`) a skriptovaným `test`. Běhy T01/T02 (plan-commit, reálný commit, `code=None`). T02 spouštěj s `force=True`, protože závisí na T01.
- T01 planner: zapíše svůj spec + `src/app/model.py` = `VALUE = 1\n`. T02 planner: spec `specs/M01-S01-T02-loader.md` + `VALUE = 2\n`.

1. `test_conflict_resolve_then_approve` (hlavní scénář z „Done“): run T01, run T02, approve T01 (merged), approve T02 → `ReviewError` s kódem `conflict` a textem obsahujícím `factory task resolve M01-S01-T02`. Také přes CLI `--json`: `errors[0].code == "conflict"`, message obsahuje `task resolve`. Pak builder effect zapíše `VALUE = 3\n` a vrátí `ok(changed_files=["src/app/model.py"], commit_message="…")`. `resolve_task(repo, T02, code=ResolveCode([True]))`, případně CLI `task resolve T02 --json`, kde `code` předáš přes monkeypatch nebo volej funkci přímo. Aserce:
   - `result.ok`, `run.workflow == "resolve"`, builder volán právě jednou a jeho `previous()` obsahuje `src/app/model.py`;
   - `git merge-base --is-ancestor main <branch>`; `git show <branch>:src/app/model.py == "VALUE = 3"`; spec T02 na větvi je;
   - PR row: stav `open`, `base_sha == rev-parse main`; nová řádka běhu na stejné větvi;
   - `approve_task(repo, T02)` projde, `main:src/app/model.py == "VALUE = 3"` a oba task soubory na `main` mají `status: done`. Řádek `## Běhy` T02 uvádí `plan-commit`, ne `resolve`.
2. `test_clean_rebase_skips_agent`: T02 píše jiný soubor (`src/app/loader.py`), T01 approved. `resolve_task` s `ResolveCode([True])` a bez builder envelope ve skriptu projde, žádné volání builderu, `main` je předek větve a počet commitů větve nad main odpovídá (historie zachována). Approve projde.
3. `test_unresolved_conflict_restores_branch`: builder nic nezmění (`ok()`, bez effectu). Běh `failed`, chyba obsahuje `conflict markers`, `rev-parse <branch> == before`, `git status --porcelain` ve worktree běhu je prázdné, neprobíhá rebase ani merge (`.git` worktree nemá `rebase-merge`/`MERGE_HEAD` a `git ls-files -u` je prázdné), `task_prs.base_sha` beze změny, `result.pr` bez nového pushe.
4. `test_red_suite_restores_branch`: builder vyřeší, `ResolveCode([False])` → failed, větev == before.
5. `test_clean_rebase_red_suite_restores_branch`: čistý rebase + `ResolveCode([False])` → větev == before (i nekonfliktní rebase se vrátí).
6. `test_resolver_outside_conflict_is_breach`: builder zapíše i `src/app/other.py` → run failed (breach), `other.py` neexistuje, větev == before.
7. `test_resolve_force_pushes`: bare `origin` + remote, jako `test_approve_catches_up_base`. Po úspěšném resolve je `git rev-parse` větve v origin rovno lokálnímu tipu (force-with-lease push prošel).
8. `test_resolve_without_pr`: `ReviewError("no_pr")`. CLI `task resolve T02 --json` → exit 2. `task --help` a `task resolve --help` zmiňují resolve.

Pozor: `fake_env` nastavuje identity; rebase potřebuje committer identity. Pokud git v testech otevře editor, ověř, že `rebase_onto` nastavuje `GIT_EDITOR=true`.

## Ověření
```bash
just test
just typecheck
just lint        # ruff check + ruff format --check
```
Všechny tři musí skončit s exit 0. Pak ještě ručně `just factory workflow check aifactory/src/aifactory/defaults/workflows/resolve.yaml`, pokud je pro check k dispozici roster. Jinak to pokrývá parametrizovaný test.

## Mimo rozsah
- Automatické spuštění `resolve` (auto-continue, dashboard) se nedělá.
- Approve review hostingu (D11) zůstává TODO.
