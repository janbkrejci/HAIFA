# Plán: zrychlení testové sady prototypu (`just test` < 120 s)

## Cíl a kritéria hotovo

- `just test` (= `cd prototype && uv run pytest "$@"`) projde a celý doběhne do **120 s** (měřit `time just test`).
- Žádný záznam v `just test --durations=10` není delší než **5 s** (setup, call i teardown).
- Pořád **299 testů**, 0 přeskočených (`skipped`), žádná aserce odstraněná ani změkčená.
- Beze změn ve `vendor/`. Beze změny výchozího chování CLI a běhů: vše níže je **jen testová infrastruktura**
  (`prototype/tests/`, `prototype/pyproject.toml`, `prototype/uv.lock`). Do `prototype/src/haifa_proto/` se
  **nesahá** — viz „Zjištění“: v kódu žádné čekání (sleep/polling) není.

## Zjištění z měření (stroj: i5-5350U, 2 fyzická jádra / 4 vlákna, macOS 12, Apple git 2.37.1)

Výchozí stav: 299 passed za 407–477 s. **349 s z 407 s tvoří podprocesy** (trace přes obalený `subprocess.run`):

| příčina | měření | dopad |
|---|---|---|
| `git` na PATH je `/usr/bin/git` = xcrun shim; každé volání hledá skutečný nástroj | `git rev-parse` z Pythonu: **57 ms** přes shim vs **18 ms** přímo na `/Library/Developer/CommandLineTools/usr/bin/git` | 3 834 volání gitu za běh (1 464× rev-parse, 342× cat-file, 244× commit, 235× worktree, 84× push …) |
| git po `commit`/`merge`/`push` spouští `git maintenance run --auto` / `gc --auto` / `receive.autogc` | 20 prázdných commitů: 1,39 s → **0,50 s** s `maintenance.auto=false`, `gc.auto=0` | ~300 commit/merge + 84 push |
| fake `gh` (`tests/gh_fake.py`) se generuje jako **nový spustitelný soubor v každém testu**; macOS (syspolicyd/XProtect) kontroluje první spuštění každého nového spustitelného souboru | první exec nového skriptu **~1,8 s**, další 0,04 s; při paralelním běhu až 30 s | 39 volání `gh` = 60 s; `test_providers_github.py` (16 testů) ~31 s |
| v `src/` ani v používaných částech vendoru nic nečeká | `grep sleep/poll` v `src/haifa_proto` = nic; jediné `time.sleep` ve vendoru je v `agent_pi.py` (v testech nahrazen fake harnessem) | — |

Ověřené zkoušky (nic z toho zatím není v repu):
- jen přímý git: sériově 275 testů (bez gh souborů) 150 s; celá sada 196 s; nejhorší test 6,35 s.
- přímý git + `pytest-xdist -n 2 --dist loadfile`, bez gh souborů: **275 passed za 94 s**, nejhorší 7,0 s.
- `-n 4` (logická jádra) je na tomto stroji horší: jednotlivé testy 10–15 s.
- `--dist load` (výchozí xdist): 2 ze 3 běhů spadl `test_auto_continue.py::test_parallel_runs_of_different_tasks`
  (`BrokenBarrierError` / `database is locked`, test visí 60 s na bariéře). Samostatně, sériově i pod zátěží
  CPU prochází; s `--dist loadfile` prošel. Příčina nedohledána (viz krok 5).

Odhad po všech krocích: sériově ~130 s, s 2 workery ~70–85 s; nejtěžší testy (3–4 běhy `run_task` v jednom testu)
~4–5 s. **Limit 5 s na test je nejtěsnější místo plánu** — proto měř po každém kroku.

## Kroky

### 1. Hermetické a rychlé git prostředí pro celou session — `prototype/tests/conftest.py`

Přidej session-scoped **autouse** fixturu (např. `_fast_git`), která pomocí `pytest.MonkeyPatch.context()`
(obnoví env na konci session) nastaví:

