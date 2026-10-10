# Plán: akceptační scénář F2 ve validaci (úkol 2.18)

## Cíl

Do `just validate` přibude scénář `F2`. Na ukázkovém repu (sandbox validace) založí ukázkový backlog se 2 moduly a 5 tasky s vazbami. Tasky projdou z CLI `factory` od `task run` po mergnutý PR a `status: done` v `base`. Dva tasky poběží současně, jeden běh použije `--auto` (auto-continue spustí dva tasky za sebou) a všech 5 se schválí přes `factory task approve`.

Kontroly: 5 mergnutých PR, `status: done` u všech 5 tasků v `base`, žádný zápis mimo worktree, žádný zbylý worktree F2 běhů a `backlog check` projde.

`just validate --remote local` musí projít se scénářem `F2` bez `failed`. Projít musí i `just test`, `just typecheck` a `just lint`.

Mimo rozsah: běh proti GitHubu (ten spustí engineer). Kód ale musí v `--remote github` fungovat stejně jako ostatní scénáře, bez zvláštních větví kromě retry approve.

Pevná omezení:
- `vendor/`, `prototype/` ani `justfile` se nemění. `justfile` patří operátorovi.
- Testy nevolají model: v local režimu jede falešný harness.
- Produktový kód v `aifactory/src/` se nemění. Kdyby scénář odhalil chybu produktu, zapiš ji do `observations` a plán ji neopravuje.

## Kontext (jak validace funguje dnes)

- `aifactory/validation/runner.py` pouští scénáře v pořadí `scenarios.ORDER`. Výsledek je `ScenarioResult` (`results.py`): `outcome` se počítá z `checks`.
- `aifactory/validation/context.py`, `Context`:
  - `haifa(*argv, task=, variant=)` spustí `python -m validation.worker <argv> --repo <repo> --json` a vrátí `Cmd` (`.ok`, `.run`, `.pr`, `.payload`, `.error_code`);
  - `haifa_async` totéž neblokující (`Pending.wait()`);
  - `run_task`, `catch_up_base`, `fetch_base`, `status_in_base` / `task_in_base` (čte `TASK_PATHS[task_id]` z `origin/<base>`), `task_pr(branch)`, `task_run(run_id)`, `events(run_id, type, name)`, `reference`, `add_pr`.
- Falešný harness (`fake.py`) dostane pro jeden proces `factory` jeden skript z `fake_scripts.script_for(task, variant, repo)`. Skript má fronty podle agenta (`planner`, `builder`, `reviewer`, `documenter`) a každé volání agenta vezme další položku. Běh `--auto` spustí víc tasků v jednom procesu, takže jeho skript musí mít fronty všech tasků řetězu za sebou.
- Každý běh `simple-sdlc` má vynucené kolo review → revise. Pomocník `_script(task_id, revised, builds)` ve `fake_scripts.py` dodá plan, build(y), revise (přidá `REVIEW_RULE_MARKER` na konec souboru `revised`), dvě review (zamítne, schválí) a document. Plán a dokumentace jdou do `specs/<stem>.md` a `app_docs/<stem>.md`, kde `<stem>` je jméno souboru tasku (`TASK_STEMS`).
- Chování `factory task run --auto` popisuje `src/aifactory/run/queue.py`. Po úspěšném běhu s otevřeným PR spustí další `todo` task stejného stepu, potom modulu. Přeskočí tasky s otevřeným PR a tasky se závislostmi, které nejsou `done` v base. Když nic nezbývá, skončí `stop == "exhausted"`. JSON výstup: `data.run` a `data.pr` patří k prvnímu běhu, `data.chain = {runs: [{ok, run, pr, pr_error}], stop, waiting}`.
- `factory task add STEP TITLE --id ID --slug SLUG --writes P... --depends-on ID... --body TEXT` založí soubor `<step dir>/<ID>-<slug>.md` se `status: todo`, `## Zadání` a `## Běhy` a zvaliduje backlog. Moduly a stepy CLI zakládat neumí, jejich `index.md` se zapisují přímo.
- Konfigurace sandboxu: `levels: [module, step, task]`, `backlog_dir: backlog`, `merge_strategy: squash`. `.factory/worktrees/`, `.factory/data/` a `trace.db*` jsou gitignorované.
- `approve` přidá commit s `done`, mergne PR, dotáhne base z remote a odstraní worktree větve.

