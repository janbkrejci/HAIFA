# Plán: zrychlení testové sady `aifactory` (backlog 2.20) — limity 180 s / 10 s

Tato verze nahrazuje `specs/1a545cb0_aifactory-test-speedup.md`. Zadání se změnilo:
celá sada do **180 s** (dřív 120 s) a žádný test nad **10 s** (dřív 5 s). Postup je stejný, s volnějšími limity
odpadá část rozdělování validace (viz krok 4f) a krok 3 je volitelný.

## Zadání (shrnutí)

`just test` (= `cd aifactory && uv run pytest "$@"`) musí projít a doběhnout do **180 s**, žádný záznam
v `--durations=15` nesmí být delší než **10 s**, počet testů nesmí klesnout (dnes **673**), nic
přeskočeného ani oslabeného. `vendor/` a `prototype/` se nemění. Výchozí chování CLI a běhů se nemění;
kratší čekání jen parametrem/konfigurací. Do `aifactory/src/aifactory/` sahat jen tam, kde pomalost
způsobuje čekání v kódu (průzkum žádné takové místo nenašel, viz níže → **`src/` neměnit**).

## Co ukázalo měření (2026-09-28, stroj: 2 fyzická / 4 logická jádra, load avg 5–9)

Sériově: **673 passed za 703 s**. Nejpomalejší:

| test | čas |
|---|---|
| `tests/validation/test_validation_local.py::test_validate_local` (všech 9 scénářů přes `just validate`) | 186,7 s |
| `tests/validation/test_validation_roster.py::test_validate_local_pi_haiku_roster` (R1,R10) | 26,1 s |
| `tests/run/test_auto_continue.py::*` | 3–14 s (8 testů > 5 s) |
| `tests/run/test_task_resolve.py::*` | 7–12 s (7 testů > 5 s) |
| `tests/validation/test_validation_prompt_paths.py::*[spec_path]` / `[adw_id]` | 12,9 s / 5,3 s |
| `tests/run/test_task_pr_flow.py`, `tests/run/test_backlog_sync.py` | 3–9 s |

Příčiny:

1. **Git přes xcrun shim.** `/usr/bin/git` na macOS je shim, ~44 ms/volání; skutečný binár
   (`xcrun --find git` → `/Library/Developer/CommandLineTools/usr/bin/git`) ~10 ms. Profil dvou testů
   `tests/run`: 407 subprocesů, z toho 100 % git, a subprocesy tvoří ~85 % času testu. Jen s přímým
   gitem v PATH: `test_dependent_task_skipped_until_approve` 13,8 s → 5,8 s (pod zátěží 8),
   scénář R1 12,7 s → 8,6 s, F2 87,7 s → 44,4 s.
2. **Žádná paralelizace** (není pytest-xdist).
3. **Validace jako jeden obří test.** `test_validate_local` spouští `just validate --remote local`
   se všemi scénáři v jednom sandboxu. Scénáře R1→R10→R2→RESOLVE→R3→R4 na sobě závisí přes
   `ctx.state` (docstring `validation/scenarios.py`; RESOLVE samostatně = `inconclusive`), R5, B1 a F2
   jsou nezávislé. F2 = 5 běhů úkolů + `--auto` řetěz + 5 approve, desítky sekund i s rychlým gitem.
4. Každý CLI příkaz validace je nový proces `python -m validation.worker` (~0,3–0,6 s start).
5. V `src/aifactory` žádné zbytečné čekání pro testy: `sleep` v providerech je už injektovaný
   (`sleep=`/`delay=` parametry, testy je používají), `sleep(10)` ve validaci běží jen v GitHub režimu
   (`range(0 if ctx.local else 6)`), `_ensure_wal` spí jen při zamčené DB. **`src/` se nemění.**

## Kroky

### Krok 1 — sdílené zrychlení prostředí: `aifactory/tests/conftest.py` (nový, kořenový)

