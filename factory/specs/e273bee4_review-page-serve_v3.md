# Plán: minimální review stránka `haifa-proto serve`

## Cíl

`haifa-proto serve [--port N] [--host H] [--repo PATH]` spustí lokální Starlette server (D3 v `docs/product-brief.md`). Stránka `/` vypíše otevřené PR úkolů a u každého nabídne **Schválit** a **Vrátit** (s poznámkou). Výsledek operace se ukáže na stránce. Stránka nemá vlastní logiku: data i operace jdou přes funkce core, které používá CLI.

Mimo rozsah: ostatní obrazovky dashboardu, Vue, editory, přihlašování. `vendor/` se nemění. Testy nevolají model.

## Co už existuje (nečíst znovu, jen pro orientaci)

- `prototype/src/haifa_proto/review.py`: `approve_task(repo, task_id, *, provider=None, cfg=None) -> ApproveResult`, `return_task(repo, task_id, note, *, cfg=None, code=None, provider=None) -> TaskRunResult`, `ReviewError(code, message)`. Soukromý `_context(repo, cfg, provider) -> _Ctx(root, config, store, provider)`. CLI (`cli.py::_task_approve`, `_task_return`) volá právě tyto funkce; `_task_return` chytá `(review.ReviewError, run.TaskRunError)`.
- `prototype/src/haifa_proto/run.py`: `TaskRunStore` (tabulky `task_runs`, `task_prs` v trace DB), `TaskRunRow`, `TaskPrRow` (`branch, task_id, provider, pr_id, url, base, base_sha, title, body, state, ...`, `.request()`), `runs_on_branch(branch)` (nejnovější první), `load_base_backlog(root, config, sha, dest)`, `main_root`, `trace_db_path`. `_signals_restored()` kolem `run_workflow`.
- `prototype/src/haifa_proto/prbody.py`: `run_cost(trace_db, run_id) -> (cost, tokens)`, `branch_cost`, `_gates(trace_db, run_id)` (čte `gate_results` + `phases`, vrací markdown řádky), `_query(trace_db, sql, args)` (read-only, chyby → `[]`).
- Trace DB schéma (vendor `tracer.py`): `phases(phase_id, adw_id, seq, name, kind, owner, status, ...)`, `events(event_id, adw_id, phase_id, type, name, payload_json, ...)`, `gate_results(adw_id, phase_id, gate, passed, violations_json, ...)`, `sessions(adw_id, total_cost, total_tokens, ...)`.
  - Agentní krok (`workflow.py::role`) zapisuje `ph.log(harness=..., model=..., thinking=...)` → řádek v `events` s `type='log'` a `payload_json` obsahujícím `harness`, `model`; fáze má `kind='agent'`, `owner=<agent>`.
  - Kódový krok test/quality/command (`workflow.py::code_step`) zapisuje `ph.log(passed=..., checks="k/n", artifacts=...)`; fáze má `kind='code'`.
- `providers/base.py`: `GitProvider.status(pr) -> PrStatus(state, ...)`, `OPEN_STATES = (open, mergeable, conflict)`.
- `backlog.py`: `Task(id, title, status, level, path, parent: Container, ...)`, `Container(id, title, level, parent, ...)`.
- `config.py`: `load_config(root)` čte `.factory/config.yaml`; `ConfigError`.
- `cli.py`: subparser `serve` je zatím stub („not implemented yet“).
- Testy: `tests/test_cli_task.py::_with_agents_config(env)` (commitne falešný sssf config tam, kde ho CLI hledá → CLI i web jdou bez `cfg`), `tests/task_repo.py` (`make_task_repo`, `T01`, `TASK_FILE`, `git`, `writer`), `tests/workflow_fakes.py` (`EngineEnv`, `ok`, `env.script.add/on/calls`). Fixture `engine_env` v `conftest.py`. Falešný config: `coding_agent: claude`, `model: sonnet`.

## Změny

### 1. Závislosti (`prototype/pyproject.toml`, `uv.lock`)

V `prototype/`:
```
uv add starlette jinja2 uvicorn python-multipart
uv add --dev httpx
```
(`python-multipart` potřebuje `request.form()`, `httpx` potřebuje `starlette.testclient.TestClient`.) Šablony v `src/haifa_proto/templates/` hatch zabalí automaticky s balíčkem.

### 2. Lokální nastavení portu (`prototype/src/haifa_proto/config.py`)