## Návrh ukázkového backlogu F2

Nové moduly `M03` a `M04` s novými zdrojovými soubory. Nekolidují s tasky šablony (M01, M02), takže F2 může běžet po ostatních scénářích i samostatně (`--only F2`).

Kontejnery (scénář je zapíše přímo do hlavního checkoutu):

| Soubor | Hlavička |
|---|---|
| `backlog/M03-units/index.md` | `id: M03`, `title: Unit conversions`, `workflow: simple-sdlc`, `source: src/sandbox/`, `target: src/sandbox/` a krátký popis |
| `backlog/M03-units/S01-temperature/index.md` | `id: M03-S01`, `title: Temperature` |
| `backlog/M04-stats/index.md` | `id: M04`, `title: Statistics`, `workflow: simple-sdlc`, `source`/`target` jako M03 |
| `backlog/M04-stats/S01-summary/index.md` | `id: M04-S01`, `title: Summary` |

Tasky (scénář je založí přes `factory task add`):

| ID | slug | title | writes | depends_on |
|---|---|---|---|---|
| M03-S01-T01 | `c-to-f` | Celsius to Fahrenheit | `src/sandbox/units.py`, `tests/test_units.py` | — |
| M03-S01-T02 | `f-to-c` | Fahrenheit to Celsius | `src/sandbox/units.py`, `tests/test_units.py` | M03-S01-T01 |
| M04-S01-T01 | `mean` | mean | `src/sandbox/stats.py`, `tests/test_stats.py` | — |
| M04-S01-T02 | `median` | median | `src/sandbox/stats.py`, `tests/test_stats.py` | M04-S01-T01 |
| M04-S01-T03 | `report` | mean in Fahrenheit | `src/sandbox/report.py`, `tests/test_report.py` | M03-S01-T01, M04-S01-T01 (vazba na jiný modul) |

Cesty tasků: `backlog/M03-units/S01-temperature/M03-S01-T01-c-to-f.md` a obdobně pro ostatní.

`--body` (anglicky jako šablona, srozumitelně i pro skutečný model na GitHubu). Příklad pro M03-S01-T01:

> Create `src/sandbox/units.py` with `c_to_f(celsius: float) -> float` (`celsius * 9 / 5 + 32`) and `tests/test_units.py` with a `CToFTest` (`c_to_f(0) == 32`, `c_to_f(100) == 212`). Done when `just test` passes. Constraints: standard library only, at most 40 changed lines.

Obdobně pro ostatní tasky:
- `f_to_c(fahrenheit)`, tedy `(f - 32) * 5 / 9`, a `FToCTest` připsaný do `tests/test_units.py`;
- `mean(values: list[float]) -> float`, pro prázdný seznam `ValueError`, a `MeanTest`;
- `median(values)`: prostřední prvek seřazeného seznamu, pro sudou délku průměr dvou prostředních, pro prázdný seznam `ValueError`, a `MedianTest`;
- `mean_fahrenheit(celsius: list[float]) -> float = c_to_f(mean(celsius))` v novém `src/sandbox/report.py` a `ReportTest` (`mean_fahrenheit([0, 100]) == 122`).

### Průběh scénáře

1. Založení: `index.md` kontejnerů, 5× `task add` v pořadí tabulky (závislost musí existovat dřív), `backlog check`. Pak commit jen `backlog/M03-units` a `backlog/M04-stats` a push do `origin <base>`.
2. Paralelně: `task run M03-S01-T01` a `task run M04-S01-T01` přes `haifa_async`. Každý task zakládá jiný nový soubor, takže PR spolu nekolidují.
3. `task approve M03-S01-T01` a `task approve M04-S01-T01`.
4. Auto-continue: `task run M04-S01-T02 --auto`. Proběhne M04-S01-T02 a řetěz pak spustí M04-S01-T03 ze stejného stepu, protože jeho závislosti jsou už `done` v base. Řetěz skončí `exhausted` (v modulu nic dalšího nezbývá). T03 se větví z base bez `median` a píše jiné soubory, takže nekoliduje.
5. `task run M03-S01-T02`, bez `--auto`.
6. `task approve` pro M04-S01-T02, M04-S01-T03 a M03-S01-T02.
7. Kontroly (níže).

## Změny po souborech

