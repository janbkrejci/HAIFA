# HAIFA-S01-T09: Běhy z dashboardu jako samostatné procesy

## Cíl

Dashboard (Spustit, Vrátit, Vyřešit konflikt) dnes volá `run_chain` / `return_task` /
`resolve_task` na vlákně serveru (`aifactory/src/aifactory/web/launcher.py`). `run_task` mění
cwd celého procesu a drží procesní zámek signálů, proto server pustí jen jeden běh najednou,
`stop_run` odmítne běh s `pid == os.getpid()` („cannot stop itself“), `factory task stop`
z terminálu pošle SIGTERM serveru a běhy umřou se serverem.

Nově server spouští **samostatný proces** `<prefix> task run|return|resolve ID --repo KOŘEN --json`
a čeká na řádek v `task_runs` jako dnes. Řádek pak nese pid procesu běhu, takže `stop_run`
(beze změny) zastaví správný proces.

Pevná omezení: `aifactory/src/aifactory/engine/`, `vendor/`, `prototype/` se nemění;
`aifactory/src/aifactory/run/stop.py` (`factory task stop`) se nemění; testy nevolají
model ani síť. Mimo rozsah: více rep v jednom serveru, limit souběhu, `.env` per repo,
odstranění `launcher_busy` z frontendu (frontend se nemění vůbec).

## Soubory

| Soubor | Změna |
|---|---|
| `aifactory/src/aifactory/home.py` | **nový** – domovský adresář HAIFA, `logs/`, soubory 0600 |
| `aifactory/src/aifactory/web/launcher.py` | přepsat na procesový spouštěč + `Launcher` Protocol + nastavitelný prefix |
| `aifactory/src/aifactory/web/backlog.py` | `start_run` přes nový spouštěč, docstringy |
| `aifactory/src/aifactory/web/review.py` | `start_return` / `start_resolve` přes `launcher.start_return/start_resolve` |
| `aifactory/src/aifactory/web/app.py` | `create_app(..., launcher=None)`, typ `Launcher`, mapa chyb, docstring |
| `aifactory/src/aifactory/cli.py` | `factory obs`: po ukončení vypsat počet pokračujících běhů |
| `aifactory/validation/worker.py` | při `HAIFA_VALIDATE_FAKE` nastavit prefix spouštěče na sebe (+ `PYTHONPATH`) |
| `aifactory/validation/fake.py` | pozice ve skriptu z `<script>.calls.jsonl` |
| `aifactory/validation/README.md` | jedna věta o pozici ve skriptu napříč procesy (volitelně) |
| `aifactory/tests/conftest.py` | autouse `HAIFA_HOME` na dočasný adresář + kontrola skutečného domova |
| `aifactory/tests/web/thread_launcher.py` | **nový** – dnešní vláknový spouštěč jako testovací náhrada |
| `aifactory/tests/web/launch_stub.py` | **nový** – stub proces běhu pro testy |
| `aifactory/tests/web/test_web_launcher.py` | **nový** – testy procesového spouštěče |
| `aifactory/tests/web/test_web_task_run.py` | přepsat na nový spouštěč (validation.worker + stub) |
| `aifactory/tests/web/test_web_review.py` | použít `ThreadLauncher`, odstranit 2 testy starého spouštěče |
| `aifactory/tests/web/test_obs_cli.py` | test výpisu pokračujících běhů |
| `aifactory/tests/e2e/f3_repo.py`, `test_f3_browser.py` | `HAIFA_HOME` serveru, logy běhů v chybových výpisech, kontrola logů |
| `app_docs/HAIFA-S01-T09-behy-z-dashboardu-jako-samostatne-proces.md` | dokumentace (dokumentátor) |

`justfile` se měnit nemusí.

---

## 1. `aifactory/src/aifactory/home.py` (nový)