a) **Obejití xcrun shimu (jen macOS, jinak no-op):**
```python
def _direct_git() -> str | None:
    if sys.platform != "darwin":
        return None
    found = shutil.which("git")
    if found is None or os.path.realpath(found) != "/usr/bin/git":
        return None
    probe = subprocess.run(["xcrun", "--find", "git"], capture_output=True, text=True, check=False)
    real = probe.stdout.strip()
    if probe.returncode != 0 or not real or not os.access(real, os.X_OK):
        return None
    if os.path.realpath(real) == "/usr/bin/git":
        return None
    return real
```
Když vrátí cestu: `bin_dir = tmp_path_factory.mktemp("gitbin")`, `(bin_dir / "git").symlink_to(real)`,
`mp.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")`. Je to **tentýž binární git** (shim na něj jen
přesměrovává), symlink na existující podepsaný binár se nekontroluje jako nový soubor (ověřeno: 11 ms).
`xcrun` volej až po kontrole `sys.platform`; při chybě (`FileNotFoundError`) vrať `None`.

b) **Vypnutí automatické údržby gitu** přes `GIT_CONFIG_COUNT` / `GIT_CONFIG_KEY_n` / `GIT_CONFIG_VALUE_n`
(platí pro všechny git procesy v testech, včetně vendoru a forknutých dětí, bez zásahu do jejich configu):
`maintenance.auto=false`, `gc.auto=0`, `receive.autogc=false`. Pokud by v prostředí už `GIT_CONFIG_COUNT`
bylo, přidej klíče za existující (index = stávající count). Nic v `src/`, `vendor/` ani `tests/` `GIT_CONFIG_*`
nepoužívá (ověřeno grepem); `utils.operator_env()` env jen kopíruje.

Fixtura musí být autouse a session-scoped, aby platila i pro `engine_env` a fork testy. `gh_fake.install_fake_gh`
k PATH jen přidává prefix, takže se s tímto nepere; žádný test PATH nepřepisuje celý.

### 2. Fake `gh` vytvořit jednou za session — `prototype/tests/gh_fake.py` (+ `conftest.py`)

- Skript `gh` zapiš **jednou za session (za xdist worker)** do `tmp_path_factory.mktemp("ghbin")`
  (session fixtura, např. `gh_bin` v `conftest.py`), se shebangem `#!{sys.executable}`, `chmod 0o755`.
  Ve fixtuře ho rovnou jednou spusť naprázdno (např. s `HAIFA_FAKE_GH_STATE` na dočasný adresář), aby
  jednorázová kontrola macOS (~2 s) proběhla hned a ne uprostřed testu.
- Stav se přesune z adresáře skriptu do **per-test adresáře** předaného proměnnou prostředí, např.
  `HAIFA_FAKE_GH_STATE`: skript čte/zapisuje `calls.jsonl` a `responses.json` v `os.environ["HAIFA_FAKE_GH_STATE"]`
  místo `os.path.dirname(__file__)`.
- `install_fake_gh(tmp_path, monkeypatch, responses)` zachová signaturu i chování pro volající:
  vytvoří `tmp_path / "gh_state"`, zapíše `responses.json`, `monkeypatch.setenv("HAIFA_FAKE_GH_STATE", …)`,
  prefixuje PATH **sdíleným** bin adresářem, `delenv("HAIFA_GH")`, vrátí `GhLog(state_dir)`. Session bin adresář
  získá buď novým parametrem, nebo tak, že se `install_fake_gh` stane tenkou obálkou nad fixturou — zvol variantu
  s nejmenší změnou volajících (`tests/test_providers_github.py` fixtura `gh`, `tests/test_pr_flow_github.py`
  fixtura `gh_flow`). `GhLog` přejmenuj pole `bin_dir` → `state_dir` jen pokud to nikde jinde nevadí (grep).
- `GhProvider` spouští `gh` přes `subprocess.run` bez `env=`, takže proměnnou zdědí (ověřeno v
  `src/haifa_proto/providers/github.py`). Ověř, že žádná jiná cesta nevolá `gh` s `operator_env()` bez ní —
  `operator_env()` kopíruje `os.environ`, takže i tak projde.
- Test s `HAIFA_GH=<nonexistent>` (`test_providers_github.py:153`) se nemění.

### 3. Paralelní běh přes pytest-xdist — `prototype/pyproject.toml`, `prototype/uv.lock`

- `cd prototype && uv add --dev pytest-xdist psutil` (psutil, aby `-n auto` bral **fyzická** jádra: tady 2;
  bez něj by bral 4 logická a testy se zpomalí na 10–15 s).
- Do `[tool.pytest.ini_options]` přidej `addopts = ["-n", "auto", "--dist", "loadfile"]`.
  `loadfile` drží soubor v jednom workeru (ověřeně stabilní pro fork testy, viz krok 5).