- Konstanty `LOCAL_PATH = Path(".factory") / "local.yaml"`, `DEFAULT_PORT = 4700`.
- `@dataclass(frozen=True) class LocalConfig: port: int = DEFAULT_PORT`.
- `def load_local(repo_root: Path) -> LocalConfig`: chybějící nebo prázdný soubor → výchozí. Nevalidní YAML, top level ne-mapping, `port` ne-`int` (pozor: `bool` je `int`, odmítnout) nebo mimo 1–65535 → `ConfigError` se stejným stylem zpráv jako `load_config`. Neznámé klíče ignorovat.
- Do kořenového `.gitignore` přidat řádek `.factory/local.yaml` (je to strojově lokální soubor).

### 3. Čtení trace pro review (`prototype/src/haifa_proto/prbody.py`)

Přidat veřejné strukturované čtečky (vedle `_gates`, přes `_query`, takže chybějící DB/tabulka → prázdný seznam):

```python
@dataclass(frozen=True)
class StepInfo:      # agentní krok běhu
    step: str        # phases.name
    agent: str       # phases.owner
    harness: str | None
    model: str | None

@dataclass(frozen=True)
class CheckInfo:     # gate nebo test
    kind: str        # "gate" | "test"
    name: str        # gate: název gate; test: název fáze
    phase: str
    passed: bool
    detail: str      # gate: violations spojené "; "; test: "k/n" z payloadu checks (nebo "")

def run_steps(trace_db: Path, run_id: str) -> list[StepInfo]
def run_checks(trace_db: Path, run_id: str) -> list[CheckInfo]
```

- `run_steps`: `SELECT p.name, p.owner, e.payload_json FROM phases p LEFT JOIN events e ON e.phase_id = p.phase_id AND e.type = 'log' WHERE p.adw_id = ? AND p.kind = 'agent' ORDER BY p.seq, e.started_at`; na fázi vzít první payload, který má klíč `harness`; jedna položka na fázi v pořadí `seq`.
- `run_checks`: gates = stejná data jako `_gates` (poslední výsledek na `(phase, gate)`); testy = fáze `kind='code'`, jejichž log payload má klíč `passed` (bool) — `name=phase`, `detail=payload.get("checks", "")`. Přepsat `_gates` tak, aby stavěl z `run_checks` (výstup PR body se nesmí změnit — `test_pr_flow_local` to hlídá).

### 4. Core funkce pro seznam (`prototype/src/haifa_proto/review.py`, `run.py`, `gitops.py`)

- `run.py`: `TaskRunStore.open_prs(self) -> list[TaskPrRow]` = `self._prs("state = 'open'", ())`.
- `gitops.py`: `def diff_stat(cwd: Path, base: str, tip: str) -> DiffStat | None` přes `git diff --numstat base tip` (binární řádky `-\t-` počítat jako soubor s 0/0); `DiffStat(files: int, insertions: int, deletions: int)` jako frozen dataclass. Když některý ref neexistuje → `None`.
- `review.py`:

```python
@dataclass
class RunInfo:
    run_id: str; state: str; started_at: str; note: str | None; workflow: str | None
    cost: float; tokens: int
    steps: list[StepInfo]; checks: list[CheckInfo]

@dataclass
class OpenReview:
    task_id: str
    title: str                         # z backlogu v base, jinak pr.title
    ancestors: list[tuple[str, str, str]]  # (level, id, title) od nejvyšší úrovně; pro výchozí levels = [("module",..), ("step",..)]
    pr: TaskPrRow
    provider_state: str                # z provider.status(); "unknown" při ProviderError
    provider_error: str | None
    diff: DiffStat | None              # base_sha PR .. refs/heads/<branch>
    runs: list[RunInfo]                # všechny běhy na větvi, nejnovější první
    total_cost: float; total_tokens: int

def open_reviews(repo: Path, *, provider: GitProvider | None = None, cfg: Any | None = None) -> list[OpenReview]
```

  - Použít `_context`; `store.close()` ve `finally`.
  - Pro každý `store.open_prs()`: `provider.status(row.request())` — `ProviderError` nezbortí stránku (`provider_state="unknown"`, `provider_error="code: message"`); PR ve stavu mimo `OPEN_STATES` (merged/closed mimo HAIFA) vynechat.
  - Backlog z base načíst jednou (`gitops.rev_parse(root, f"refs/heads/{config.base}")` + `run.load_base_backlog` v `TemporaryDirectory`); titulek a předky vzít z `Task`, předky projít přes `parent` až po kořen (vynechat kontejnery s `id is None`).
  - `runs` z `store.runs_on_branch(row.branch)`, cost/tokens přes `run_cost`, kroky a kontroly přes `run_steps` / `run_checks` s `store.db_path`.
  - Řazení: podle `pr.created_at` vzestupně (nejstarší čeká nejdéle) — stačí otočit výsledek `open_prs`.
  - Žádná prezentační logika (formátování čísel apod. je v šabloně).