Vzor: `prototype/tests/conftest.py` (jen číst, neměnit). Session-scoped autouse fixture
`_fast_test_env(tmp_path_factory)` přes `pytest.MonkeyPatch.context()`:

- **Přímý git:** funkce `_direct_git() -> str | None` — jen `sys.platform == "darwin"`, jen když
  `os.path.realpath(shutil.which("git")) == "/usr/bin/git"`; pak `xcrun --find git`, ověřit že
  existuje, je spustitelný a není to znovu `/usr/bin/git`. Při úspěchu vytvořit
  `tmp_path_factory.mktemp("gitbin")/git` jako symlink na skutečný git a předřadit adresář do `PATH`
  (`mp.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")`). Jinde (Linux) nic.
- **Tichý git config:** `GIT_CONFIG_GLOBAL` → soubor v `mktemp("gitcfg")`, který `[include]` načte
  původní globální config (hodnota `GIT_CONFIG_GLOBAL`, jinak `$XDG_CONFIG_HOME/git/config` a
  `~/.gitconfig`) a přidá `[maintenance] auto = false`, `[gc] auto = 0`, `[receive] autogc = false`.
  (Přes `GIT_CONFIG_GLOBAL`, ne `GIT_CONFIG_COUNT` — ten git maže pro přijímající stranu lokálního push.)
- **Předehřátí falešných CLI:** `gh_fake.write_fake_gh(gh_fake.shared_bin_dir())` a
  `az_fake.write_fake_az(az_fake.shared_bin_dir())` a jednou každý spustit (`--version`) se
  stavovým adresářem obsahujícím `responses.json` = `{}` (podívej se na proměnné, které skripty čtou:
  `AIFACTORY_FAKE_GH_STATE`, obdobně pro az v `tests/providers/az_fake.py`). macOS platí první exec
  nového souboru; zaplatí se jednou v session. Moduly jsou v `tests/providers/` — importuj je tak,
  jak to dělají stávající testy (pythonpath je `["tests", "."]`, tj. `from providers import gh_fake`
  nebo přidej cestu; zvol variantu, která projde mypy i ruff).
- **Zahřátí importů:** `importlib.import_module` pro `aifactory.cli`, `aifactory.run`,
  `aifactory.workflow`, `aifactory.engine.data_types`, `aifactory.engine.agents`,
  `aifactory.engine.runner` (jen importy, žádná registrace/instalace harnessů).

Proměnné prostředí se dědí i do subprocesů (validační workery, `just validate`), takže zrychlení
platí i tam. Testy, které si nastavují `PATH` celé samy, prostě jedou přes shim — to je v pořádku.

### Krok 2 — paralelní běh: pytest-xdist

- `cd aifactory && uv add --dev pytest-xdist` (aktualizuje `pyproject.toml` a `uv.lock`). **psutil
  nepřidávat.**
- `[tool.pytest.ini_options]`: `addopts = "-n logical --dist loadgroup"`. `logical` = počet
  logických CPU (4); testy jsou vázané na spouštění procesů, ne na CPU. `loadgroup` rozkládá jako
  `load`, ale testy s `@pytest.mark.xdist_group(name=...)` drží na jednom workeru v pořadí souboru
  (potřeba pro krok 4).
- Sériový běh zůstává možný: `just test -n0`.
- Ověř, že žádný test nesdílí stav přes pevné cesty mimo `tmp_path` (sdílený `shared_bin_dir` fake
  gh/az už zapisuje atomicky přes `os.replace`). Pokud nějaký test padá jen paralelně, oprav izolaci
  testu (vlastní `tmp_path`, `monkeypatch`), ne přeskočením.

### Krok 3 — šablony repozitářů (`aifactory/tests/repo_templates.py`, nový) — VOLITELNÝ

Dělej jen tehdy, když po krocích 1, 2 a 4 celková doba nebo některý test z `tests/*` limity stále
překračuje.

