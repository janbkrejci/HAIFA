# Plán: tok PR — publish, `task approve`, `task return`, `task clean` (úkol 2.12)

Kroky 4, 5 a 7 z „Běh úkolu“ v `docs/product-brief.md`. Na konci úspěšného běhu se udělá push a vytvoří se PR. `factory task approve` přidá commit `status: done` a merguje. `factory task return` spustí nový běh na téže větvi. Worktree se po merge a přes `factory task clean` uklidí.

**Approve review se NEPOSÍLÁ** (D11, dočasné). Musí to být vidět v kódu (komentář `TODO(D11)`) i v nápovědě CLI.

Pevná omezení: `vendor/` a `prototype/` se nemění. Mimo rozsah: `backlog sync` (2.13), `resolve` (2.14) a approve review jménem uživatele.

## Co už existuje (nepřepisovat, použít)

- `aifactory/src/aifactory/run/`: `task.py` (`run_task`, `_execute`, `task_prompt`, který už přidává `## Note`), `store.py` (`TaskRunStore`, tabulka `task_runs`, `_txn`, `serialized`, `_now`), `gitops.py` (`git`, `main_root`, `head`, `ensure_excluded`, `next_branch`), `errors.py` (`TaskRunError(code, message)`).
- `aifactory/src/aifactory/providers/`:
  - `base.py`: `GitProvider` (`push`, `create_pr`, `status`, `merge(pr, head_sha, subject, strategy=None)`, `comment`), `PullRequest`, `PrStatus`, `OPEN/MERGED/CLOSED`, `CONFLICT`, `ProviderError`, `MergeFailed`.
  - `local.py`: PR = větev. `status` vrací CLOSED, když větev neexistuje. `merge` merguje lokálně do base, posune ji a pushne, pokud existuje remote. `push` je bez remote no-op.
  - `github.py`, `azure.py`.
  - `git.py`: `rev_parse`, `is_ancestor`, `has_remote`, `push`, `checked_out_in`, `advance_branch`, `remove_worktree`.
  - `get_provider(settings, root)`.
- `aifactory/src/aifactory/backlog/taskfile.py` už má `run_entry(date, workflow, pr_url, cost)`, `mark_done(text, entry, pr_url=None)` (idempotentní) a `has_entry`. Použij je, neportuj znovu.
- `ProjectSettings` (`config/settings.py`): `base`, `remote`, `worktrees_dir`, `git_provider` (výchozí `local`), `merge_strategy`.
- `RunConfig` (`config/run.py`): `load_run_config(main)` → `.base`, `.commit`, `.config.settings`, `.local.trace_db_path(main)`.
- Trace schéma v `engine/tracer.py` (`sessions.total_cost/total_tokens`, `phases`, `events.payload_json`, `gate_results`) je stejné jako v prototypu. `prototype/src/haifa_proto/prbody.py` proto jde přenést téměř doslova.
- `WorkflowRun` (`workflow/interpreter.py`): `records: list[StepRecord]` (`step, kind, owner, harness, model`), `envelopes`, `results`, `adw_id`.

## 1. Tabulka `task_prs` v `run/store.py`

Do `_SCHEMA` přidej (stejně jako v prototypu `run.py:110-126`):

```sql
CREATE TABLE IF NOT EXISTS task_prs (
  branch TEXT PRIMARY KEY, task_id TEXT NOT NULL, provider TEXT NOT NULL,
  pr_id TEXT NOT NULL, url TEXT NOT NULL, base TEXT NOT NULL, base_sha TEXT NOT NULL,
  title TEXT NOT NULL, body TEXT NOT NULL, state TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, merged_at TEXT, merge_sha TEXT
);
CREATE INDEX IF NOT EXISTS task_prs_task ON task_prs(task_id);
```

Přidej:

- `_PR_COLUMNS` a `@dataclass TaskPrRow` s `to_json()` a `request() -> PullRequest` (`PullRequest(pr_id, url, branch, base, title)`). Import `PullRequest` z `aifactory.providers.base` nevytváří cyklus: providers importují jen `config`.
- Metody `TaskRunStore`:
  - `save_pr(row)`: INSERT OR REPLACE.
  - `update_pr(branch, **fields)`: neznámé sloupce → `ValueError`, `updated_at` se nastaví automaticky.
  - `pr_for_branch(branch)`.
  - `latest_pr(task_id)`: nejnovější PR v jakémkoli stavu.
  - `open_pr(task_id)`, `open_prs()`, `prs_for_task(task_id)`.
  - `runs_on_branch(branch)`: nejnovější první.
  - `all_runs()`: nejdřív `_reap()`, pak všechny řádky.
- Exportuj `TaskPrRow` z `run/__init__.py`. Přidej `task_prs_for(repo, task_id)`, stejně jako je udělané `task_runs_for` (bez trace DB vrací `[]`).

## 2. `GitProvider.update_pr`

`return` aktualizuje popis existujícího PR. Rozhraní na to zatím nemá metodu:

- `base.py`: nová abstraktní metoda `update_pr(self, pr: PullRequest, body: str) -> None`.
- `local.py`: `return None`, protože popis žije jen v `task_prs.body`.
- `github.py`: `self.gh.run("pr", "edit", pr.id, "--body-file", "-", stdin=body)`.
- `azure.py`: `self._ready()`, pak `az repos pr update --id <id> --org … --description <řádky z _description_lines(body)> --detect false --output json --only-show-errors`.
- Testy: jeden test na github (falešný `gh`: klíč `pr edit`, ověř argv a stdin) a jeden na azure (falešný `az`: ověř argv, `pr_json` jako odpověď). Obojí přidej k existujícím souborům `tests/providers/test_providers_github.py` a `test_providers_azure.py`.

## 3. Nový balíček `aifactory/src/aifactory/review/`

### `review/errors.py`

`ReviewError(code, message)` ve stejném tvaru jako `TaskRunError`.

### `review/prbody.py`

Přenes `prototype/src/haifa_proto/prbody.py`:

- Funkce: `pr_title`, `run_cost`, `branch_cost`, `StepInfo`, `CheckInfo`, `run_steps`, `run_checks`, `pr_body`.
- Importy změň na `aifactory.backlog.Task` a `aifactory.workflow.interpreter.WorkflowRun`/`StepRecord` (nebo na to, co exportuje `aifactory.workflow`).
- Značka v popisu: `<!-- factory: task=… branch=… -->`.
- Popis obsahuje sekce `## Zadání` (plus poznámky běhů), `## Agenti`, `## Gates a testy`, `## Review` a `## Náklady`.

### `review/publish.py`

`publish(main, settings, store, row, task, wf, provider) -> TaskPrRow`, přenos `run.publish` z prototypu (`run.py:809-848`):

1. `provider.push(Path(row.worktree), row.branch)`.
2. Popis se sestaví z úspěšných běhů na větvi.
3. Když už pro větev existuje `pr_for_branch`, zavolá se `provider.update_pr(existing.request(), body)` a `store.update_pr(branch, body=body, state=OPEN)`.
4. Jinak se zavolá `provider.create_pr(branch, pr_title(task), body)` a uloží se `TaskPrRow`: `state="open"`, `provider=provider.name`, `base=row.base`, `base_sha=row.base_sha`.

### `review/flow.py` (approve, return, clean)

Společný kontext `_Ctx(main, rc, store, provider)`:

- `main = run.gitops.main_root(repo)`, `rc = load_run_config(main)`. `ConfigError` → `ReviewError("invalid_config")`.
- `store = TaskRunStore(rc.local.trace_db_path(main))`.
- `provider` z parametru, jinak `get_provider(rc.config.settings, main)`. `ProviderError` → `ReviewError(exc.code, exc.message)`.
- Každá veřejná funkce převádí `ProviderError` na `ReviewError` a ve `finally` zavře store.