```python
HOME_ENV = "HAIFA_HOME"

def haifa_home(environ: Mapping[str, str] | None = None) -> Path:
    """$HAIFA_HOME, jinak $XDG_CONFIG_HOME/haifa, jinak ~/.config/haifa (prázdná hodnota = nenastaveno)."""
def logs_dir(environ=None) -> Path:
    """<home>/logs, vytvoří ho (parents=True) s právy 0700 (os.chmod po mkdir jen když ho vytvořil)."""
def create_private(path: Path) -> BinaryIO:
    """Nový soubor s právy 0600: os.open(path, O_WRONLY|O_CREAT|O_EXCL, 0o600), os.fchmod(fd, 0o600), os.fdopen(fd, "wb")."""
```

- `environ` default `os.environ`; hodnoty `expanduser()`; prázdný řetězec se bere jako nenastaveno.
- Žádné jiné zápisy; modul nemá závislost na web/ ani run/.

## 2. `aifactory/src/aifactory/web/launcher.py` (přepis)

Nový docstring modulu popíše: proces běhu, soubory v `logs/`, čekání na řádek, mapování chyb,
souběh, úklid, přežití serveru, nastavitelný prefix.

### Prefix příkazu

```python
DEFAULT_COMMAND: tuple[str, ...] = (sys.executable, "-m", "aifactory")   # aifactory/__main__.py volá cli.main
_command: tuple[str, ...] | None = None

def set_command_prefix(prefix: Sequence[str] | None) -> None   # None vrátí výchozí
def command_prefix() -> tuple[str, ...]
```

`RunLauncher(command: Sequence[str] | None = None)` – explicitní prefix (testy), jinak
`command_prefix()` čtené **v okamžiku startu** (worker ho nastaví až před `cli.main`, ještě
před `create_app`, ale ať to nezávisí na pořadí).

### Protocol pro app a testovací náhradu

```python
class Launcher(Protocol):
    def start(self, repo: Path, task_id: str, *, note: str | None, force: bool, timeout: float = 30.0) -> TaskRunRow | None: ...
    def start_return(self, repo: Path, task_id: str, note: str, *, timeout: float = 30.0) -> TaskRunRow | None: ...
    def start_resolve(self, repo: Path, task_id: str, *, timeout: float = 30.0) -> TaskRunRow | None: ...
    def busy(self) -> bool: ...
    def running(self) -> list[LaunchedRun]: ...
```

### `LaunchedRun` (dataclass)

`task_id`, `action` (`run`/`return`/`resolve`), `argv`, `pid`, `envelope_path`, `log_path`,
`process: subprocess.Popen[bytes]` (repr=False), `started_at`.

### `RunLauncher`

- `busy()` → vždy `False` (frontend pole `launcher_busy` zůstává, `run-check` vrací `false`).
- `running()` → kopie seznamu živých `LaunchedRun` (`process.poll() is None`), pod `threading.Lock`.
- `wait(timeout=None)` → join všech čekacích vláken (testy); po něm jsou všechny procesy uklizené.
- `start(...)`: `note` prázdný/whitespace → `None`; argv
  `["task", "run", task_id, "--repo", str(repo), "--json"]` + `[f"--note={note}"]` když note + `["--force"]` když force.
  (`--note=` v jednom tokenu, aby poznámka začínající `-` nerozbila argparse.)
- `start_return(...)`: `["task", "return", task_id, "--repo", str(repo), "--json", f"--note={note}"]`.
- `start_resolve(...)`: `["task", "resolve", task_id, "--repo", str(repo), "--json"]`.
- Všechny tři volají `_launch(repo, task_id, action, args, timeout)`.

### `_launch`

1. `known = _run_ids(repo, task_id)` (stávající helper zůstává; stejně `_new_row`).
2. Soubory: `logs = home.logs_dir()`; jméno
   `f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{action}-{task_id}-{secrets.token_hex(4)}"`;
   `envelope_path = logs / f"{stem}.json"`, `log_path = logs / f"{stem}.log"`, oba přes
   `home.create_private`. **`os.getpid()` (pid serveru) v názvu je nutný** – používá ho kontrola
   v `conftest.py`. Nikdy nic do repa.
3. `subprocess.Popen([*prefix, *args], cwd=repo, env=dict(os.environ), stdin=subprocess.DEVNULL,
   stdout=envelope_file, stderr=log_file, start_new_session=True, close_fds=True)`;
   rodičovské kopie obou souborů hned po `Popen` zavřít (`with` blok). `OSError` z `Popen`
   → `TaskRunError("internal_error", f"cannot start {argv[0]}: {exc}")`.
