# HAIFA-S03-T08 — Souběžné běhy: posun base od factory není porušení hlídače

## Problém

`TaskWriteGuard.enforce` (`aifactory/src/aifactory/run/guard.py`) porovná `HEAD`/větev
hlavního checkoutu se stavem před fází agenta. Každý posun hlásí jako
`main checkout: HEAD — moved to refs/heads/main, not rolled back`. Když během fáze
agenta běhu A jiný proces factory (např. `factory task approve` běhu B) fast-forwardem
posune `main`, který je v hlavním checkoutu vyhozený, běh A selže, i když agent nic
neudělal.

Druhý skrytý problém: po legitimním posunu `backup.verify(main_backup)` porovnává index
s `index_tree` zachyceným před fází → hlásí `(index)`, a `backup.restore` vidí
`head_moved` a nic neopraví. I tohle musí zmizet.

## Návrh

Factory příkazy, které posouvají base, zapisují **deník posunů base** (append-only
JSONL ve sdíleném git adresáři). Každý záznam nese, *kdo* posun udělal: id běhu
z proměnné prostředí `HAIFA_RUN_ID`, kterou nastaví proces běhu a kterou dědí agent
i každý příkaz factory, který agent spustí. Hlídač po fázi: když se `HEAD` hlavního
checkoutu posunul, ale větev (`symbolic_head`) zůstala, zkusí složit řetěz záznamů
z deníku (zapsaných od snapshotu) `head_před → … → head_teď`. Pokud řetěz existuje a
žádný jeho článek nepochází z vlastního běhu, posun je od factory: hlídač přepne
zálohu hlavního checkoutu na nový `HEAD` (a index tree ze záznamu) a pokračuje
v kontrole souborů, jako by base byla vždy na nové pozici. Jinak je to porušení
jako dnes.

Důsledky (odpovídají „Done means“):
- posun od cizího factory příkazu → řetěz složen → žádný problém, nic se nevrací;
- agent commitne / resetne / checkoutne v hlavním checkoutu → `HEAD` mimo řetěz nebo
  změněná větev → porušení, i když byl ve fázi také posun od factory (řetěz nedosáhne
  `head_teď`, resp. větev nesedí);
- factory příkaz spuštěný agentem → záznam má `run == vlastní run_id` → porušení;
- změny souborů hlavního checkoutu se dál vrací a hlásí (verify/restore běží nad
  přepnutou zálohou, takže se porovnává proti novému `HEAD`).

## Soubory a změny

### 1. Nový modul `aifactory/src/aifactory/run/basemoves.py`

Jen stdlib + `aifactory.run.backup` (pro index tree) — žádné importy z `providers`,
`review`, `run.task` (cykly). Obsah:

```python
RUN_ENV = "HAIFA_RUN_ID"

@dataclass(frozen=True)
class BaseMove:
    ref: str            # "refs/heads/main"
    old: str            # sha před
    new: str            # sha po
    run: str | None     # os.environ.get(RUN_ENV) v procesu, který posunul
    index_tree: str | None  # strom indexu checkoutu s base po posunu (None = base nikde vyhozená)
    command: str        # "task approve" | "config pull" | "config commit" | "backlog commit" | "advance"

def journal(root: Path) -> Path
    # <git rev-parse --git-common-dir (absolutně, relativní vůči root)>/haifa/base-moves.jsonl
def offset(root: Path) -> int
    # velikost deníku v bajtech (0 když neexistuje / chyba) — volá snapshot
def record(root: Path, ref: str, old: str, new: str, *, checkout: Path | None, command: str) -> None
    # index_tree = backup.index_tree(checkout) if checkout else None
    # run = os.environ.get(RUN_ENV) or None
    # jeden řádek JSON + "\n", open(path, "a") a jeden write(); mkdir parents.
    # NIKDY nevyhodí (OSError/RuntimeError spolkne) — deník nesmí rozbít approve/pull.
def moves_since(root: Path, start: int) -> list[BaseMove]
    # přečte od bajtu `start`, vynechá nečitelné/rozbité řádky
def factory_chain(moves, ref, start, end, own_run) -> BaseMove | None
    # Složí řetěz start→…→end jen ze záznamů s daným ref. Postup: cur=start;
    # opakuj max len(moves)×: najdi první nepoužitý záznam s old==cur; žádný → None;
    # záznam s run == own_run (a own_run není None) → None (posun od agenta);
    # cur = rec.new; cur == end → vrať tento (poslední) záznam.
def wait_for_chain(root, start_offset, ref, start, end, own_run, *, tries=10, delay=0.1) -> BaseMove | None
    # Záznam se píše až PO posunu refu, takže enforce může přijít těsně před zápisem.
    # Když řetěz chybí (ne když narazí na vlastní běh!), krátce počkej a zkus znovu.
    # Rozliš „chybí“ vs „vlastní“ — např. factory_chain vrací tuple (move|None, own: bool)
    # nebo vlastní výjimku; při own=True hned vrať None. V testech záznam existuje hned.
```