**Pomocné funkce:**

- `_checked_pr(ctx, task_id) -> tuple[TaskPrRow, PrStatus]`:
  - `store.latest_pr` je `None` → `no_pr` („run it first“).
  - `row.state != "open"` → `pr_not_open` („PR <url> is <state>“).
  - `store.running(task_id)` → `already_running`.
  - `status = provider.status(row.request())`.
  - `CLOSED` → `store.update_pr(branch, state="closed")`, pak `pr_not_open`.
  - `MERGED` → `store.update_pr(branch, state="merged", merged_at=_now(), merge_sha=status.merge_sha)`, pak `pr_not_open` s hláškou „merged outside factory; `backlog sync` (2.13) marks it done“.
- `_catch_up_base(ctx) -> list[str]`: vrací varování, nikdy nevyhazuje.
  - Bez `has_remote(main, remote)` vrátí `[]`.
  - `git fetch <remote> <base>`, pak `theirs = rev_parse(refs/remotes/<remote>/<base>)` (záloha `FETCH_HEAD`) a `ours = rev_parse(refs/heads/<base>)`.
  - Když je `ours` předkem `theirs`, zavolá `providers.git.advance_branch(main, base, theirs, ours)`. Ten dělá `merge --ff-only` tam, kde je base checkoutnutá, jinak `update-ref`.
  - Když se větve rozešly, vrátí varování `base <b> and <remote>/<b> have diverged`. `ProviderError`/`RuntimeError` → varování `base not updated: …`.
  - Fetch přidej jako funkci `fetch(root, remote, branch)` do `providers/git.py`.
- `_remove_run_worktrees(ctx, branch) -> (removed, warnings)`: pro každý `runs_on_branch` zavolá `providers.git.remove_worktree(main, Path(r.worktree))`. Chyby jdou do varování.

**`approve_task(repo, task_id, *, provider=None) -> ApproveResult`**

1. `row, status = _checked_pr(...)`. `status.mergeability == CONFLICT` → `ReviewError("conflict", "… rebase the branch or return the task")`.
2. V kódu tento komentář:
   ```python
   # TODO(D11): approve currently does NOT send an approve review in the hosting on behalf of
   # the user; it goes straight to the done commit and merge. Temporary, to be done (D11).
   ```
3. Worktree větve:
   - `where = providers.git.checked_out_in(main, branch)`.
   - Hlavní checkout → `branch_checked_out`.
   - Žádný → dočasný `main/<worktrees_dir>/approve-<branch s / → ->`. Nejdřív `remove_worktree`, pak `run.gitops.ensure_excluded(main, ["/" + worktrees_dir + "/"])` a `git worktree add <temp> <branch>`.
4. Task na tipu větve: `load_backlog(worktree, settings)`, najdi `Task` podle id. Nenalezen → `unknown_task`.
5. `entry = run_entry(date.today().isoformat(), workflow, row.url, cost)`:
   - `workflow` je z posledního úspěšného běhu na větvi, jinak `"?"`.
   - `cost = branch_cost(store.db_path, run_ids)[0]`.
6. `new = mark_done(text, entry, pr_url=row.url)`. Když se text změnil, zapiš ho, udělej `git add <task.path>` a `git commit -q -m "<task-id>: status done"`.
7. `provider.push(worktree, branch)` a `head = git rev-parse HEAD`.
8. `merge_sha = provider.merge(row.request(), head, row.title)`, kde strategie je `None`, tedy z nastavení. `MergeFailed` → `ReviewError(exc.code, …)`: done commit na větvi zůstane, a protože je `mark_done` idempotentní, opakování je bezpečné.
9. `store.update_pr(branch, state="merged", merged_at=_now(), merge_sha=merge_sha)`.
10. `warnings += _catch_up_base(ctx)`.
11. Smaž worktree všech běhů na větvi a dočasný worktree. Posbírej `removed_worktrees`.
12. `ApproveResult(task_id, pr=<řádek po update>, merge_sha, strategy, reviewed=False, base_sha=rev_parse(base), removed_worktrees, warnings)`. `to_json()` vrací `{"ok": True, …}`.