4. Zapsat `LaunchedRun` do `self._live`, spustit daemon vlákno `_reap(launched, repo, task_id)`
   (`name=f"factory-run-wait-{pid}"`), uložit ho do `self._waiters`.
5. Smyčka do `deadline = monotonic() + timeout` s `_POLL = 0.05`:
   - `row = _new_row(repo, task_id, known)` → je-li, vrátit ho;
   - `process.poll() is not None` → ještě jednou `_new_row` (vrátit, je-li), jinak
     `raise _launch_error(launched)`; pokud obálka je `ok: true` (bez řádku), vrátit `None`;
   - po deadline `None` (`pending`, proces běží dál).

### `_launch_error(launched) -> TaskRunError | None`

- Přečíst `envelope_path` (text, `errors="replace"`). Parsovat `json.loads(text)`; když
  selže, zkusit od prvního řádku, který je přesně `{` (stdout může obsahovat cizí výpis).
- Obálka je `dict` s `ok is False` a `error` dict s `code`/`message` (str) →
  `TaskRunError(code, message)` (stejná třída pro run i review; mapování dělá app, viz §5).
- Obálka `ok is True` → `None` (volající vrátí `pending`).
- Jinak (prázdná / nečitelná) → `TaskRunError("internal_error",
  f"{action} {task_id}: process exited with {returncode} without a readable envelope; log tail:\n{tail}")`,
  kde `tail` = posledních 20 řádků (max ~2000 znaků) z `log_path`.

### `_reap` (čekací vlákno)

`launched.process.wait()` (úklid zombie; `Popen` je vůči souběžnému `poll()` bezpečný),
odebrat z `self._live`, pak `store = existing_store(repo)` → `store.for_task(task_id)` → `close()`
(proces je pryč, takže `_reap` ve store přepne `running` řádek zabitého procesu na `aborted`).
Výjimky `TaskRunError`, `ConfigError`, `sqlite3.Error`, `OSError` spolknout.

Pozn.: proces běží v nové session a výstupy jdou do souborů → přežije SIGINT/ukončení
serveru; po skončení serveru ho uklidí init. Nová instance aplikace ho vidí přes `task_runs`
(pid žije) a `stop_run` ho zastaví normálně (`row.pid != os.getpid()`).

Odstranit: `start_job`, `last_error`, `last_result`, `_work`, import `ReviewError`,
`run_queue`, `traceback`. Vláknová varianta jde do testů (§9).

## 3. `aifactory/src/aifactory/web/backlog.py`

- `from aifactory.web.launcher import Launcher` místo `RunLauncher`.
- `start_run(repo, task_id, body, launcher: Launcher)` – volání `launcher.start(...)` beze změny,
  docstring: „``factory task run [--note] [--force]`` as a separate process (``launcher.py``)“.
- `run_check` beze změny (parametr `launcher_busy` zůstává).

## 4. `aifactory/src/aifactory/web/review.py`

- Typ `Launcher`; docstring modulu: return/resolve se spouští jako samostatný proces
  `factory task return|resolve`.
- `start_return`: kontroly (`_check_keys`, typ `note`, `missing_note` ReviewError) zůstávají
  v serveru; pak `row = launcher.start_return(repo, task_id, text)`. Funkce `job` pryč.
- `start_resolve`: `_check_keys`, pak `launcher.start_resolve(repo, task_id)`.
- Import `review_core` zůstává, pokud ho používá approve/další kód (ano: `approve_task`).

## 5. `aifactory/src/aifactory/web/app.py`

- `create_app(repo, *, static_dir=None, live_interval=..., launcher: Launcher | None = None)`
  (přidat jen nový keyword na konec stávající signatury); `app.state.launcher = launcher or RunLauncher()`.
- Typové anotace `launcher: Launcher` v handlerech; `backlog_run_check` posílá dál
  `launcher.busy()` (u `RunLauncher` vždy `False`).