Hodně testů staví stejný git repozitář od nuly (init, config, zápis souborů, commit = desítky volání
gitu). API:

```python
def enable(directory: Path) -> None: ...            # volá session fixture z kroku 1
def build(path: Path, key: str, make: Callable[[Path], object]) -> None:
    """Postav repo `make(tpl)` jednou za session (per worker) do directory/key a pak
    shutil.copytree(tpl, path, symlinks=True). Bez enable() zavolá make(path) přímo."""
```

Použij ve stavitelích, kde repo nemá remote ani worktree ani absolutní cesty v `.git/config`
(zkontroluj `git -C <tpl> config --local --list` a `git worktree list`):
`tests/run/run_repo.py::make_run_repo` (klíč = `f"run-{harness}"`, zachovat návratovou hodnotu
`path.resolve()`), `tests/engine/engine_fakes.py::build_repo`, stavitel repa v
`tests/workflow/workflow_fakes.py`, `tests/config/config_repo.py`, `tests/providers/provider_repo.py`,
fixtura `repo` v `tests/validation/test_validation_f2.py`. Obsah vzniklého repa musí být
bajtově stejný jako při přímé stavbě (šablona = stejná funkce). Pokud stavitel přijímá parametry,
jsou součástí klíče. Kde je repo s remote (bare `origin`), šablonu nepoužívej, pokud nejde po
zkopírování jedním `git remote set-url` opravit cestu — jinak ji tam nepoužívej vůbec.
Po tomto kroku změř; nepřinese-li stavitel měřitelný rozdíl, klidně ho vynech.

### Krok 4 — validace rozdělená na samostatné testy

**4a. Refaktor bez změny chování v `aifactory/validation/runner.py`:** vytáhni z `main()` dvě
funkce a `main()` je bude volat (výstupy a exit kódy beze změny):

- `make_context(remote, sandbox, workdir, owned, r5_samples) -> Context` — dnešní stavba `Context`
  (`hidden=write_hidden(workdir)`, `harnesses=step_harnesses(sandbox.repo)`).
- `write_results(ctx, out, done) -> None` — `out.mkdir`, `copy_trace(ctx, out)`, oprava
  `trace_sessions`/`trace_files` přes `_existing` a `write_result` pro každý výsledek.

**4b. Rozdělení F2 na fáze v `aifactory/validation/f2.py`:** dnešní `f2()` má přirozené hranice.
Zaveď `@dataclass class F2Run: res, runs, base_sha: str | None = None, before_status: str = ""`
a `F2_STAGES: tuple[tuple[str, Callable[[Context, F2Run], bool]], ...]` v pořadí:
`backlog` (catch_up_base + `_create_backlog` + dvě `res.observe` + `before_status`),
`parallel`, `approve_parallel`, `auto_chain`, `last_run` (run + `_record` + `last_run_ok`),
`approve_rest`, `final` (`_final_checks`, vrací True). `f2(ctx)` vytvoří `F2Run`, projde fáze a
**skončí při prvním `False`** — přesně jako dnes. Texty, checky a pořadí volání beze změny.

**4c. Testovací pomocník `aifactory/tests/validation/local_validation.py` (nový):**

```python
class LocalValidation:
    """Jeden lokální validační běh rozdělený do testů: sandbox, Context a výsledky na disku."""
    def __init__(self, root: Path, roster: Path | None = None) -> None
        # workdir = root/"work", out = root/"results"; setup_local(workdir, roster),
        # runner.make_context("local", sandbox, workdir, Owned(), r5_samples=3)
    def scenario(self, name: str) -> dict[str, Any]
        # pro řetěz R1,R10,R2,RESOLVE,R3,R4: nejdřív spusť všechny DŘÍVĚJŠÍ scénáře řetězu
        # (v pořadí ORDER), které ještě neběžely — test puštěný samostatně tak funguje;
        # pak runner.run_scenarios(ctx, [name], out), runner.write_results(...) a vrať
        # načtený out/NAME.json
    def f2_stage(self, stage: str) -> F2Run
        # obdobně: doběhni předchozí fáze F2_STAGES, které neběžely, pak tuto;
        # po poslední fázi res.finish() + write_results a vrať data F2.json
```