**`return_task(repo, task_id, note, *, provider=None, code=None) -> TaskRunResult`**

1. Prázdná `note` → `missing_note`.
2. `row, _ = _checked_pr(...)`.
3. Worktree všech běhů na větvi a `checked_out_in` (hlavní checkout → `branch_checked_out`). Kterýkoli s necommitnutými změnami (`git status --porcelain` není prázdný) → `dirty_worktree`. Jinak je všechny smaž.
4. `provider.comment(pr, "Vráceno k přepracování:\n\n<note>")`.
5. Zavři store a zavolej `run_task(repo, task_id, note=note.strip(), force=True, code=code, provider=provider, branch=row.branch)` (viz bod 4). Výsledek vrať.

**`clean_worktrees(repo, *, provider=None) -> CleanResult`**

1. Obnov stav otevřených PR: pro každý `store.open_prs()` zavolej `provider.status`. `CLOSED` → `update_pr(state="closed")`, `MERGED` → `update_pr(state="merged", merged_at, merge_sha)`. `ProviderError` jde do varování a pokračuje se.
2. Pro každý běh z `store.all_runs()`:
   - Běh je `running` nebo jeho worktree na disku neexistuje → přeskoč.
   - PR na větvi je `merged` → důvod `merged`.
   - PR je `closed` → důvod `closed`.
   - Na větvi není otevřený PR a existuje novější běh téhož tasku (`started_at` větší, nebo pozdější v pořadí `for_task`) → `abandoned`.
   - Jinak se nechává: poslední běh tasku bez PR, například selhaný, ze kterého uživatel ještě může vycházet, nebo otevřený PR.
   - Smaž `providers.git.remove_worktree(main, path)`. Chyba jde do varování.
3. `CleanResult(removed=[{run_id, task_id, branch, worktree, reason}], warnings)`. `to_json()` vrací `{"ok": True, "removed": [...], "warnings": [...]}`.

### `review/__init__.py`

Docstring popisuje tok a výslovně říká, že approve review zatím neposílá (D11). Exportuje `ReviewError`, `ApproveResult`, `CleanResult`, `approve_task`, `return_task`, `clean_worktrees`, `publish`, `pr_body`, `pr_title`.

## 4. Úpravy `run/task.py`

- `TaskRunResult` dostane `pr: TaskPrRow | None = None` a `pr_error: str | None = None`. `ok` platí, když `state == SUCCEEDED and pr_error is None`.
- `run_task(..., provider: GitProvider | None = None, branch: str | None = None)`:
  - `branch` je interní parametr pro `return`. V docstringu uveď, že ho používá `review.return_task`.
  - S `branch`:
    - `rev_parse(refs/heads/<branch>)` neexistuje → `TaskRunError("unknown_branch")`.
    - `fork_sha = store.pr_for_branch(branch).base_sha`, jinak `rc.commit`.
    - Nevolá se `next_branch`.
    - `row.base_sha = fork_sha`.
  - `provider` se vyřeší před `claim`: `get_provider(settings, main)`, `ProviderError` → `TaskRunError(exc.code, …)`. Nic se tak nevytvoří, když je provider špatně nastavený.
- `_execute` dostane `new_branch: bool`, `task`, `provider`:
  - Worktree: nová větev → `git worktree add -b <branch> <wt> <rc.commit>` (jako dnes). Existující větev → `git worktree add <wt> <branch>`.
  - Po `store.finish(... SUCCEEDED ...)`: `from aifactory.review.publish import publish` jako **lokální import uvnitř funkce**, jinak vznikne cyklus `run` ↔ `review`. Pak `result.pr = publish(...)`. `ProviderError` → `result.pr_error = f"{code}: {message}"` a `result.pr = store.pr_for_branch(branch)`.