V `aifactory/src/aifactory/run/backup.py` přidej veřejnou funkci
`index_tree(root: Path) -> str | None` = `_write_tree(root)` (tenký wrapper), ať
basemoves nesahá na privátní jméno.

Docstring modulu: k čemu deník je, kdo píše, že `run` pochází z `HAIFA_RUN_ID`, a
známý limit: agent, který ručně dopíše do deníku podvržený záznam s cizím `run`,
hlídač oklame (stejně jako dnes `.gitignore` limit) — zmínit, neřešit.

### 2. Zápis do deníku v příkazech factory (lazy import `from aifactory.run import basemoves` uvnitř funkcí, ať nevznikne cyklus `run/__init__` → `task` → `providers`)

- `aifactory/src/aifactory/providers/git.py::advance_branch` — po úspěšném
  `merge --ff-only` (v `where`) i po `update-ref` zavolej
  `basemoves.record(root, f"refs/heads/{branch}", old_sha, new_sha, checkout=where, command="advance")`.
  Pokrývá `task approve` (LocalProvider.merge i `_catch_up_base` v `review/flow.py`)
  a `config pull` (`publish.py` ~ř. 378). Volitelně přidej parametr
  `command: str = "advance"` a z volajících předej `"task approve"` / `"config pull"`
  (jen pro čitelnost deníku; logika na něm nezávisí).
- `aifactory/src/aifactory/providers/publish.py::_advance` (config commit) — po
  `update-ref` zavolej `record(root, f"refs/heads/{base}", old, sha, checkout=where, command="config commit")`.
- `aifactory/src/aifactory/backlog/commit.py::commit_backlog` — před `git add` si
  zapamatuj `old = gitops.head(main)`; po úspěšném commitu
  `record(main, f"refs/heads/{base}", old, sha, checkout=main, command="backlog commit")`
  (jen když `old` není None).

### 3. Proces běhu nastaví `HAIFA_RUN_ID`

`aifactory/src/aifactory/run/task.py`, funkce kolem ř. 500–560 (blok s
`os.chdir(worktree)` a `run_workflow(...)`): před `run_workflow` ulož
`saved = os.environ.get(basemoves.RUN_ENV)`, nastav
`os.environ[basemoves.RUN_ENV] = row.run_id`; ve stejném `finally` jako
`os.chdir(prev)` vrať původní hodnotu (pop, když nebyla). Agenti dostávají
`operator_env()` = kopie `os.environ`, takže proměnnou zdědí i jejich bash a každý
`factory …` spuštěný agentem. Fake harness volá efekty in-process, takže v testech
proměnnou vidí taky.

### 4. Hlídač `aifactory/src/aifactory/run/guard.py`

- `snapshot`: přidej `"base_moves": basemoves.offset(self.main_root)` do vráceného dictu.
- `enforce`: **před** `backup.verify(main_backup, …)` doplň:

```python
main_backup = before["main_backup"]
main_head = gitops.head(self.main_root)
main_ref = gitops.symbolic_head(self.main_root)
factory_move = False
if (main_ref and main_ref == before["main_ref"] and main_head
        and main_head != before["main_head"] and before["main_head"]):
    move = basemoves.wait_for_chain(self.main_root, before.get("base_moves", 0), main_ref,
                                    before["main_head"], main_head,
                                    getattr(run, "adw_id", None))
    if move is not None:
        main_backup = dataclasses.replace(main_backup, head=main_head,
                                          index_tree=move.index_tree)
        factory_move = True
```
  Pak `off = backup.verify(main_backup, …)` a `restore(main_backup, …)` nad
  přepnutou zálohou (`CheckoutBackup` je obyčejný `@dataclass`, `replace` funguje;
  `restore` pak nevidí `head_moved` a vrací soubory proti novému `HEAD`).
  Kontrolu HEAD změň na
  `if not factory_move and (main_head != before["main_head"] or main_ref != before["main_ref"]):`
  — text hlášení beze změny. Hlavy si nečti dvakrát (použij `main_head`/`main_ref` výše).
  `index_tree=None` ze záznamu → verify index nekontroluje (stávající chování pro None).
- Docstring modulu: doplň odstavec o posunu base od factory (deník, `HAIFA_RUN_ID`,
  posun od agenta i spuštěný agentem zůstává porušením, po posunu se soubory kontrolují
  proti novému `HEAD`).
- `ConflictWriteGuard` (`run/resolve.py`) dědí — nic neměnit.
- Nic se nemění na kontrole worktree běhu.

Pozor: `own_run` je `run.adw_id` (= `row.run_id`, viz `run_workflow(adw_id=row.run_id)`).

## Testy (žádný model, žádná síť)

