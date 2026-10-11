# Plán: `factory backlog sync [--json]` (úkol 2.13)

`backlog sync` najde PR tasků, které někdo mergnul mimo HAIFA (merge v GitHubu nebo Azure DevOps, ručně `git merge`) a jejichž task v `base` ještě nemá `status: done`. Pro tyto tasky otevře **jeden PR**. PR obsahuje commit na vlastní větvi, který nastaví `status: done` a přidá řádek do `## Běhy`. Sync zároveň aktualizuje `task_prs.state` (`merged`, `closed`).

Pevná omezení:
- Sync **nikdy** necommituje do `base`. Commit vzniká jen na sync větvi v dočasném worktree.
- `vendor/` a `prototype/` se nemění.

Mimo rozsah je automatický merge sync PR.

## Co už existuje (použít, nepřepisovat)

- `aifactory/src/aifactory/review/flow.py`:
  - `_Ctx(main, rc, store, provider)` a `_context(repo, provider)`.
  - `_record_state(ctx, row, status)`: zapíše `closed` nebo `merged` do `task_prs`.
  - `_catch_up_base(ctx)`: vrací varování, nikdy nevyhazuje.
  - `_remove(ctx, path, removed, warnings)` a `_main_checkout_error`.
  - V `_approve`: získání worktree větve (`checked_out_in`, jinak dočasný `main/<worktrees_dir>/approve-…`) a sestavení `run_entry` (workflow z posledního úspěšného běhu a `branch_cost`).
- `backlog/taskfile.py`: `run_entry(date, workflow, pr_url, cost)`, `mark_done(text, entry, pr_url=None)` (idempotentní) a `has_entry(text, pr_url)`.
- `run/store.py`: `TaskRunStore` s tabulkou `task_prs`, `_PR_COLUMNS`, `TaskPrRow` (`to_json()`, `request()`), `_prs`, `update_pr`, `open_prs`, `latest_pr`, `runs_on_branch`, `_now`, konstanty `RUNNING/SUCCEEDED`.
- `providers/`:
  - `OPEN/MERGED/CLOSED` a `GitProvider` (`push`, `create_pr`, `status`, `update_pr`, `merge`).
  - `LocalProvider`: PR = větev. `status` je `MERGED`, když je tip předkem base, a `CLOSED`, když větev neexistuje.
  - `providers.git`: `rev_parse`, `has_remote`, `checked_out_in`, `remove_worktree`.
  - Konstanta `BRANCH_PREFIX = "factory/"` a `task_id_from_branch`.
- `run/gitops.py`: `git`, `main_root`, `ensure_excluded`.
- `backlog.load_backlog(root, settings)` vrací `Backlog.by_id` s objekty `Task`. `Task.status` je `todo`, `done` nebo `cancelled`.
- Testy: `tests/run/run_repo.py` (`make_run_repo`, `fake_env`, `Script`, `ok`, `write`, `git`, `T01`, `T02`, `SPEC`) a vzory v `tests/run/test_task_pr_flow.py` (`succeed`, `cli_json`, `close_pr`, `stored_pr`).

## 1. Tabulka `sync_prs` v `run/store.py`

Do `_SCHEMA` přidej:

```sql
CREATE TABLE IF NOT EXISTS sync_prs (
  branch TEXT PRIMARY KEY, provider TEXT NOT NULL, pr_id TEXT NOT NULL, url TEXT NOT NULL,
  base TEXT NOT NULL, base_sha TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
  state TEXT NOT NULL, tasks TEXT NOT NULL,          -- JSON list of task ids
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, merged_at TEXT, merge_sha TEXT
);
```

Sync PR nepatří žádnému tasku, proto má vlastní tabulku a do `task_prs` se nedává. Kdyby tam byl, `open_prs()` v `clean` i `latest_pr` by ho braly jako PR tasku.

Přidej:

- `_SYNC_COLUMNS` a `@dataclass SyncPrRow` se stejnými poli:
  - `tasks: str` je JSON.
  - `task_ids() -> list[str]`.
  - `to_json()`: `tasks` vrací jako seznam.
  - `request() -> PullRequest(pr_id, url, branch, base, title)`.
- Metody `TaskRunStore`:
  - `save_sync_pr(row)`: INSERT OR REPLACE.
  - `update_sync_pr(branch, **fields)`: stejná kontrola sloupců jako `update_pr`, automaticky nastaví `updated_at`.
  - `sync_pr_for_branch(branch)`.
  - `open_sync_prs()`: nejnovější první.
  - `sync_branches() -> list[str]`.
- Exportuj `SyncPrRow` z `run/__init__.py` (i v `__all__`).

## 2. `review/flow.py`: malý refaktor sdílených kroků (chování approve se nemění)

Vytáhni z `_approve` dvě funkce, `_approve` je pak použije:

- `_branch_worktree(ctx, branch, prefix) -> tuple[Path, Path | None]` vrací `(worktree, temp)`. Logika je stejná jako dnes:
  - Když je větev checkoutnutá v hlavním checkoutu → `_main_checkout_error`.
  - Když je checkoutnutá v existujícím worktree, vrátí ho a `temp` je `None`.
  - Jinak vytvoří dočasný `main/<worktrees_dir>/<prefix>-<branch s / → ->`. Approve předává `prefix="approve"`.
- `_done_entry(ctx, row: TaskPrRow) -> str` vrací `run_entry(date.today(), workflow or "?", row.url, cost)`:
  - `workflow` je z posledního `SUCCEEDED` běhu na `row.branch`.
  - `cost` se spočítá přes `branch_cost(ctx.store.db_path, run_ids)`.

Existující testy approve musí dál projít beze změny.

## 3. Nový modul `review/sync.py`

```python
SYNC_PREFIX = "factory-sync/"   # NOT "factory/": task_id_from_branch must not read it as a task

@dataclass
class SyncTask:      # task_id, path, pr_url, pr_branch, merge_sha
@dataclass
class SyncSkip:      # task_id, reason, pr_url
@dataclass
class SyncResult:
    pr: SyncPrRow | None
    created: bool            # a new sync PR was opened now
    updated: bool            # a commit was added to an already open sync PR
    tasks: list[SyncTask]    # tasks this sync marked done (in the PR)
    skipped: list[SyncSkip]
    states: list[dict[str, str]]   # task PRs whose state changed: task_id, branch, url, state
    warnings: list[str]
    def to_json(self) -> dict[str, object]:
        # {"ok": True, "pr": pr.to_json() | None, "url": pr.url | None, "created", "updated",
        #  "tasks": [...], "skipped": [...], "states": [...], "warnings": [...]}

def sync_backlog(repo: Path, *, provider: GitProvider | None = None) -> SyncResult
```

Obal funkce je stejný jako u `approve_task`: `_context`, `ProviderError` → `ReviewError`, `RuntimeError` → `ReviewError("worktree_failed")` a ve `finally` `ctx.store.close()`.

Postup v `_sync(ctx)`:

1. **Obnovení stavů task PR.** Pro každý `store.open_prs()`:
   - Zavolej `status = provider.status(row.request())`, pak `_record_state(ctx, row, status)`.
   - Když se stav změnil (`CLOSED` nebo `MERGED`), přidej `{task_id, branch, url, state}` do `states`.
   - `ProviderError` se zapíše jako varování a pokračuje se dalším PR.
   - Zavřený PR se jen zapíše a na task se nesahá.
2. **Obnovení stavů sync PR.** Pro každý `store.open_sync_prs()` zavolej `status`. `CLOSED` a `MERGED` zapiš přes `update_sync_pr` (u merged i `merged_at` a `merge_sha`). Chyby jdou do varování.
3. **Base.**
   - `warnings += _catch_up_base(ctx)`.
   - Startovní bod: když `has_remote(main, remote)` a existuje `refs/remotes/<remote>/<base>`, je to tento ref, jinak `refs/heads/<base>`.
   - Chybí oba → `ReviewError("unknown_base", …)`.
   - `start_sha = rev_parse(...)`.
4. **Kandidáti.**
   - Založ dočasný detached worktree `main/<worktrees_dir>/sync-check`. Nejdřív `remove_worktree` a `ensure_excluded(main, ["/<worktrees_dir>/"])`, pak `git worktree add --quiet --detach <path> <start_sha>`. Ve `finally` ho vždy smaž.
   - `backlog = load_backlog(path, settings)`.
   - Projdi každé `task_id`, které má v `task_prs` řádek ve stavu `merged`. Distinct task_id přidej do store jako `merged_task_ids()`, nebo je spočítej ze `_prs("state = 'merged'")` přes novou metodu `merged_prs()`.
   - Pro každý takový task:
     - `latest = store.latest_pr(task_id)`. Když `latest.state != MERGED` → skip `newer_pr` (task se znovu zpracovává, jeho nejnovější PR je otevřený nebo zavřený).
     - Node v base není `Task` → skip `not_in_base`.
     - `task.status == "done"` → nic nedělej, bez skipu. To je běžný případ po approve i po mergnutém syncu.
     - `task.status == "cancelled"` → skip `cancelled`.
     - Soubor v base už má `has_entry(text, latest.url)` a přitom není done → skip `reopened`. Done pro tento PR už jednou bylo zapsané a člověk ho vrátil.
     - Jinak je task kandidát `(task, latest)`.