- Aktualizuj docstring modulu (už neplatí věta „Push and pull request are not part of this (2.12)“) a docstring `run/__init__.py`.

## 5. CLI (`cli.py`)

Nové podpříkazy v `_add_task_commands`, všechny s `--json` a `--repo` (přidej je do tuple `for child in (...)`):

- `approve ID`. Help: „merge the task's pull request after a commit with status: done“. Description musí obsahovat: „Temporary (D11, to be done): no approve review is sent to the hosting yet; approve goes straight to the done commit and the merge.“
- `return ID --note TEXT` (`required=True`). Description: „Start a new run on the same branch with the note in the prompt; the pull request is updated.“
- `clean`: bez ID. „Remove worktrees of runs whose PR is merged or closed, and of abandoned runs (a newer run of the task exists).“

`_task` dispatch rozšiř o `approve`, `return` a `clean` a přidej `except ReviewError` se stejným výstupem jako `TaskRunError` a exit **2**. `approve` a `clean` nepotřebují backlog root, stačí `_backlog_root(args.repo)` jako dnes.

Výstupy:

- `task run`:
  - JSON: `{"ok", "run", "pr": pr.to_json() | None, "pr_error", "warnings"}`.
  - Text: navíc `pr <url>`, nebo `factory task run: pr: <pr_error>` na stderr.
- `task approve`:
  - JSON: `result.to_json()`, exit 0.
  - Text: `merged <url> into <base> (<merge_sha[:7]>)`, pak řádek `note: approve review not sent (D11, temporary)` a případná varování na stderr.
- `task return`: stejně jako `run`, s `redirect_stdout(sys.stderr)` při `--json`. Exit 0/1 podle `result.ok`.
- `task clean`:
  - JSON: `result.to_json()`.
  - Text: řádek `removed <worktree> (<reason>, <task-id>)`, na konci `N worktree(s) removed`.
- `task show`: přidej `"prs": [p.to_json() for p in task_prs_for(...)]` do JSON a sekci `prs:` do textu (`<state> <url> <branch>`).
- `TASK_EPILOG` doplň o:
  ```
  task approve / return / clean:
    no_pr, pr_not_open, already_running, conflict, branch_checked_out,
    dirty_worktree, missing_note, unknown_task, merge_failed, push_failed   (exit 2)
    approve does not send an approve review yet (temporary, D11)
  ```
  a u `task run` o `unknown_branch` a o to, že po úspěchu se udělá push a PR.

## 6. Testy (`aifactory/tests/run/`, provider `local`, falešné harnessy z `run_repo.py`)

Nový soubor `tests/run/test_task_pr_flow.py`. Fixtures `script` (přes `fake_env`) a `repo` (`make_run_repo`) jsou stejné jako v `test_task_run.py`. Pomocná funkce `succeed(script)` nastaví planneru `write(wt, SPEC, …)` a `ok(artifacts=[SPEC], commit_message=…)`. Trace DB je `repo/.factory/trace.db`.

Testy:

1. **publish**: `run_task` na T01 skončí `ok`.
   - `result.pr.state == "open"`, `pr_id == "factory/M01-S01-T01-1"`, `url == "local:factory/…"`.
   - Řádek je v `task_prs` (přes `TaskRunStore(...).pr_for_branch`).
   - `body` obsahuje `## Zadání`, `Navrhnout schéma`, `## Agenti`, `## Gates a testy`, `## Review` a `## Náklady`.
2. **approve**: po běhu zavolej `main(["task","approve",T01,"--json","--repo",…]) == 0`.
   - `git show main:backlog/M01-core/S01-model/M01-S01-T01-schema.md` obsahuje `status: done` a v `## Běhy` řádek s URL PR.
   - `git show main:<SPEC>` existuje.
   - `task_prs` má state `merged` a `merge_sha`.
   - Worktree běhu neexistuje (`removed_worktrees` ho obsahuje).
   - JSON `reviewed is False`.
   - Hlavní checkout je čistý a na `main`.