- Pokud by `-n auto` s psutil přesto dal > 2 na stroji s málo jádry a testy přetekly 5 s, zvaž
  `--maxprocesses` nebo pevné `-n 2`; rozhodni podle měření a zdůvodni v commitu.
- `just test -n0 …` zůstane k dispozici pro sériový běh/ladění; justfile není třeba měnit
  (pokud změníš, jen komentář).

### 4. (Jen pokud po krocích 1–3 nějaký záznam překročí 5 s nebo celek 120 s) šablony repozitářů pro fixtury

- `tests/workflow_fakes.make_engine_env` dělá 6 git volání (init, 2× config, add, commit) na každý test,
  `task_repo.make_task_repo` další 2 + zápisy, `add_bare_remote` 3 (vč. push).
- Session-scoped šablona (per worker, `tmp_path_factory`) připravená jednou; v testu
  `shutil.copytree(template, repo, symlinks=True)`. Pozor na absolutní cesty: bare remote URL v `.git/config`
  po kopii přenastav (`git remote set-url`), `sssf.config.yaml` obsahuje absolutní `tmp_path` cesty — ten
  commit (`with_agents_config`) nech per-test. Ověř, že žádný test netestuje konkrétní SHA/čas commitu fixture.
- Tohle zkracuje hlavně fázi **setup** (dnes 1–1,6 s u `test_auto_continue`/`test_pr_flow_*`).

### 5. Stabilita fork testů pod xdist

`test_parallel_runs_of_different_tasks` a `test_concurrent_start_of_same_task_one_refused` forkují workery
(`multiprocessing.get_context("fork")`). Pod `--dist load` občas spadly (dítě neprojde bariérou 60 s, druhé dostane
`database is locked` po `busy_timeout=5000`). S `--dist loadfile` prošly.
- Po krocích 1–3 pusť celou sadu **3×** za sebou. Pokud fork testy kdykoli spadnou nebo visí, nepřeskakuj je a
  neměň jejich aserce/timeouty. Nejdřív najdi příčinu: kandidáti jsou (a) SQLite spojení / otevřená transakce
  zděděná přes fork z rodiče (hledej moduly, které si drží `TaskRunStore`/`Tracer` spojení mezi testy),
  (b) vlákna execnet v xdist workeru při `fork()`. Oprava patří do testů (např. zavřít spojení před forkem
  v testu), ne do `src/`, pokud nejde o skutečné čekání v kódu. Pokud příčinu nenajdeš, ponech `loadfile`
  a zapiš zjištění do reportu.

### 6. Co NEdělat

- Neměnit `src/haifa_proto/` ani `vendor/` (žádné čekání tam není; redukce git volání v `src/` je mimo zadání).
- Nepřidávat `skip`/`xfail`, nemazat ani neslučovat testy, nesnižovat timeouty v testech jako „opravu“.
- Neměnit výchozí hodnoty CLI/konfigurace (`busy_timeout`, `DEFAULT_COMMAND_TIMEOUT`, …).
- Neměnit globální git config uživatele — vše jen přes env v rámci pytest session.

## Ověření (vše z kořene repa, posuzuj podle exit statusu)

1. `time just test` → exit 0, `299 passed`, žádné `skipped`/`xfail`, celkový čas < 120 s (reálný čas z `time`).
2. `just test --durations=10` → žádný řádek > 5,00 s. Stroj je hlučný: měř 2–3×, v reportu uveď nejhorší běh.
3. `just test -n0 --durations=10` jednou pro kontrolu, že sériový běh také prochází (čas zde není kritérium).
4. `just test --collect-only -q | tail -1` → `299 tests collected`.
5. `just lint` a `just typecheck` projdou (nový kód v `tests/` je pod mypy strict: typuj fixtury).
6. `git diff --stat` obsahuje jen `prototype/tests/*`, `prototype/pyproject.toml`, `prototype/uv.lock`
   (případně komentář v `justfile`); nic v `vendor/` ani `prototype/src/`.

Pozn.: `timeout` (GNU) na tomto macOS není; na měření používej `time`. V `/tmp` leží cizí `bisect.py`, který
zastíní stdlib, když se Python spouští s cwd `/tmp` — pomocné skripty tam nespouštěj.