5. **Žádní kandidáti** → vrať `SyncResult(pr=None, created=False, updated=False, tasks=[], …)`. Nevzniká žádná větev ani PR a nic se necommituje.
6. **Cíl zápisu.**
   - Existuje otevřený sync PR (po kroku 2 první z `open_sync_prs()`)? Pak piš na jeho větev: `worktree, temp = _branch_worktree(ctx, sync.branch, "sync")`.
   - Jinak použij detached worktree z kroku 4. Nová větev je `factory-sync/<n>`, kde `n` je o jedna vyšší než maximum z `refs/heads/factory-sync/*` a `store.sync_branches()`. Vzor je `gitops.next_branch`.
   - Větev v tomto kroku ještě nevytvářej.
7. **Úpravy.**
   - Pro každého kandidáta vezmi `text = (worktree / task.path).read_text()` a `new = mark_done(text, _done_entry(ctx, latest), pr_url=latest.url)`.
   - Když se text změnil, zapiš ho, udělej `git add -- <path>` a kandidáta přidej do `tasks` (`SyncTask`, `merge_sha = latest.merge_sha`).
   - Když se nezměnilo nic (všechno už je na otevřené sync větvi), vrať existující sync PR s `created=False, updated=False` a `tasks` = kandidáti. Nový PR nevzniká.
8. **Commit, jen na sync větvi.**
   - Nová větev: `git switch -q -c factory-sync/<n>` ve worktree.
   - Pojistka před commitem: `git symbolic-ref --short HEAD` ve worktree musí začínat `SYNC_PREFIX` a nesmí se rovnat `settings.base`, jinak `ReviewError("sync_on_base", …)`.
   - `git commit -q -m "backlog sync: status done for <id1>, <id2>"`.
   - `provider.push(worktree, branch)`.
9. **PR.**
   - `title = f"backlog sync: done for {len(tasks)} task(s)"`.
   - `body` sestav přes `_sync_body(branch, tasks_all)`:
     - Značka `<!-- factory: sync branch=<branch> -->`.
     - Věta, že PR doplňuje `status: done` pro PR mergnuté mimo HAIFA.
     - Odrážka na každý task: `- <id> (<path>): PR <url>`.
     - `tasks_all` = tasky dosavadního sync PR plus nové.
   - **Nový PR:** `pr = provider.create_pr(branch, title, body)` a `store.save_sync_pr(SyncPrRow(..., state=OPEN, base=settings.base, base_sha=start_sha, tasks=json.dumps(ids)))`. Výsledek má `created=True`.
   - **Existující PR:** `provider.update_pr(sync.request(), body)` a `store.update_sync_pr(branch, body=body, tasks=json.dumps(tasks_all), title=title)`. Výsledek má `updated=True`.
   - Sync PR nikdy nemerguje (mimo rozsah).
10. **Úklid.** Ve `finally` smaž dočasné worktree. Varování přidej do `warnings`. Lokální sync větev zůstává, protože u provideru `local` právě ona je PR.

Exportuj `SyncResult` a `sync_backlog` z `review/__init__.py` (i v `__all__`). Doplň docstring balíčku o bod `sync_backlog (factory backlog sync)`.

V `flow._checked_pr` změň text u `MERGED` na „…; `factory backlog sync` marks it done“ (bez „(2.13)“). Odkaz na hotový příkaz tam nepotřebuje číslo úkolu.

## 4. CLI (`cli.py`)

- V `_add_backlog_commands` přidej subpříkaz `sync`:
  - Nápověda: „open one PR that marks tasks done whose PR was merged outside factory“.
  - Popis: sync commituje jen na vlastní větev `factory-sync/<n>`, nikdy do base, a PR nemerguje.
  - Přidej ho do smyčky, která přidává `--json` a `--repo`.
- V `_backlog` obsluž `command == "sync"` **před** `load_backlog` přes novou funkci `_backlog_sync(args)`:
  - Kořen je `root = _backlog_root(args.repo)`, výsledek `result = sync_backlog(root)`.
  - `ReviewError` a `TaskRunError` → JSON `{"ok": False, "errors": [{"code", "message"}]}` nebo text na stderr, exit 2.
  - `ConfigError` stejně jako dnes, exit 2.
  - Výstup `--json`: `result.to_json()`, exit 0.
  - Textový výstup:
    - `created` → `opened <url>: done for T1, T2`.
    - `updated` → `updated <url>: …`.
    - Existující PR bez změny → `sync PR <url> already open: …`.
    - Bez PR → `nothing to sync`.
    - Pak řádky `skipped <id>: <reason>` a `PR <url> of <id> is <state>`. Varování jdou na stderr. Exit 0.
- Docstring modulu (ř. 3–4, „Implemented: …“) doplň o `backlog sync`.

## 5. Testy: `aifactory/tests/run/test_backlog_sync.py` (provider `local`)