- `_RUN_ERROR_STATUS` doplnit o kódy review, které dosud chyběly (spouštěč vyhazuje
  `TaskRunError` i pro return/resolve): `"no_pr": 404, "pr_not_open": 409, "conflict": 409,
  "dirty_worktree": 409, "branch_checked_out": 409, "missing_note": 400, "merge_failed": 502,
  "unknown_base": 500, "invalid_config": 500`. Existující položky nemění hodnotu, takže
  stavy zůstávají jako dnes (`already_running`/`unmet_dependencies` 409, `no_pr` 404, ...).
  `internal_error` → výchozí 500.
- Docstring modulu (odstavce Run a Review): „starts ``factory task run`` as a separate process
  (``launcher.py``); runs of several tasks run concurrently“.

## 6. `aifactory/src/aifactory/cli.py` – `factory obs`

V `_obs` obalit `web_server.serve(...)` do `try/finally` (uvnitř stávajícího
`contextlib.suppress(KeyboardInterrupt)` nebo kolem něj) a po návratu:

```python
left = len(app.state.launcher.running())
message = f"Běhy spuštěné z dashboardu, které pokračují: {left}" + (
    " (zastaví je factory task stop ID)" if left else "")
print(message, file=sys.stderr if args.json else sys.stdout)
```

S `--json` musí stdout zůstat jediná obálka (test `test_obs_json_envelope` parsuje stdout).

## 7. `aifactory/validation/worker.py`

V `main`, ve větvi `if script:` po `fake.install(...)`:

```python
from aifactory.web import launcher
launcher.set_command_prefix([sys.executable, "-m", "validation.worker"])
_ensure_pythonpath()   # AIFACTORY_DIR = Path(__file__).resolve().parents[1] na začátek os.environ["PYTHONPATH"], pokud tam není
```

Procesy běhu dědí prostředí serveru (včetně `HAIFA_VALIDATE_FAKE` a `PYTHONPATH`) → běží
zase přes worker nad falešným harnessem. `HAIFA_VALIDATE_HIDDEN` worker už dnes pop-uje, to
zůstává. Aktualizovat docstring.

## 8. `aifactory/validation/fake.py`

- Docstring: místo „One script serves one process … nothing is kept between processes“ →
  „Each call of an agent takes the entry at the position given by the number of calls of that
  agent already recorded in `<script>.calls.jsonl`, so a second process with the same script
  continues with the next entry. Concurrent processes on one script are not supported.“
- `FakeHarness.run`: nepopovat. `taken = max(self._recorded(agent), self._local.get(agent, 0))`,
  kde `_recorded` počítá řádky `calls.jsonl` s `"agent" == agent` (neexistující soubor = 0,
  vadné řádky přeskočit) a `_local` je počítadlo v procesu (zvýšit při převzetí položky,
  aby se v jednom procesu chování nezměnilo, ani když `apply_edits` selže před zápisem).
  `taken >= len(queue)` → stávající `RuntimeError("validation fake: no scripted entry left for ...")`.
  `entry = copy.deepcopy(queue[taken])`.
- `self._local` sdílet mezi fakes stejného skriptu (např. uložit do slovníku `script` pod
  klíčem mimo `agents`, nebo předat jeden dict všem `FakeHarness` v `install`).

Validace (`validation/context.py`) píše pro každý příkaz nový soubor skriptu → beze změny.

## 9. Testy

### 9a. `aifactory/tests/conftest.py`

- Session fixture zjistí skutečný domov **před** jakoukoli úpravou prostředí:
  `real = aifactory.home.haifa_home()`.
- Nová autouse fixture (scope function) `_haifa_home(tmp_path_factory, monkeypatch)`:
  `home = tmp_path_factory.mktemp("haifa-home")` (ne `tmp_path`, aby testy, které vypisují
  `tmp_path`, neviděly nic navíc), `monkeypatch.setenv("HAIFA_HOME", str(home))`,
  snapshot skutečného domova před testem, `yield`, snapshot po testu, `assert` shoda.
