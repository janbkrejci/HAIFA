# HAIFA-S01-T09: Běhy z dashboardu jako samostatné procesy

## Co se změnilo a proč

Dashboard (`factory obs`) dřív spouštěl běhy (Spustit, Vrátit, Vyřešit konflikt) na vlákně
serveru. `run_task` přitom mění cwd celého procesu, takže server pustil jen jeden běh najednou.
Zastavit odmítlo běh z dashboardu („cannot stop itself“), protože `pid` v `task_runs` byl pid
serveru. `factory task stop` tak poslal SIGTERM serveru a běhy skončily spolu se serverem.

Teď každá akce spustí samostatný proces:

```
<prefix> task run|return|resolve ID --repo KOŘEN --json [--note=…] [--force]
```

Výchozí prefix je `python -m aifactory`. Proces se spouští s `start_new_session=True`,
zavřeným stdin (`DEVNULL`), `cwd` v kořeni repa a kopií prostředí serveru. Jeho stdout (JSON
obálka) a stderr (výpis) jdou do dvou nových souborů s právy 0600
v `<HAIFA home>/logs/`, nikdy do repa. Název souboru má tvar
`<čas>-<pid serveru>-<akce>-<task>-<náhodný hex>.json|.log`.

Důsledky:

- Běhy více tasků jednoho repa i běhy více rep (více instancí serveru) běží souběžně.
  `busy()` vrací vždy `False`, takže `run-check` hlásí `launcher_busy: false`.
- Řádek v `task_runs` nese pid procesu běhu, takže Zastavit (`POST /api/runs/{id}/stop`)
  i `factory task stop` posílají signál tomuto procesu a server běží dál.
- Běh přežije ukončení serveru. Nová instance ho vidí jako běžící přes `task_runs`.
- Ke každému procesu patří daemon vlákno (`_reap`), které na proces počká, aby nezůstal
  zombie. Potom zavolá `store.for_task(task_id)`, takže řádek zabitého procesu přejde na
  `aborted`.

## Soubory

- **`aifactory/src/aifactory/home.py`** (nový): `haifa_home()` vrací `$HAIFA_HOME`, jinak
  `$XDG_CONFIG_HOME/haifa`, jinak `~/.config/haifa`; prázdná proměnná se bere jako nenastavená.
  `logs_dir()` vytvoří `logs/` s právy 0700. `create_private()` vytvoří nový soubor s právy 0600
  (`O_EXCL`).
- **`aifactory/src/aifactory/web/launcher.py`**: přepsaný `RunLauncher` s metodami `start`,
  `start_return`, `start_resolve`, `running()` a `wait()`. Přibyl protokol `Launcher`,
  dataclass `LaunchedRun` a dvojice `set_command_prefix()` / `command_prefix()`. Metoda
  `start_job` byla odstraněna.
  - Server po spuštění čeká na nový řádek v `task_runs` jako dřív. Když se řádek do 30 s
    neobjeví, vrátí `None` (`pending`) a proces běží dál.
  - Když proces skončí dřív, než řádek zabere, přečte se jeho obálka a `error.code`
    a `error.message` se vyhodí jako `TaskRunError`. Nečitelná obálka vede na `internal_error`
    s koncem výpisu (posledních 20 řádků, nejvýš 2000 znaků).
- **`aifactory/src/aifactory/web/app.py`**: `create_app(..., launcher=None)` přijímá vlastní
  spouštěč (výchozí je `RunLauncher()`). `_RUN_ERROR_STATUS` doplňuje kódy, které dřív
  přicházely jako `ReviewError`. Teď přicházejí z obálky procesu:
  - `no_pr` 404,
  - `pr_not_open`, `conflict`, `dirty_worktree` a `branch_checked_out` 409,
  - `missing_note` 400,
  - `merge_failed` 502,
  - `unknown_base` a `invalid_config` 500.
- **`aifactory/src/aifactory/web/backlog.py`, `web/review.py`**: typují se na `Launcher`.
  Vrátit volá `launcher.start_return`, Vyřešit konflikt `launcher.start_resolve`. Kontrola
  `missing_note` zůstává v serveru, takže proběhne ještě před spuštěním procesu.