3. **approve help/D11**: `main(["task","approve","--help"])` zachytí `SystemExit`. Výstup obsahuje `D11`.
4. **return**: po běhu `script.add` druhý envelope. `main(["task","return",T01,"--note","Přidej index","--json",…]) == 0`.
   - Druhý `Call` planneru má v `prompt` text `Přidej index`.
   - Nový běh má stejnou `branch` a jiný `run_id`.
   - Starý worktree je smazaný.
   - `task_prs` má pro větev stále jeden řádek, `state == "open"`, `body` obsahuje `Přidej index` a dvě položky v `## Náklady`.
   - `return` bez `--note` skončí `SystemExit` z argparse. `return_task(repo, T01, "  ")` vyhodí `missing_note`.
5. **closed PR**: po běhu:
   - `git -C <worktree> checkout --detach` a `git branch -D factory/M01-S01-T01-1` (u provideru local je to zavřený PR).
   - `task approve --json` vrátí exit 2 a `errors[0].code == "pr_not_open"`.
   - `task_prs.state == "closed"`.
   - Další `approve` zase vrátí `pr_not_open`, protože stav je už v DB.
6. **no PR**: `approve` na T02 bez běhu vrátí `no_pr`.
7. **dotažení base**:
   - Bare remote `tmp/origin.git`, `git remote add origin`, `git push -u origin main`.
   - Testovací provider `HostedLocal(LocalProvider)` simuluje hosting: `merge` naklonuje/fetchne origin do `tmp/clone`, udělá `git merge --no-ff origin/<branch> -m subject` a `git push origin main`. Vrací sha z klonu. Lokální `main` nechává být.
   - `run_task(..., provider=HostedLocal(repo, settings))`, pak `approve_task(repo, T01, provider=…)`.
   - Lokální `main` == `origin/main` v bare repu == `merge_sha`. Pracovní strom obsahuje `SPEC`.
   - Další `run_task` na T02 má `run.base_sha == merge_sha`.
   - `settings` získej přes `load_run_config(repo).config.settings`.
8. **clean**:
   - (a) První běh T01 selže (`script.on("planner", lambda wt: write(wt, "src/other.py", "x\n"))` → breach), druhý uspěje. `task clean --json` odstraní worktree prvního běhu s důvodem `abandoned`. Worktree druhého (otevřený PR) zůstane.
   - (b) Worktree běhu se zavřeným PR (odpojit a smazat větev jako v bodě 5) se odstraní s důvodem `closed` a `task_prs.state == "closed"`.
   - (c) Bez běhů vrátí `removed == []`.
9. **store**: unit test `TaskRunStore`: `save_pr`, `update_pr` (nastaví `updated_at`, neznámý sloupec → `ValueError`), `latest_pr`, `open_prs`.

Existující testy v `test_task_run.py` a `test_task_run_cli.py` musí projít beze změn. `test_run_failure_exits_1` a podobné nesmí vytvořit PR. Pokud některý kontroluje přesný tvar JSON `task run`, nově přibudou klíče `pr` a `pr_error`: rozšiř jen tolik, kolik je nutné.

## 7. Ověření

```bash
just test
just typecheck
just lint        # případně: cd aifactory && uv run ruff format . a znovu
```

Všechny tři musí skončit exit kódem 0. Hodnotí se exit status, ne text výstupu.

## Soubory

- nové: `aifactory/src/aifactory/review/{__init__,errors,prbody,publish,flow}.py`, `aifactory/tests/run/test_task_pr_flow.py`
- měněné: `run/store.py`, `run/task.py`, `run/__init__.py`, `providers/{base,local,github,azure,git}.py`, `cli.py`, `tests/providers/test_providers_{github,azure}.py`
- neměnit: `vendor/`, `prototype/`, `docs/product-brief.md`