### 5. Běh workflow mimo hlavní vlákno (`prototype/src/haifa_proto/run.py`)

Engine (`vendor/.../session.py::_finalize_when_killed`) volá `signal.signal`, což mimo hlavní vlákno vyhodí `ValueError`. Starlette TestClient i `run_in_threadpool` pouští handler v jiném vlákně, takže `return_task` z webu by selhal. `vendor/` měnit nelze.

- Nejdřív napsat test vrácení (bod 8) a ověřit, že bez opravy padá na `signal only works in main thread`.
- Oprava v `run.py`: rozšířit `_signals_restored()` — když `threading.current_thread() is not threading.main_thread()`, po dobu běhu nahradit `signal.signal` funkcí, která handler neinstaluje a vrátí `signal.getsignal(sig)` (např. `unittest.mock.patch.object(signal, "signal", ...)`), a pod modulovým `threading.Lock`, aby se záměna nepřekrývala. V hlavním vlákně chování beze změny. Komentář: proč (engine váže SIGINT/SIGTERM na běh; mimo hlavní vlákno to Python nedovolí, zabití serveru ukončí běh i bez toho).
- `_run` dělá `os.chdir` (globální pro proces): web proto operace serializuje zámkem (bod 6).

### 6. Web (`prototype/src/haifa_proto/web.py`) — nový soubor

```python
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

def create_app(repo: Path, *, cfg: Any | None = None, code: CodeRunner | None = None,
               provider: GitProvider | None = None) -> Starlette
def serve(repo: Path, host: str, port: int) -> None   # uvicorn.run(create_app(repo), host=host, port=port)
```

Routy:
- `GET /` → `review.open_reviews(repo, provider=provider, cfg=cfg)` → `review.html` s `reviews`, `result=None`. `ReviewError`/`ConfigError` z listování → stránka s chybou (status 500) místo tracebacku.
- `POST /tasks/{task_id}/approve` → `review.approve_task(repo, task_id, provider=provider, cfg=cfg)`.
- `POST /tasks/{task_id}/return` → `note = (await request.form()).get("note", "")` → `review.return_task(repo, task_id, str(note), cfg=cfg, code=code, provider=provider)`.

Oba POSTy: volání přes `starlette.concurrency.run_in_threadpool` pod modulovým (nebo per-app) `threading.Lock` (jedna operace najednou), výstup enginu přesměrovat `contextlib.redirect_stdout(sys.stderr)` jako CLI `--json`. Chytat `(review.ReviewError, run.TaskRunError)`. Poté znovu načíst `open_reviews` a vyrenderovat tutéž šablonu s `result`:
- `result = {"ok": True, "action": "approve", "task_id", "message": f"Schváleno {task_id}: PR {pr.url} sloučeno do {pr.base} ({strategy})", "detail": ApproveResult.to_json()}`.
- Návrat: `ok = TaskRunResult.ok`; message `f"Vráceno {task_id}: běh {run.run_id} {run.state} na {run.branch}"` + `pr_error`/`run.error`, pokud jsou.
- Chyba: `{"ok": False, "action", "task_id", "code", "message"}`.
Status: úspěch 200; `ReviewError`/`TaskRunError` 400; neúspěšný běh návratu (`result.ok` False) 200 s `ok: False` (běh proběhl, jen neprošel).

Handlery neobsahují žádné rozhodování o stavu PR — jen volají core a předávají výsledek do šablony.

### 7. Šablona (`prototype/src/haifa_proto/templates/review.html`) — jediná

Čisté HTML + malé inline CSS, česky, bez JS. Jinja autoescape (výchozí u `Jinja2Templates`).
- Nadpis „HAIFA — review“, blok výsledku (`<div class="result ok|error">` s `message`, u chyby i `code`).
- Prázdný stav: „Žádné otevřené PR.“
- Pro každý `review`: sekce s `task_id` a titulkem; předci jako „module M01 Title · step S01 Title“ (`level id title`); větev; odkaz/URL PR a `provider_state` (+ `provider_error`); diff stat „N souborů, +X −Y“ (nebo „—“); celkové náklady `$%.2f` a tokeny.
- Tabulka běhů: `run_id`, stav, start, poznámka, náklady; pod ním kroky (`step`, `agent`, `harness`, `model`) a kontroly (`gate`/`test`, název, fáze, prošla/neprošla, detail).
- Formulář `POST /tasks/{{ id }}/approve` s tlačítkem **Schválit**; formulář `POST /tasks/{{ id }}/return` s `<textarea name="note" required>` a tlačítkem **Vrátit**.