- **`aifactory/src/aifactory/cli.py`** (`factory obs`): při ukončení vypíše „Běhy spuštěné
  z dashboardu, které pokračují: N“. Když N > 0, přidá nápovědu `factory task stop ID`.
  Při `--json` jde výpis na stderr.
- **`aifactory/validation/worker.py`**: když je nastavené `HAIFA_VALIDATE_FAKE`, nastaví
  `set_command_prefix([python, -m, validation.worker])` a dá adresář `aifactory` na
  `PYTHONPATH`. Procesy, které spustí server pod workerem, pak také běží nad falešným harnessem.
- **`aifactory/validation/fake.py`**: pozici ve skriptu bere z počtu volání daného agenta
  v `<script>.calls.jsonl` (a z lokálního počítadla). Druhý proces tedy dostane další položku.
  Souběžné procesy nad jedním skriptem podporované nejsou.

### Testy

- `tests/conftest.py`: autouse fixture `_haifa_home` nastaví každému testu `HAIFA_HOME` na
  dočasný adresář. Po testu ověří, že se skutečný domov nezměnil. Logy cizích procesů
  pozná podle pidu v názvu a ignoruje je.
- `tests/web/launch_stub.py`: stub procesu běhu, řízený souborem z `$HAIFA_LAUNCH_STUB`. Má
  režimy `claim-wait`, `claim-exit`, `fail` a `garbage`.
- `tests/web/test_web_launcher.py`: pokrývá vlastnosti procesu (session, stdin, cwd, soubory
  0600), mapování chyb před zabráním (běh i review), nečitelnou obálku, `pending`, souběh
  tasků i rep, Zastavit přes API, `factory task stop` z terminálu, novou instanci aplikace,
  úklid zabitého procesu, nastavitelný prefix a rozlišení domovského adresáře.
- `tests/web/test_web_task_run.py`: spouští skutečný `factory task run` přes `validation.worker`
  se skriptem JSON. Binárky `claude`, `codex`, `pi` a `gh` míří na tripwire. Testy
  `test_server_answers_while_run_is_going` a `test_second_dashboard_run_is_refused` byly
  odstraněny.
- `tests/web/thread_launcher.py`: `ThreadLauncher`, původní vláknový spouštěč zachovaný jen
  jako testovací náhrada. Používá ho `tests/web/test_web_review.py`, protože tam falešné
  harnessy žijí v testovacím procesu. Odtud byly odstraněny testy
  `test_action_while_dashboard_run_busy` a `test_launcher_start_job_propagates_review_error`.
- `tests/web/test_obs_cli.py`: ověřuje výpis pokračujících běhů na stdout, při `--json` na
  stderr, a výpis při nule běhů.
- `tests/e2e/f3_repo.py`, `tests/e2e/test_f3_browser.py`: server F3 dostane vlastní
  `HAIFA_HOME`. Po skončení se zabijí běhy, které v `trace.db` zůstaly `running`. Test na konci
  ověří, že v `logs/` jsou dvě obálky s `ok: true`, všechny soubory mají práva 0600 a žádná
  obálka není v repu. Při selhání se vypíše i konec výpisů běhů (`run_logs_tail`).

## Jak ověřit

```
just test        # mimo jiné tests/web/test_web_launcher.py, test_web_task_run.py, test_obs_cli.py
just typecheck
just lint
just e2e         # F3: dva běhy z prohlížeče jako procesy nad falešným harnessem
```

Ruční ověření: spusťte `factory obs` a v dashboardu spusťte dva tasky. Oba poběží souběžně.
Obálky a výpisy najdete v `~/.config/haifa/logs/` (nebo v `$HAIFA_HOME/logs/`). Pak
`factory task stop ID` zastaví jen běh a server běží dál. Po Ctrl+C server vypíše, kolik běhů
pokračuje.

Spec: `specs/HAIFA-S01-T09-behy-z-dashboardu-jako-samostatne-proces.md`.