- Snapshot: `{relpath: (size, mtime_ns)}` souborů pod `real` (neexistuje → `{}`).
  Aby souběžně běžící skutečný dashboard operátora nezpůsobil flaky test, ignorovat soubory
  v `logs/`, jejichž jméno **neobsahuje** `f"-{os.getpid()}-"` (spouštěč dává pid serveru do
  názvu; server v testech = proces pytestu). Ostatní cesty (mimo `logs/`) se porovnávají celé.
- Docstring modulu doplnit o odrážku.

### 9b. `aifactory/tests/web/thread_launcher.py` (nový) – testovací náhrada

Dnešní `RunLauncher` přesunutý sem jako `ThreadLauncher` splňující `Launcher`:
`start` → `run_queue.run_chain(...)`, `start_return` → `review_core.return_task(repo, task_id, note)`,
`start_resolve` → `review_core.resolve_task(repo, task_id)` (vyhledat na modulu
`aifactory.review` v okamžiku volání – testy je monkeypatchují), `busy`, `wait`, `running() → []`,
jeden běh najednou jako dnes. Docstring: „test double: in-process thread, for tests whose
fake harnesses live in the test process“.

### 9c. `aifactory/tests/web/test_web_review.py`

- `app_fixture`: `create_app(repo, static_dir=..., launcher=ThreadLauncher())`; `wait()` beze změny.
- Odstranit `test_action_while_dashboard_run_busy` a `test_launcher_start_job_propagates_review_error`
  (pokryje 9e) a nepoužité importy (`RunLauncher`, `threading` pokud nepoužité).

### 9d. `aifactory/tests/web/launch_stub.py` (nový) – stub proces

Spouští se jako `[sys.executable, str(STUB)]` + argv spouštěče (`task run ID --repo R --json ...`).
Typovaný (mypy strict), bez `__init__` side-effectů. Chování z JSON souboru v `$HAIFA_LAUNCH_STUB`
(`{task_id: {"mode": ..., "code": ..., "message": ...}}`, chybějící task → `claim-wait`):

- Vždy na začátku zapíše `<control>.<task_id>.<pid>.json` s `argv`, `cwd`, `sid == pid`
  (`os.getsid(0) == os.getpid()`), `stdin` (výsledek `sys.stdin.read()` – u DEVNULL `""`),
  `haifa_home` (`os.environ.get("HAIFA_HOME")`).
- `claim-wait`: `TaskRunStore(repo/".factory"/"trace.db").claim(TaskRunRow(run_id=new id,
  task_id, branch=f"factory/{task_id}-x", worktree="", base="main", base_sha="0"*40,
  head_sha=None, state=RUNNING, started_at=_now(), pid=os.getpid(), workflow=action, note=<--note>))`;
  `TaskRunError` z `claim` (`already_running`) → vypsat `envelope_fail(code, message)` JSON na
  stdout, exit 2. Pak `time.sleep` ve smyčce (do SIGTERM/SIGKILL; max ~120 s pojistka).
- `claim-exit`: claim, `finish(run_id, SUCCEEDED, None, None)`, na stdout `envelope_ok({...})`, exit 0.
- `fail`: na stdout `envelope_fail(code, message)` (JSON), exit 2, nic nezabere.
- `garbage`: stdout `not json`, stderr pár řádků s `STUB-TAIL-MARKER` na konci, exit 3.

### 9e. `aifactory/tests/web/test_web_launcher.py` (nový)

Fixture: `repo = make_run_repo(...)` (z `tests/run/run_repo`), control soubor,
`monkeypatch.setenv("HAIFA_LAUNCH_STUB", ...)`, `RunLauncher(command=[sys.executable, str(STUB)])`,
`create_app(repo, static_dir=..., launcher=launcher)`, `TestClient`. Teardown: zabít živé
procesy z `launcher.running()` (SIGKILL) a `launcher.wait(30)`.

Testy:
1. **start a obálka/soubory**: `POST /api/backlog/tasks/T01/run` (`claim-wait`) → 202, `run.state == "running"`,
   `run.pid` je pid procesu z `launcher.running()`; záznam stubu: `cwd == repo`, `sid == pid`,
   `stdin == ""`, `haifa_home == os.environ["HAIFA_HOME"]`, argv obsahuje `--repo <repo> --json`
   a `--note=z UI`; v `$HAIFA_HOME/logs` je pár `.json` + `.log` s `stat.S_IMODE == 0o600`
   a v názvu `-{os.getpid()}-`; v repu žádný nový soubor mimo `.factory/` (git status).