### 8. CLI (`prototype/src/haifa_proto/cli.py`)

- Nahradit stub: `serve = sub.add_parser("serve", help="start the local review page")`, argumenty `--port` (`int`, default `None`), `--host` (default `127.0.0.1`), `--repo` (`Path`, default `None`).
- V `main`: `repo = args.repo or Path.cwd()`; port = `args.port`, jinak `load_local(run.main_root(repo) nebo repo).port` (při `TaskRunError` z `main_root` použít `repo`); `ConfigError` → `_config_error(exc, False)`. Pak lazy `from haifa_proto import web; web.serve(repo, args.host, port)`; návrat 0. Vypsat `serving http://{host}:{port}` na stderr před startem.

### 9. Testy

`prototype/tests/test_web.py` (TestClient, provider `local`, falešný harness; setup jako `test_cli_task._with_agents_config` — zkopírovat helper nebo ho přesunout do `task_repo.py` jako `with_agents_config` a importovat v obou; web se vytváří `create_app(repo)` bez `cfg`, tedy stejnou cestou jako CLI):

1. `test_get_lists_open_pr`: `main(["task","run",T01,"--repo",repo,"--json"])` s builderem zapisujícím `src/app/h.py`; `GET /` → 200 a v HTML: `T01`, titulek úkolu („Health check“), id modulu a stepu z fixture (`M01`, `S01` — ověř přesná id v `task_repo.py`), `factory/<T01>-1`, diff stat (`1 soubor`/`+1`), `claude` a `sonnet` (harness/model), sekce kontrol, `$`, tlačítka `Schválit` a `Vrátit`, formulářové akce `/tasks/<T01>/approve` a `/return`.
2. `test_get_without_prs`: čerstvé repo → „Žádné otevřené PR.“.
3. `test_post_approve_merges`: po běhu `POST /tasks/<T01>/approve` → 200, stránka obsahuje zprávu o schválení a už nevypisuje PR; `status: done` v `git show main:<TASK_FILE>` (přes `parse_frontmatter` jako `test_pr_flow_local._status`); PR v `task_prs` má `state == "merged"` (`run.task_prs_for`).
4. `test_post_return_runs_again_with_note`: po běhu naskriptovat další builder běh, `POST /tasks/<T01>/return` s `data={"note": "make it 2"}` → 200, ve výsledku nový `run_id`; `"## Note\nmake it 2" in engine_env.script.calls[-1].prompt`; `run.task_runs_for(repo, T01)` má 2 běhy na stejné větvi; PR stále `open` a GET ho vypisuje s oběma běhy.
5. `test_post_return_without_note`: prázdná poznámka → 400, `missing_note` na stránce.
6. `test_post_approve_without_pr`: bez běhu → 400, `no_pr`.

`prototype/tests/test_config.py` (doplnit): `load_local` — bez souboru 4700; `port: 4811` → 4811; `port: "x"`, `port: true`, `port: 0` → `ConfigError`.

`prototype/tests/test_cli.py` nebo `test_web.py`: `monkeypatch.setattr("haifa_proto.web.serve", fake)`; `main(["serve","--repo",repo])` → fake dostal port 4700; s `.factory/local.yaml` `port: 4811` → 4811; `--port 5000` přebije soubor. Testy nikdy nespouští uvicorn.

`prototype/tests/test_task_run.py` nebo nový test: `run_task` spuštěný v `threading.Thread` doběhne (ověřuje bod 5).

## Ověření

Z kořene repa (exit status 0 u všech):
```
just test
just typecheck
just lint
```
Ruční kontrola (nepovinná): `just proto serve --repo <repo s PR>` a otevřít `http://127.0.0.1:4700/`.

## Pevná omezení (připomenutí)

- `vendor/` beze změn. Web nemá vlastní logiku — jen volá `review.open_reviews`, `review.approve_task`, `review.return_task`.
- Testy nevolají model (falešný harness z `workflow_fakes`).
- Stávající testy (zejména PR body v `test_pr_flow_local.py`) musí dál procházet.