Helper do testů (např. v novém souboru): context manager `foreign()` —
`os.environ.pop(basemoves.RUN_ENV)` a po bloku vrátit. Simuluje příkaz factory
z terminálu operátora / jiného procesu, protože fake harness běží in-process
s proměnnou běhu A.

### A. `aifactory/tests/run/test_basemoves.py` (unit)
- `record` + `moves_since` + `offset`: zápis dvou záznamů, čtení od offsetu vrátí jen
  nový; `run` se bere z `HAIFA_RUN_ID` (monkeypatch.setenv / delenv); rozbitý řádek se
  přeskočí.
- `factory_chain`: řetěz přes dva cizí záznamy projde; článek s `own_run` → None;
  chybějící článek → None; jiný `ref` se ignoruje.
- `commit_backlog` zapíše záznam (old=head před, new=nový commit, command
  "backlog commit") — repo z `make_run_repo`, upravit soubor pod `backlog/`, zavolat
  `commit_backlog(repo)`, přečíst deník. Pokud by validace backlogu dělala potíže,
  upravit jen text těla existujícího úkolu.
- `providers.git.advance_branch` zapíše záznam s `index_tree` (base vyhozená v repu).

### B. `aifactory/tests/run/test_guard_base_moves.py` (hlídač přes `run_task` + fake harness, vzor `tests/run/test_task_run.py`, fixtures `fake_env`, `make_run_repo`)
Příprava posunu: v repu vytvoř commit na větvi `side` z `main` (např. změna
`README.md` nebo nový soubor mimo scope), `new = rev-parse side`, a vrať se na `main`
(main checkout čistý, na `main`). V efektu planneru:
1. **posun od factory projde**: `with foreign(): pgit.advance_branch(repo, "main", new, old)`,
   pak zapiš spec do worktree a `ok(artifacts=[SPEC], …)` → `run.state == "succeeded"`,
   `rev-parse main == new`, `git status --porcelain` hlavního checkoutu prázdný,
   v adresáři session neleží `guard_backup/*` od té fáze (záloha smazána).
2. **posun od agenta je porušení**: totéž bez `foreign()` → `failed`,
   `"main checkout: HEAD" in error`.
3. **oba ve stejné fázi jsou porušení**: `foreign()` posun a pak
   `git commit --allow-empty -q -m x` v hlavním checkoutu → `failed`, `main checkout: HEAD`
   v chybě. Druhá varianta: cizí posun a pak `git checkout -q -b other` v hlavním
   checkoutu → `failed` (pak v testu vrátit `main`, není nutné).
4. **soubory se dál vrací**: cizí posun + `write(repo, "README.md", "hijacked\n")` →
   `failed`, `"main checkout: README.md"` v chybě, `README.md` má obsah z **nového**
   `HEAD` (`git show main:README.md`), status čistý.

### C. Dva běhy (fake harness) — do `test_guard_base_moves.py` nebo `tests/run/test_task_pr_flow.py`
Repo: `make_run_repo` + `setup_chain(repo)` z `test_auto_continue` (T01 a T03
nezávislé, obě píší `src/app/`).
1. Běh B: `build(script, "b")` (nebo vlastní planner skript zapisující
   `src/app/b.py`) a `run_task(repo, T03)` → succeeded, otevřené PR.
2. Běh A (T01): planner efekt
   `with foreign(): approve_task(repo, T03)` a pak zápis `src/app/a.py`;
   `ok(artifacts=[], changed_files=["src/app/a.py"], commit_message=…)` (vzor
   `test_parallel_runs._child`). Ověř: `result.run.state == "succeeded"`,
   PR T03 je `merged` (`TaskRunStore.pr_for_branch`), `main` == `merge_sha`,
   hlavní checkout čistý a na `main`, běh A má otevřené PR.
3. Varianta: `approve_task` bez `foreign()` (agent spustil factory) → běh A `failed`,
   `"main checkout: HEAD"` v chybě.

Upozornění: `approve_task` odstraní worktree běhu B — to nevadí. Efekt běží s cwd ve
worktree A; `approve_task(repo, …)` dostává absolutní `repo`.

## Ověření

```
just test
just typecheck
just lint
```
(ruff format: `cd aifactory && uv run ruff format <soubory>` před `just lint`.)
Stávající testy v `tests/run/test_task_run.py` (`test_write_to_main_checkout_is_reverted`,
`test_agent_reverting_main_checkout_work_is_restored`, …) a `test_task_pr_flow.py`
musí projít beze změny.

## Omezení
- Měnit jen `aifactory/`, `justfile` (není potřeba), tento spec a app_docs soubor.
- `vendor/`, `prototype/` nesahat.
- Mimo rozsah: zápisy souborů do hlavního checkoutu od factory během fáze
  (`task add/edit/link` z dashboardu), ruční změny operátora, limit paralelity.
- `config commit`/`config pull` dnes s živým během odmítají posunout base; zápis do
  deníku přidat stejně (pokrytí, kdyby se to změnilo), test pro ně není nutný.