2. **mapování chyb před zabráním** (parametrizace): `fail` s `already_running` → 409,
   `unmet_dependencies` → 409, `unknown_task` → 404, `no_writes` → 422; přes
   `POST /api/review/T01/return` (`{"note": "x"}`) `no_pr` → 404 a `/resolve` `pr_not_open` → 409;
   kód a message v obálce odpovědi = ze stubu; žádný řádek v `task_runs`.
3. **nečitelná obálka**: `garbage` → 500, `error.code == "internal_error"`, message obsahuje
   `STUB-TAIL-MARKER` a exit kód.
4. **claim-exit** → 202 s řádkem; `launcher.wait()`; řádek `succeeded`.
5. **pending**: `claim-wait` se zpožděním před claim (mode `claim-wait` + `"delay": 2`)
   a `RunLauncher.start(..., timeout=0.2)` přímo → `None`; pak se řádek objeví.
6. **souběh v jednom repu**: T01 a T02 (`force: true`) `claim-wait` → oba 202 a oba `running`;
   `GET /api/backlog/tasks/T01/run-check` → `launcher_busy is False`; druhý start téhož tasku
   → 409 `already_running` (ze store ve stubu).
7. **souběh dvou rep**: dvě `create_app` nad dvěma repy (každá svůj `RunLauncher`) → oba běhy `running`.
8. **Zastavit přes API**: `POST /api/runs/{run_id}/stop` → 200, `run.state == "stopped"`,
   `signalled == [pid]`; `launcher.wait(10)`; `launcher.running() == []`.
9. **`factory task stop` z terminálu**: `subprocess.run([sys.executable, "-m", "aifactory", "task",
   "stop", T01, "--repo", repo, "--json"])` → ok; proces stubu skončil (reaped), `/api/health` 200
   (server = pytest proces žije), řádek `stopped`.
10. **nová instance aplikace**: start přes app A, pak `create_app` B (nový `RunLauncher`) nad
    stejným repem: `GET /api/runs?task=T01` → `running` se stejným pidem; stop přes B → 200.
11. **úklid zabitého procesu**: `os.kill(pid, SIGKILL)`; do ~10 s: `launcher.running() == []`,
    `ps -o stat= -p pid` neukazuje `Z` (nebo pid neexistuje) a řádek je `aborted`
    (čti `TaskRunStore(...).get(run_id)` bez reapu – úklid musí udělat spouštěč sám).
12. **prefix**: `set_command_prefix([...])` → `RunLauncher()` ho použije; `set_command_prefix(None)`
    vrátí `DEFAULT_COMMAND` (vrátit v `finally`).
13. **home**: `haifa_home` s `HAIFA_HOME`, jen `XDG_CONFIG_HOME`, ani jedno (`HOME` přes
    `environ` dict) → `~/.config/haifa`; prázdné hodnoty ignorované; `create_private` → 0600.

### 9f. `aifactory/tests/web/test_web_task_run.py` (přepis na nový spouštěč)

Fixture `worker_env(monkeypatch, tmp_path)`: JSON skript
`{"agents": {"planner": [call("model"), call("loader")]}}` (vzor `f3_repo._planner_call`,
`writes` kroku je `src/app/`), tripwire (vzor `f3_repo.tripwire`) pro `AIFACTORY_GH`,
`CODEX_PATH`, `CLAUDE_CODE_PATH`, `PI_PATH`; `setenv`: `HAIFA_VALIDATE_FAKE`, `PYTHONPATH`
(+ `AIFACTORY` dir), `UV_NO_SYNC=1`, `ENGINEER_NAME`, `GIT_*`; `delenv`
`HAIFA_VALIDATE_HIDDEN`, `HAIFA_SANDBOX_REPO`. App:
`create_app(repo, static_dir=..., launcher=RunLauncher(command=[sys.executable, "-m", "validation.worker"]))`.
`wait(app)` = `launcher.wait(120)` + `launcher.running() == []`. Na konci každého testu
`not marker.exists()` (tripwire nesáhnut).