### 1. Nový `aifactory/validation/f2_backlog.py`: data backlogu a skripty falešných agentů

Bez importů z `validation.context`, `validation.scenarios` ani `validation.fake_scripts`, aby nevznikl cyklus. Obsah:

- `@dataclass(frozen=True) class F2Task: id, step, slug, title, writes: tuple[str, ...], depends_on: tuple[str, ...], body: str` s vlastnostmi `stem` (`f"{id}-{slug}"`) a `path` (`f"{STEP_DIRS[step]}/{stem}.md"`).
- `CONTAINERS: dict[str, str]`: relativní cesta `index.md` → text (4 soubory z tabulky, formát jako `template/backlog/M01-core/index.md`).
- `STEP_DIRS = {"M03-S01": "backlog/M03-units/S01-temperature", "M04-S01": "backlog/M04-stats/S01-summary"}`.
- `TASKS: tuple[F2Task, ...]`: 5 tasků v pořadí založení.
- `TASK_PATHS: dict[str, str]` a `TASK_STEMS: dict[str, str]` odvozené z `TASKS`.
- Konstanty ID podle role ve scénáři:
  - `PARALLEL = ("M03-S01-T01", "M04-S01-T01")`;
  - `AUTO_START = "M04-S01-T02"`;
  - `AUTO_CHAIN = ("M04-S01-T02", "M04-S01-T03")`;
  - `LAST = "M03-S01-T02"`;
  - `ALL = tuple(t.id for t in TASKS)`;
  - `BACKLOG_DIRS = ("backlog/M03-units", "backlog/M04-stats")`.
- Kódové fragmenty:
  - `UNITS` (write, docstring modulu plus `c_to_f`) a `UNITS_TEST` (write: `import unittest`, `from sandbox import units`, `CToFTest`);
  - `F_TO_C` a `F_TO_C_TEST` (append, začínají `"\n\n"`);
  - `STATS`, `STATS_TEST`, `MEDIAN`, `MEDIAN_TEST` obdobně;
  - `REPORT` (write, importuje `from sandbox.stats import mean` a `from sandbox.units import c_to_f`) a `REPORT_TEST` (write).
  Testy importují balíček jako šablona (`from sandbox import ...`). `tests/__init__.py` přidá `src/` do `sys.path`.
- `def edits_for(task_id) -> list[dict]`: edity buildu (formát `fake.apply_edits`: `write` a `append`).

`fake_scripts.py` tento modul importuje (směr `fake_scripts → f2_backlog` je bez cyklu).

### 2. `aifactory/validation/fake_scripts.py`

- `TASK_STEMS.update(f2_backlog.TASK_STEMS)`, nebo slovník rozšiř rovnou při definici. `_plan` a `_document` pak znají stem.
- `def _f2(task_id) -> dict`: `_script(task_id, <první položka writes>, [_build(f"added {title}", f2_backlog.edits_for(task_id), f"Add {slug}")])`. Revise tak jde na první soubor `writes`, stejně jako u ostatních tasků.
- `def chain_script(*scripts) -> dict`: sloučí fronty agentů v pořadí (`{"task": scripts[0]["task"], "agents": {agent: [*a, *b]}}`).
- Do `_SCRIPTS` přidej `(id, "happy")` pro všech 5 F2 tasků a `(AUTO_START, "auto")`, což je `chain_script(_f2("M04-S01-T02"), _f2("M04-S01-T03"))`. `_SCRIPTS` má dnes hodnoty typu `Callable[[], dict]`, proto použij `functools.partial` nebo lambdu a drž mypy strict.
- Rozšiř docstring modulu o jednu větu o F2.

### 3. `aifactory/validation/context.py`

- `TASK_PATHS.update(f2_backlog.TASK_PATHS)` (import `from validation import f2_backlog`).
- Přesuň `_base_suite` ze `scenarios.py` do `Context` jako `def base_suite(self, dirname: str = "resolve-check") -> tuple[bool, str]`. Tělo zůstane stejné, jen `ctx` → `self` a `path = self.workdir / dirname`. Import `subprocess` už v modulu je. V `scenarios.resolve` volej `ctx.base_suite()`. F2 potom volá `ctx.base_suite("f2-check")` bez importu ze `scenarios`.

### 4. Nový `aifactory/validation/f2.py`: scénář