Soubor dej do `tests/run/`, aby šel import `from run_repo import ...`. Fixture `script` a `repo` a pomocné funkce `succeed`, `cli_json`, `close_pr` a `trace_db` zkopíruj z `test_task_pr_flow.py`, nebo je importuj, pokud to jde bez cyklů. Konstanty: `TASK_FILE = "backlog/M01-core/S01-model/M01-S01-T01-schema.md"` a `BRANCH = f"factory/{T01}-1"`.

Merge mimo HAIFA udělej v hlavním checkoutu: `git(repo, "merge", "-q", "--no-ff", "-m", "outside", BRANCH)`.

Testy:

1. `test_sync_opens_pr_for_outside_merge`:
   - Průběh: `run_task` → merge mimo HAIFA → `before = git rev-parse main` → `cli_json(capsys, "backlog", "sync", "--json", "--repo", repo)`.
   - `code == 0`, `data["created"] is True`, `data["url"]` není prázdné a `[t["task_id"] for t in data["tasks"]] == [T01]`.
   - `git rev-parse main == before`: base se nezměnila.
   - `git show main:TASK_FILE` nemá `status: done`.
   - `git status --porcelain` v repu je prázdný.
   - Sync větev `factory-sync/1` existuje a `git show factory-sync/1:TASK_FILE` obsahuje `status: done` a `PR local:<BRANCH>` v části za `## Běhy`.
   - `stored_pr(repo).state == "merged"`.
   - `git log -1 --format=%s factory-sync/1` začíná `backlog sync:`.
2. `test_sync_pr_merged_then_second_sync_is_noop`:
   - Jako test 1, pak merge sync PR mimo HAIFA: `git merge --no-ff factory-sync/1` v repu. Jiná možnost je `LocalProvider(repo, settings).merge(pr, head, subject, strategy="merge")`. Strategie `squash` se u `local` nehodí, protože po ní tip není předek base.
   - `git show main:TASK_FILE` teď obsahuje `status: done`.
   - Druhý sync: `code == 0`, `data["pr"] is None`, `data["tasks"] == []` a neexistuje `factory-sync/2`.
   - V `sync_prs` je řádek `factory-sync/1` ve stavu `merged`. Ověř přes `TaskRunStore(trace_db(repo)).sync_pr_for_branch`.
3. `test_sync_closed_pr_does_not_change_task`:
   - `run_task` → `close_pr(worktree)` → sync.
   - `pr is None`, `states` obsahuje `{"task_id": T01, "state": "closed", …}` a `stored_pr(...).state == "closed"`.
   - `main:TASK_FILE` bez `status: done` a žádná větev `factory-sync/*`.
4. `test_sync_nothing_to_do`: repo bez běhů → `pr is None`, exit 0, textový výstup `nothing to sync`.
5. `test_sync_reuses_open_sync_pr`:
   - Merge mimo HAIFA → sync (`factory-sync/1`) → druhý sync bez dalších změn.
   - `created is False`, `updated is False`, `data["pr"]["branch"] == "factory-sync/1"` a neexistuje `factory-sync/2`.
6. `test_sync_after_approve_is_noop`: `run_task` → `approve_task` → sync → `pr is None`.
7. Store: `test_store_sync_prs` (`save_sync_pr`, `update_sync_pr` s neznámým sloupcem → `ValueError`, `open_sync_prs`, `sync_branches`, `to_json()["tasks"]` je list). Test může být v novém souboru, nebo ho přidej k `test_store_prs`.
8. Nápověda: `main(["backlog", "sync", "--help"])` (`SystemExit` 0) obsahuje `base` a `factory-sync`.

Testy nevolají model: `fake_env` a `Script` jako v existujících testech.

## 6. Ověření

```bash
just test
just typecheck   # mypy strict
just lint        # ruff check + ruff format --check (line-length 100)
```

Všechny tři musí skončit s exit 0. Ruční kontrola: `git diff --stat` nesmí ukázat nic ve `vendor/` ani v `prototype/`.

## Soubory

- `aifactory/src/aifactory/run/store.py`: tabulka `sync_prs`, `SyncPrRow`, metody a `merged_prs()`.
- `aifactory/src/aifactory/run/__init__.py`: export `SyncPrRow`.
- `aifactory/src/aifactory/review/flow.py`: `_branch_worktree`, `_done_entry` a text hlášky u merged.
- `aifactory/src/aifactory/review/sync.py`: nový modul.
- `aifactory/src/aifactory/review/__init__.py`: exporty a docstring.
- `aifactory/src/aifactory/cli.py`: `backlog sync`.
- `aifactory/tests/run/test_backlog_sync.py`: nový soubor.
- `aifactory/src/aifactory/backlog/`: beze změny. `mark_done`, `has_entry` a `run_entry` už stačí. Novou čistou funkci přidej jen v případě, že ji `sync.py` opravdu potřebuje.