1. `test_run_from_api_creates_task_run` – skutečný `task run` přes worker: 202, `pending False`,
   `run.task_id == T01`, `run.pid != os.getpid()`; po `wait` řádek `succeeded`, `note == "z UI"`,
   `calls.jsonl` má 1 volání `planner`.
2. `test_unmet_dependencies_and_force` – T02 bez force → 409 `unmet_dependencies` (skutečný
   proces, žádné volání agenta), žádný řádek; s `force` → 202, `succeeded`; protože T01 v tomto
   testu neběžel, plánovač dostane položku 1 – **přidat i test, že druhý proces dostane druhou
   položku**: v testu 1 navíc spustit po T01 ještě T02 (`force: true`) a ověřit, že vznikl
   `src/app/loader.py` (druhá položka) v jeho worktree / commitu větve `factory/T02-1`.
3. `test_run_check_reports_uncommitted_config` – beze změny + `launcher_busy is False`.
4. `test_run_rejects_bad_input` – beze změny (`unknown_task` 404 teď přichází z obálky procesu).
5. Odstranit `test_server_answers_while_run_is_going` a `test_second_dashboard_run_is_refused`
   (nahrazeno 9e/6 a 9e/1); docstring modulu přepsat.

### 9g. `aifactory/tests/web/test_obs_cli.py`

Nový test: `fake_serve` nahradí `app.state.launcher` objektem, jehož `running()` vrací 2 položky
(nebo monkeypatch `RunLauncher.running`), spustit `factory obs --no-open` (text) → stdout obsahuje
`pokračují: 2`; varianta `--json` → stdout je jediná obálka, hláška na stderr.

### 9h. e2e (`tests/e2e/f3_repo.py`, `test_f3_browser.py`)

- `obs_server(repo, script, wire, log, home)` a `_server_env(..., home)` nastaví
  `env["HAIFA_HOME"] = str(home)` (home = `tmp_path / "haifa-home"`); `Server` dostane `home`.
- `log_tail` / chybová hlášení v `_watch_run` a `_run`: přidat konec nejnovějších `*.log`
  z `home/logs` (helper `run_logs_tail(home)`), protože výpis běhu už není ve výpisu serveru.
- Na konci `test_f3_task_lifecycle_in_browser`: v `home/logs` jsou `.json` soubory (2 běhy),
  všechny s právy 0600, každá obálka `ok: true`; žádný z nich v repu.
- Úklid fixture: po ukončení serveru přečíst `task_runs` a `running` řádky (pid) zabít, ať
  po neúspěšném testu nezůstanou procesy.
- Pořadí `["planner", "planner"]` v `calls.jsonl` a `second.py == "SECOND = 2"` už ověřuje,
  že druhý proces dostal druhou položku skriptu.

## 10. Dokumentace

`app_docs/HAIFA-S01-T09-behy-z-dashboardu-jako-samostatne-proces.md` (česky): domovský adresář
(`HAIFA_HOME` → `XDG_CONFIG_HOME/haifa` → `~/.config/haifa`), kde jsou logy běhů, chování
Zastavit / `factory task stop`, přežití serveru, hláška `factory obs`, prefix a validation.worker,
pozice ve falešném skriptu.

## Ověření

```
just test        # celé pytest + frontend
just typecheck   # mypy strict (src, tests, validation)
just lint        # ruff check + format --check
just e2e         # F3 v prohlížeči
```

Rychlé iterace: `cd aifactory && uv run pytest tests/web tests/validation -q`.

## Rizika / poznámky

- `stop_run` nijak neměnit; funguje, protože `row.pid` je pid procesu běhu.
- Zombie: `store._alive` považuje zombie za živý → úklid musí dělat čekací vlákno (`process.wait()`)
  a hned potom reap ve store; bez toho by řádek zabitého procesu zůstal `running`.
- `Popen` s `start_new_session=True` a soubory místo rour – plná roura by běh zablokovala.
- Logy se nerotují (mimo rozsah).
- Souběžné procesy nad jedním falešným skriptem nejsou podporované (pozice z `calls.jsonl`).