`def f2(ctx: Context) -> ScenarioResult`. Scénář importuje `context`, `results`, `sandbox.git`, `f2_backlog` a `fake_scripts.REVIEW_RULE_MARKER` (jen pokud ho potřebuje), ne `scenarios`. Struktura:

```python
def f2(ctx):
    res = ScenarioResult("F2", ctx.remote)
    ctx.catch_up_base()
    if not _create_backlog(ctx, res):       # check "backlog_created"
        return res
    before_status = git(ctx.repo, "status", "--porcelain", "--untracked-files=all")
    runs: dict[str, dict] = {}               # task_id -> {"run": ..., "pr": ...}
    ...
```

**`_create_backlog(ctx, res) -> bool`**
- Když některý soubor z `TASK_PATHS` F2 v `origin/<base>` už existuje, vrať `res.inconclusive(...)` a skonči `False`. Ve fresh base se to nestane.
- Zapiš `CONTAINERS` do `ctx.repo` (`mkdir(parents=True)`).
- Pro každý `F2Task` zavolej `ctx.haifa("task", "add", t.step, t.title, "--id", t.id, "--slug", t.slug, "--writes", *t.writes, *(["--depends-on", *t.depends_on] if t.depends_on else []), "--body", t.body)`.
- Pak `check = ctx.haifa("backlog", "check")`.
- `git add -- backlog/M03-units backlog/M04-stats`, `git commit -q -m "F2: sample backlog (2 modules, 5 tasks)"`, `git push -q origin HEAD:<base>`.
- Check `backlog_created`: všechny `task add` jsou `ok`, `check.ok` platí a `ctx.status_in_base(id) == "todo"` pro všech 5. Detail je seznam `brief()` těch, které selhaly.
- Commit přidej do `res.commits`.

**Paralelní běhy** (vzor `scenarios.r2`):
- `pending = [ctx.haifa_async("task", "run", t, task=t) for t in PARALLEL]`, pak `cmds = [p.wait() ...]`.
- U každého `ctx.reference`, `ctx.add_pr` a záznam do `runs`.
- Checks:
  - `parallel_runs_ok`: všechny `ok`, `run.state == "succeeded"` a PR `url`;
  - `runs_overlapped`: overlap > 0 z `task_run.started_at/ended_at`, stejný výpočet jako R2. Do `measurements["overlap_s"]`;
  - `distinct_worktrees`.
- Když paralelní běhy selžou, vrať `res`.

**`_approve(ctx, task_id) -> Cmd`**: `ctx.haifa("task", "approve", task_id)`. Mimo local mode opakuj až 6× po 10 s, dokud `error_code == "merge_failed"` (stejně jako RESOLVE). `merge_sha` přidej do `res.commits`. Po approve zavolej `ctx.catch_up_base()`.

- Approve obou paralelních tasků. Check `parallel_approved`: oba `ok`.

**Auto-continue**:
- `cmd = ctx.run_task(AUTO_START, "--auto", variant="auto")`.
- `chain = cmd.payload.get("chain")`, pokud je dict, jinak `{}`. `chain_runs = chain.get("runs", [])`.
- Pro každou položku ber `item["run"]["task_id"]`, `item["run"]` a `item["pr"]`, ulož do `runs`, pak `ctx.reference(res, run_id)` a `ctx.add_pr`. Když `run.to_json()` nemá `task_id`, zjisti task přes `ctx.task_run(run_id)["task_id"]` (sloupec `task_runs`). Ověř si to čtením `src/aifactory/run/store.py`.
- Check `auto_chain`: `cmd.ok` platí, tasky řetězu jsou přesně `list(AUTO_CHAIN)`, každý má `ok`, `run.state == "succeeded"` a `pr.url`, a `chain.stop == "exhausted"`. Detail obsahuje tasky, stop a `waiting`.
- `measurements["auto_chain"] = {"tasks": [...], "stop": ..., "waiting": [...]}`.

**Poslední běh**: `ctx.run_task(LAST)`. Check `last_run_ok` jako `run_ok` v `_run_checks`, včetně PR.

- Approve pro `AUTO_CHAIN` a `LAST`. Check `all_approved` (všechny tři `ok`, detail `brief()`).

