# Plán v2: zrychlení testové sady prototypu — dotažení na limit 5 s na test

Navazuje na `specs/e1f8b8ce_test-suite-speedup.md` (v1). Kroky 1–3 z v1 jsou **už v pracovním stromu**
(necommitnuté). Tento plán je ponechává a řeší jediné, co ještě nesplňuje zadání.

## Kritéria hotovo (beze změny)

- `just test` projde a celý doběhne do **120 s** (`time just test`).
- Žádný záznam v `just test --durations=10` (setup/call/teardown) není delší než **5 s**.
- **299 testů**, 0 skipped/xfail, žádná aserce odstraněná ani změkčená.
- Beze změn ve `vendor/` a v `prototype/src/haifa_proto/` (čekání tam žádné není, viz v1). Výchozí chování CLI se nemění.

## Stav teď (změřeno 3× po sobě na i5-5350U, 2 fyzická jádra)

Hotovo v pracovním stromu (`git diff` na `prototype/pyproject.toml`, `prototype/uv.lock`, `prototype/tests/conftest.py`, `prototype/tests/gh_fake.py`):
- `conftest.py::_fast_test_env` (session, autouse): symlink na skutečný git místo xcrun shimu `/usr/bin/git`;
  `GIT_CONFIG_GLOBAL` → vygenerovaný config, který includuje uživatelův `~/.gitconfig` / XDG config a přidává
  `maintenance.auto=false`, `gc.auto=0`, `receive.autogc=false`. (Odchylka od v1: místo `GIT_CONFIG_COUNT`,
  protože git ho u přijímací strany lokálního push maže. Je to v pořádku, nech to tak.) Dále zapíše
  a jednou naprázdno spustí sdílený fake `gh`.
- `gh_fake.py`: jeden skript ve stabilním adresáři `$TMPDIR/haifa-fake-gh-<uid>-<hash>` (přežije i mezi
  sessions, takže kontrola macOS při prvním spuštění proběhne jen jednou). Stav testu je v `HAIFA_FAKE_GH_STATE`,
  zápis je atomický přes `os.replace`.
- `pyproject.toml`: dev deps `pytest-xdist`, `psutil`; `addopts = ["-n", "auto", "--dist", "loadfile"]`.

Výsledky:
- `time just test`: **299 passed za 64–73 s** (real 66–75 s) ✅
- `just lint`, `just typecheck` projdou, `--collect-only` = 299 ✅; fork testy prošly ve všech 3 bězích ✅
- **Nejhorší záznam: `test_auto_continue.py::test_dependent_task_skipped_until_approve` call = 5,08 / 5,21 / 4,92 s** ❌
  Další nejpomalejší jsou do 4,4 s (`test_three_independent_tasks_run_in_order`, `test_task_that_cannot_start_is_reported`,
  `test_auto_flag_continues`, `test_cli_auto_json`). Měření kolísá o ±20 %, takže i ty jsou blízko hranice.

Rozbor nejhoršího testu (sériově, `-n0`): call 4,4 s, z toho ~3,5 s podprocesy (179 volání): 7× `git push`
(~1,0 s, z toho 2 z testových helperů), 13× `worktree`, 32× `rev-parse`, 24× `cat-file`, 8× `archive` … Téměř vše
je v `src/`/`vendor/` a je to skutečná práce (4× `run_task` + `approve_task`), žádné čekání. Proces v Pythonu
se spouští ~6 ms, git ~11 ms na exec; tady už velká rezerva není. Pod xdist (2 workery) je test o ~10–15 % pomalejší.
Setup fáze těžkých testů trvá ~0,8 s (`engine_env` + `make_task_repo` + `add_bare_remote`: ~12 volání gitu vč. push).

**Cíl v2:** u každého těžkého testu ubrat ≥ 20 % (≈ 0,5–1 s) skutečné práce v testové infrastruktuře, aby
nejhorší záznam měl s rezervou < 5 s i při paralelním běhu. Nejde jen o přesun času mezi fázemi.

## Kroky

### 1. Zahřát importy jednou za session — `prototype/tests/conftest.py`

První test v každém workeru teď platí ~0,6 s za import vendoru a `haifa_proto` (změřeno: moduly `haifa_proto` 0,26 s,
engine moduly 0,1 s, `harness.install()` poprvé 0,2 s) a jsou to právě těžké testy (`test_three_independent…` je v souboru první).
Do `_fast_test_env` (nebo do samostatné session autouse fixtury) přidej jen **importy**:
`import haifa_proto.run, .queue, .review, .workflow, .web, .cli` a
`engine.load_engine_module(m)` pro `data_types`, `agents`, `runner`, `permissions`, `git_helper`, `tracer`, `session`, `utils`
(uprav seznam podle toho, co skutečně existuje ve `vendor/sssf/templates/adws/adw_modules/`).
**Nevolej `harness.install()`**: mění `agents.INTERFACES` a testy registru mají dostat čistý stav jako dnes.
`test_engine_import.py` se tím neoslabí, protože kontroluje jen `__file__` načtených modulů.

### 2. Šablony gitových repozitářů pro fixtury — `prototype/tests/workflow_fakes.py`, `prototype/tests/task_repo.py`, `prototype/tests/conftest.py`

Stejný obsah repa se dnes v každém testu staví znovu přes `git init/config/add/commit`. Místo toho ho postav
**jednou za worker** a do testu jen kopíruj (`shutil.copytree(..., symlinks=True)`, malé repo ~100 souborů ≈ desítky ms).