Prostředí jako v dnešních testech (tripwire pro `AIFACTORY_GH`, `CODEX_PATH`, `CLAUDE_CODE_PATH`,
`PI_PATH`, `UV_NO_SYNC=1`, odebrané `HAIFA_SANDBOX_REPO`, `HAIFA_VALIDATE_FAKE`,
`HAIFA_VALIDATE_HIDDEN`) nastav přes `pytest.MonkeyPatch.context()` ve fixture — `Context._spawn`
kopíruje `os.environ`, takže tripwire dostanou i workery. Fixture ponechá `@skipif(just missing)`
jako dnes (sandbox spouští `just test`).

**4d. `tests/validation/test_validation_local.py` přepsat na:**

- Modul-scoped fixture `chain` (`LocalValidation(tmp_path_factory.mktemp(...))`) a testy
  `test_r1`, `test_r10`, `test_r2`, `test_resolve`, `test_r3`, `test_r4` — všechny
  `@pytest.mark.xdist_group(name="validation-chain")`, v tomto pořadí v souboru.
- `test_r5`, `test_b1` — každý s vlastním `LocalValidation(tmp_path)`.
- F2: modul-scoped fixture `f2` + testy po fázích (F2 trvá i s rychlým gitem 44 s pod zátěží,
  takže dělení na fáze je potřeba i při limitu 10 s; jednotlivé fáze vycházejí ~2–6 s) (`test_f2_backlog`, `test_f2_parallel`, …,
  `test_f2_final`) v `xdist_group(name="validation-f2")`.
- Jeden **end-to-end test přes `just validate`**: `just validate --remote local --only R5
  --results-dir … --workdir …` — kontroluje, co dnes kontroluje souhrn: exit 0, jeden adresář
  `local-*`, workdir smazaný, `summary["remote"] == "local"`, `summary["results"] == {"R5": "passed"}`,
  `workdir_kept is False`, `out/"logs"` existuje, trace soubory z evidence existují, tripwire nespuštěn.
- **Každá dnešní aserce se přenese.** Per-scénář: `outcome == "passed"`, `remote == "local"`,
  `run_ids`/`trace.sessions` (kromě R5), existence souborů trace. Scénářové: R2 `overlap_s > 0`
  a `second_reports_conflict`; R10 `test_failed_first`, `hidden_test_failed_first`,
  `repair_rounds >= 1`; R1/R10 review/revise checky a `revise_1` ve fázích R1; RESOLVE
  `both_prs_merged`, `resolve_phase_ran`; B1 `write_reverted`, `run_failed`; F2 všechny
  vyjmenované checky, `overlap_s`, `auto_chain` (tasks, stop), 5 `run_ids`, 5× `merged`.
  Checky F2 přiřaď k testu fáze, která je vytvoří; `final` navíc ověří `outcome == "passed"` a celý
  seznam. Na konci každého testu `assert not marker.exists()`.

**4e. `tests/validation/test_validation_roster.py::test_validate_local_pi_haiku_roster`** stejně:
E2E `just validate --remote local --roster PI_HAIKU --only R5` pro aserce souhrnu (`roster`,
`harness_per_step["build"] == "pi"`, žádný `codex`), a R1/R10 s rosterem přes `LocalValidation(…,
roster=resolve_roster(PI_HAIKU))` ve dvou testech (`xdist_group`), každý s dnešními asercemi
(`outcome == "inconclusive"`, žádný failed check, `revise_ran`/`review_2_approved`, pozorování
„codex“, chybějící `harness_per_phase`/`fix_ran_on_codex`). Ověř v kódu scénářů, zda R10 s rosterem
potřebuje R1 — pokud ne, můžou být testy nezávislé.