**Kontroly výsledku**:
- `five_prs_merged`: pro každý z `ALL` vezmi `branch` z `runs[t]["pr"]["branch"]` (fallback `run.branch`). Musí platit `len({branches}) == 5` a `ctx.task_pr(branch).get("state") == "merged"` u všech. Detail obsahuje stav PR podle tasku.
- `all_done_in_base`: pro každý task `header, text = ctx.task_in_base(t)` (po `catch_up_base`). Platí `header["status"] == "done"` a URL PR je v části za `## Běhy` (jako R3 `done_in_base_after_approve`). Detail obsahuje stav po tascích.
- `no_write_outside_worktree`:
  - `git status --porcelain --untracked-files=all` hlavního checkoutu se rovná `before_status`;
  - žádný F2 běh nemá event `ctx.events(run_id, "error", "permission_breach")`;
  - `git diff --name-only <base commit po založení backlogu>..origin/<base>` obsahuje jen povolené cesty. Povolené jsou `writes` pěti tasků, `specs/<stem>.md`, `app_docs/<stem>.md` a soubory tasků (`TASK_PATHS`, commit `done`). Seznam nečekaných souborů patří do detailu.
- `no_leftover_worktrees`: pro každý z 5 běhů `wt = run["worktree"]`. Musí platit `not Path(wt).exists()` a `wt` (ani `Path(wt).resolve()`) není v `git worktree list --porcelain`. Worktree jiných scénářů (B1, R4) se nepočítají. `measurements["leftover_worktrees"]` je seznam.
- `backlog_check_ok`: po `ctx.catch_up_base()` projde `ctx.haifa("backlog", "check")` s `ok` (a `code == 0`).
- Jen v local režimu `base_suite_green`: `ctx.base_suite("f2-check")`. Na githubu to vynech a zapiš `observe`.
- `measurements["run_seconds"] = {task: run_seconds(ctx.task_run(run_id))}`.
- `observations`:
  - „F2: 2 moduly, 5 tasků; paralelně M03-S01-T01 a M04-S01-T01; --auto od M04-S01-T02 spustil M04-S01-T03; approve bez approve review (D11)“;
  - v local režimu věta o falešném harnessu.

Scénář nesmí spadnout na `KeyError`, když běh selže. Chybějící hodnoty čti přes `.get` a kontrolu nech skončit `ok=False`. Po selhání kroku, na kterém závisí další kroky, vrať `res` (fail fast, výsledek je `failed`).

### 5. `aifactory/validation/scenarios.py`

- `from validation.f2 import f2` a na konec `ORDER` přidej `("F2", f2)`.
- `resolve` volá `ctx.base_suite()` a funkce `_base_suite` se smaže.
- Docstring modulu doplň o F2 (akceptace fáze F2, nezávisí na ostatních scénářích).

### 6. `aifactory/validation/results.py`

`RISKS["F2"] = "Akceptace F2: 5 úkolů z CLI (2 paralelně, auto-continue) až po mergnutý PR a done v base"`.

### 7. `aifactory/validation/runner.py`

Popis parseru: `"Validation scenarios R1-R5, R10, RESOLVE, B1 and F2 of aifactory."`.

### 8. `aifactory/validation/README.md`

- Úvod: doplň F2 (akceptační scénář fáze F2).
- `--only`: pořadí `R1, R10, R2, RESOLVE, R3, R4, R5, B1, F2`.
- Tabulka scénářů: řádek F2 popíše backlog (M03, M04, 5 tasků a vazby), paralelní dvojici, `--auto` řetěz, 5 approve a kontroly.
- „Kolik to stojí na githubu“: +5 běhů `simple-sdlc` (celkem 13). F2 nenechává otevřené PR ani worktree. Do úklidu doplň větve `factory/M03-*` a `factory/M04-*`.
- Výsledky: `F2.json`.

### 9. Testy

**`aifactory/tests/validation/test_validation_local.py`**
- `SCENARIOS = (..., "B1", "F2")`.
- `timeout=600` zvyš na `900` (5 běhů navíc).
- Nové asserty:
  ```python
  f2 = _checks(data["F2"])
  for name in ("backlog_created", "parallel_runs_ok", "runs_overlapped", "auto_chain",
               "five_prs_merged", "all_done_in_base", "no_write_outside_worktree",
               "no_leftover_worktrees", "backlog_check_ok", "base_suite_green"):
      assert f2[name] is True, name
  assert data["F2"]["measurements"]["overlap_s"] > 0
  assert data["F2"]["measurements"]["auto_chain"]["tasks"] == ["M04-S01-T02", "M04-S01-T03"]
  assert len(data["F2"]["evidence"]["run_ids"]) == 5
  ```