a) **Adresář šablon:** session fixtura (např. `repo_templates`) vytvoří `tmp_path_factory.mktemp("repo-templates")`
   a uloží cestu do modulové proměnné (stejný vzor jako `gh_fake._shared_bin`), aby ji helpery viděly bez nového
   parametru. Helpery musí fungovat i bez fixtury (fallback na dnešní cestu), aby šly volat samostatně.

b) **`make_engine_env`:** git část (`init`, 2× `config`, `README.md`, `add`, `commit`) nahraď kopií šablony
   „engine repo“ do `tmp_path / "repo"`. Šablona vznikne líně: poprvé proveď přesně dnešní příkazy v adresáři šablon.
   Zbytek funkce (prompts, `sssf.config.yaml` s absolutními cestami, harness fakes, signály) nech per-test.

c) **`make_task_repo(env)`:** pokud je `env.repo` pořád nedotčený klon engine šablony, nahraď ho kopií šablony
   „task repo“ (= engine šablona + dnešní obsah `make_task_repo` + commit). Šablonu opět postav líně dnešním kódem.
   Jak poznat „nedotčený“: nejjednodušší je v `make_engine_env` nastavit na `EngineEnv` příznak (např. `pristine=True`)
   a v helperech, které repo mění, ho neřešit, protože všichni volající (`grep make_task_repo tests/`) volají
   `make_task_repo` hned po `engine_env`. **Ověř to u všech 7 souborů** (test_auto_continue, test_cli_backlog,
   test_cli_task, test_pr_flow_github, test_pr_flow_local, test_task_run, test_web). Kde ne, použij dnešní cestu.
   Kopii dělej jako: smaž obsah `env.repo` → `copytree(template, env.repo, dirs_exist_ok=True, symlinks=True)`;
   `monkeypatch.chdir(repo)` z `make_engine_env` platí dál, protože cesta se nemění.

d) **`add_bare_remote(repo, tmp_path)`:** šablona „bare remote s pushnutým `main`“ je kopie bare repa, které vzniklo
   ze šablony task repa. Po kopii nastav v `repo/.git/config` URL `origin` na nové `tmp_path / "remote.git"`
   a nastav tracking `branch.main.remote/merge`, tedy totéž co `push -u`. Buď jedním `git remote set-url` +
   `git config` (2 volání místo init+remote add+push), nebo přímo úpravou config souboru. Musí sedět i
   `refs/remotes/origin/main` v lokálním repu: zkopíruj ho ze šablony (je součástí `.git`) a ověř
   `git rev-parse origin/main == main`. Šablona remote platí jen tehdy, když `main` v repu je shodný se šablonou
   (task repo hned po `make_task_repo`). Jinak (např. po `set_config`) použij dnešní cestu. Kontroluj SHA `main`
   proti uložené SHA šablony (1× `rev-parse`).

e) **Neměň** `set_config`, `with_agents_config`: `sssf.config.yaml` obsahuje absolutní per-test cesty,
   takže commit musí vzniknout v testu.

f) Commity v šablonách mají pevný obsah; SHA budou mezi testy stejné. Ověř grepem, že žádný test nespoléhá
   na unikátní SHA nebo čas fixture commitu (neměl by, protože porovnává relativně: `main_before` atd.).

### 3. Šablony pro `_setup` v `test_auto_continue.py` (volitelné, jen pokud po krocích 1–2 nejhorší záznam > 4,5 s)

`_setup(repo, step_auto, t02_depends, keep_s02)` v call fázi každého těžkého testu dělá `add` + `commit` + `push`
(~0,4 s). Stejný mechanismus jako 2c/2d: klíč `(step_auto, t02_depends, keep_s02)` → líně postavená šablona
repa **i** remote. `_setup` pak jen nahradí oba adresáře kopií a přepíše URL `origin`. Chování a výsledný stav
(soubory, commit „chain backlog“, `origin/main`) musí být stejné jako dnes; ověř porovnáním
`git log --format=%s main`, `git ls-tree -r main` a `git rev-parse origin/main` před a po změně (jednorázově, ručně).
`test_select_next_rules` `_setup` nevolá, ten se nemění.

### 4. Co NEdělat

- Nesahat do `src/`, `vendor/`, výchozích hodnot ani timeoutů. Nic neskipovat, neslučovat, neoslabovat.
- Nepřesouvat práci z call do setup fáze jen kvůli metrice. Šablony jsou v pořádku, protože skutečně ubírají
  git volání.
- Neměnit `--dist loadfile` na `load`: v1 zjistila, že fork testy (`test_parallel_runs_of_different_tasks`,
  `test_concurrent_start_of_same_task_one_refused`) pod `load` občas visí.
- Nevracet `-n` na počet logických jader (4). Na tomto stroji testy zpomalí na 10–15 s.

## Ověření (posuzuj podle exit statusu)

1. `time just test --durations=15` **3× po sobě**: pokaždé exit 0, `299 passed`, žádné skipped, real < 120 s
   a **žádný řádek > 5,00 s**. Cíl s rezervou: nejhorší ≤ 4,5 s. V reportu uveď všechny tři nejhorší hodnoty.
2. `just test -n0 --durations=10`: sériový běh také projde.
3. `cd prototype && uv run pytest --collect-only -q | tail -1` → `299 tests collected`.
4. `just lint` a `just typecheck` projdou (nové fixtury/helpery typuj, mypy je strict i pro `tests/`).
5. `git status --short` ukazuje změny jen v `prototype/tests/*`, `prototype/pyproject.toml`, `prototype/uv.lock`
   (a spec soubory). Nic ve `vendor/` ani `prototype/src/`.

Pozn.: GNU `timeout` na tomto macOS není, na měření použij `time`. V `/tmp` leží cizí `bisect.py`, který zastíní
stdlib, pokud se Python spustí s cwd `/tmp`.