**4f. Rozhodovací pravidlo pro zbylé dlouhé testy validace:** po krocích 1–4e změř
`just test --durations=30`. Scénář řetězu nad 10 s (kandidát podle měření: R3, 46 s pod load 64,
případně R2/RESOLVE)
rozděl stejným vzorem jako F2 (tuple fází + scénářová funkce, která je iteruje a končí stejně jako
dnes) na hranicích mezi CLI příkazy. **Jeden jediný CLI příkaz se dělit nedá** (např. `task run --auto`
se dvěma úkoly ve fázi `auto_chain`): když sám přesáhne 10 s na klidném stroji, nezkracuj workflow,
nesnižuj počet úkolů ani neměň aserce — uveď test s naměřenými časy v reportu jako zbývající
odchylku.

### Krok 5 — zbylé pomalé testy `tests/run/*`

Po krocích 1–3 změř. Testy `test_auto_continue`, `test_task_resolve`, `test_task_pr_flow`,
`test_backlog_sync` jsou z ~85 % volání gitu, přímý git je má stáhnout ~2–2,5×. Pokud některý
zůstane nad 10 s: nejdřív šablona repa pro jeho fixturu (krok 3, u repa s bare remote jen s opravou
`remote set-url`), jinak ho **rozděl** na víc testů jen tam, kde testuje víc nezávislých věcí za
sebou. Nesnižovat počet běhů/fází, které test ověřuje, a neměnit aserce.

## Co NEdělat

- Neměnit `vendor/`, `prototype/`, `aifactory/src/` (žádné výchozí hodnoty `UNKNOWN_DELAY` apod.).
- Nepřidávat `skip`, `xfail`, `-k` vyřazení, nesnižovat `timeout` subprocesů jako „zrychlení“.
- Neměnit chování `just validate` (výstupní soubory, pořadí scénářů, exit kódy) — refaktor 4a/4b
  je jen přeskupení kódu.
- Nehonit časy naměřené pod cizí zátěží.

## Ověření (posuzuj podle exit statusu)

1. **Klidný stroj:** před měřením `uptime`; při 1min load avg > 4 čekej (smyčka `sleep 10`, max
   10 min). Když neklesne, zapiš load avg a časy do reportu.
2. `time just test --durations=15` **3×**: exit 0, `passed ≥ 673`, 0 skipped/xfailed,
   real < 180 s, žádný řádek > 10,00 s. Ke každému běhu zapiš load avg, real a nejhorší test.
3. `just test -n0 -q`: sériově projde (čas není kritérium).
4. `cd aifactory && uv run pytest --collect-only -q | tail -1` ≥ 673.
5. `just validate --remote local` (celý, bez pytestu) projde se všemi 9 scénáři `passed` —
   důkaz, že refaktor 4a/4b nezměnil chování.
6. `just lint` a `just typecheck` projdou.
7. `git diff --quiet -- vendor prototype aifactory/src` → exit 0.
8. `git diff` testů: žádná aserce neodebrána ani změkčená (jen přesunutá do nových testů).

## Soubory

- nové: `aifactory/tests/conftest.py`, `aifactory/tests/repo_templates.py`,
  `aifactory/tests/validation/local_validation.py`
- měněné: `aifactory/pyproject.toml`, `aifactory/uv.lock`, `aifactory/validation/runner.py`,
  `aifactory/validation/f2.py`, případně `aifactory/validation/scenarios.py` (jen krok 4f),
  `aifactory/tests/validation/test_validation_local.py`,
  `aifactory/tests/validation/test_validation_roster.py`, stavitelé repozitářů v `tests/run`,
  `tests/engine`, `tests/workflow`, `tests/config`, `tests/providers`,
  `tests/validation/test_validation_f2.py`