**Nový `aifactory/tests/validation/test_validation_f2.py`** (rychlý, bez `just validate`, bez modelu):
- Fixture `repo`: jako v `test_validation_template.py` (`sandbox.materialize(path, "main", "local")` + `commit_all`) v `tmp_path`.
- `test_f2_backlog_is_valid`: zapiš `f2_backlog.CONTAINERS` a pro každý task zavolej `run_json(capsys, ["task", "add", ..., "--repo", str(repo), "--json"])` (helper `cli_json.run_json`, stejné argv jako scénář). Pak `backlog check --json`: `ok is True` a `warnings == []`. Soubory tasků leží na `f2_backlog.TASK_PATHS` a `task list --json` ukáže 2 moduly navíc a 5 F2 tasků (M03-S01-T01 a M04-S01-T01 `ready`, ostatní `blocked`). Kdyby se tvar `task list` nehodil, stačí kontrola cest a `check`. Aby scénář i test sdílely stavbu argv, vytvoř ji ve `f2_backlog` funkcí `add_argv(task) -> list[str]`.
- `test_f2_fake_edits_keep_the_suite_green`: na kopii repa aplikuj přes `fake.apply_edits` edity builderů (build + revise) ze `script_for(t, "happy")` v pořadí merge: M03-S01-T01, M04-S01-T01, M04-S01-T02, M04-S01-T03, M03-S01-T02. Po každém tasku spusť `python3 -m unittest discover -s tests -t . -q` (cwd repo) s návratovým kódem 0. Zvlášť ověř M04-S01-T03 aplikovaný jen na M03-S01-T01 + M04-S01-T01 (větev bez `median`). Suite běží bez `HAIFA_VALIDATE_HIDDEN`.
- `test_f2_auto_script_chains_two_tasks`: `script_for("M04-S01-T02", "auto")` má 2 položky `planner`, 4 položky `builder` (build, revise, build, revise), reviewery `[False, True, False, True]` a 2 položky `documenter`. Každý revise je `revise_edit(<první writes>)`.
- `test_f2_scripts_revise_the_first_written_file`: pro všech 5 `("id","happy")` platí reviewer `[False, True]` a poslední builder je `revise_edit(writes[0])`.

**`aifactory/tests/validation/test_validation_unit.py`**: test, že `runner._selected("f2") == ["F2"]` a že `[n for n, _ in ORDER][-1] == "F2"`.

## Ověření

```bash
just test -k validation_f2          # rychlé testy F2
just validate --remote local --only F2 --keep-workdir   # jen F2, exit 0, F2.json passed
just validate --remote local        # všech 9 scénářů, exit 0, žádné failed
just test
just typecheck
just lint
```

Kontrola `F2.json`:
- `outcome: passed`;
- `evidence.run_ids` má 5 položek, `evidence.prs` 5 PR se `state: merged`;
- `measurements.auto_chain.stop == "exhausted"`.

## Rizika a poznámky pro buildera

- Běh `--auto` je jeden proces, a proto má jeden skript. Pořadí front musí odpovídat pořadí volání agentů (T02 celý, potom T03). Když řetěz spustí jiný task, fake vyhodí „no scripted entry left“ nebo zapíše špatné soubory. Zkontroluj, že M04-S01-T03 je v backlogu po T02 (pořadí souborů podle jména, `T02` < `T03`).
- `status_in_base` a `task_in_base` potřebují `TASK_PATHS` včetně F2 cest (bod 3).
- `task add ... --depends-on` má `nargs="+"`. Bez závislostí volbu vynech. `--writes` má `nargs="*"`.
- Commit backlogu přidávej jen s cestami `backlog/M03-units` a `backlog/M04-stats`. `git add -A` by mohl zachytit nečekané soubory.
- Po `task approve` dotahuje base aifactory. `ctx.catch_up_base()` je pojistka pro github.
- Když by lokální squash merge druhého paralelního PR hlásil `conflict`, soubory se překrývají. Zkontroluj `writes` a cesty spec/doc (mají být různé podle stemu).
- Nesahej na `justfile` (komentář u receptu `validate` uvádí jen seznam scénářů, nevadí).
