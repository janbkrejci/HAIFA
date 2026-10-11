# Plán: Backlog: graf závislostí, spuštění tasku a přepínač auto-continue

## Zadání

Doplnit obrazovku Backlog v dashboardu o:

1. **Graf závislostí** modulu nebo stepu: uzly jsou tasky se stavem (`board_state`), hrany jsou `depends_on`. Klik na uzel otevře detail tasku.
2. **Tlačítko Spustit** v detailu tasku s volitelnou poznámkou. Volá stejnou core funkci jako `factory task run`, tedy `aifactory.run.run_chain`. Před spuštěním UI ukáže:
   - varování na necommitnutou konfiguraci `.factory/` (D4, stejná data jako `factory config status`),
   - nesplněné závislosti s volbou „Spustit přesto“ (`force=True`, odpovídá `--force`).
3. **Přepínač auto-continue** u modulu a stepu. Zapisuje přes `aifactory.backlog.set_auto_continue` stejně jako `factory backlog auto-continue ID --on|--off|--inherit`.
4. Běh spuštěný z UI **běží na pozadí serveru** (vlákno) a server přitom dál odpovídá.
5. Testy API s falešným harnessem: spuštění z API vytvoří řádek v `task_runs`.
6. `just test`, `just typecheck` a `just lint` projdou.

Mimo rozsah: plánovač napříč moduly.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.
- Měnit se smí jen `aifactory/src/aifactory/web/` (včetně `static/` z buildu), `aifactory/web/src/` a `aifactory/tests/web/`.
- Core (`aifactory/run`, `aifactory/backlog`, `aifactory/config`, `aifactory/skill/codes.py`) se **nemění**. Proto se nezavádějí nové chybové kódy a používají se jen ty, které už jsou v `skill/codes.py`.

## Co je potřeba vědět o core (zjištěno)

- `aifactory.run.run_chain(repo, task_id, *, auto=False, note=None, force=False, code=None, provider=None) -> ChainResult` volá CLI `factory task run` (`cli.py::_task_run`). První `TaskRunError` (například `unmet_dependencies`, `already_running`, `no_writes`, `unknown_task`, `task_not_in_base`, `invalid_config`, `invalid_workflow`) se propaguje dřív, než vznikne řádek v `task_runs`. Pak následuje `store.claim(row)` (stav `running`, `pid=os.getpid()`, `note`) a samotný běh.
- `run_task` dělá `os.chdir(worktree)` a vrací cwd zpět. Cwd je **globální pro celý proces**, takže dva běhy ve vláknech téhož procesu se nesmí překrývat (gates podle komentáře v `engine/gates.py` spoléhají na cwd). Mimo hlavní vlákno `_signals_restored` handlery signálů sám neutralizuje, s tím se nic dělat nemusí.
- `stop_run` už počítá s během ve vlastním procesu: `if row.pid == os.getpid()` sebe nezabije (`run/stop.py:113`). Tlačítko Stop na obrazovce Běhy tedy u běhu spuštěného z UI jen označí běh `stopped` a pošle SIGTERM agentům. To stačí.
- D4:
  - `aifactory.config.worktree_base(root)` vrací `base`,
  - `resolve_commit(root, base)` vrací sha,
  - `config_changes(root, sha)` vrací `list[ConfigChange]` (`to_dict()`: `path`, `status`),
  - `change_warnings(changes, base, sha)` vrací texty varování.
  - Celé to dělá `cli.py::_config_status`.
- Nesplněné závislosti kontroluje `run_task` proti backlogu **z base commitu**:
  - `gitops.extract_backlog(main, rc.commit, settings.backlog_dir, dest)`,
  - `load_backlog(dest, settings)`,
  - `aifactory.backlog.unmet(backlog, task)` vrací `list[Unmet]` (`to_dict()`).
  - `rc = aifactory.config.load_run_config(main)`, `main = aifactory.run.gitops.main_root(repo)`.
  - `ConfigError` z `load_run_config` převést na `TaskRunError("invalid_config", str(exc))` stejně jako `run/task.py::_load`.
- Auto-continue:
  - `aifactory.backlog.set_auto_continue(root, container_id, enabled: bool | None) -> ContainerWriteResult` (`changed`, `path`, `container`, `backlog`, `issues`).
  - Chyby: `TaskEditError` s kódem `unknown_container`, `no_index` nebo `backlog_invalid`.
  - JSON výstup CLI (`cli.py::_backlog_auto_continue`): `{changed, id, level, path, auto_continue, issues}`.
  - Vlastní hodnota kontejneru je `container.defaults.get("auto_continue")`. Efektivní hodnotu tasku vrací `aifactory.run.auto_continue_enabled(task)`.
- `envelope_problems` nekontroluje, zda je kód registrovaný. Přesto se použijí jen existující kódy.

## Backend

### 1. Nový soubor `aifactory/src/aifactory/web/launcher.py`: běh na pozadí

```python
"""Start a task run from the dashboard on a background thread of the server.

`RunLauncher.start` calls `aifactory.run.run_chain`, the function behind `factory task run`,
on a daemon thread and waits (off the event loop) until the run is claimed in `task_runs`
or failed to start. `run_task` changes the process cwd, so a server runs one dashboard chain
at a time; a second start gets `already_running`. CLI runs in other processes are unaffected.
"""
```

- `class RunLauncher` s atributy `_lock: threading.Lock`, `_thread: threading.Thread | None`, `_task_id: str | None`, `last_error: BaseException | None`, `last_result: ChainResult | None`.
- `start(repo: Path, task_id: str, *, note: str | None, force: bool, timeout: float = 30.0) -> TaskRunRow | None`:
  1. Pod `_lock`: pokud `_thread` žije, vyhodit `TaskRunError("already_running", f"a run started from the dashboard is still running (task {self._task_id}); wait for it to finish or use factory task run")`.
  2. Snapshot: `known = {r.run_id for r in task_runs_for(repo, task_id)}`. Při `sqlite3.Error` nebo chybějící DB brát prázdnou množinu. `task_runs_for` vrací `[]`, pokud DB neexistuje; ověřit a jinak ošetřit.
  3. Vytvořit `threading.Thread(target=self._work, args=(repo, task_id, note, force), daemon=True, name=f"factory-run-{task_id}")` a spustit ho.
  4. Poll smyčka co 0,05 s až do `timeout`:
     - když se v `task_runs_for(repo, task_id)` objeví řádek s `run_id not in known`, vrátit ho;
     - když vlákno skončilo s chybou `TaskRunError`, vyhodit tu chybu (jiné výjimky zabalit do `TaskRunError("internal_error" …)`; kód `internal_error` v registru už je);
     - když vlákno skončilo bez chyby a bez nového řádku, znovu přečíst řádky (mohl proběhnout rychle) a případně vrátit nejnovější nový;
     - po timeoutu vrátit `None` (běh se spouští dál, UI ukáže „spouští se“).
- `_work`: `try: self.last_result = aifactory.run.queue.run_chain(repo, task_id, note=note, force=force)`. Volat přes atribut modulu (`from aifactory.run import queue as run_queue; run_queue.run_chain(...)`), aby šel v testech případně patchnout. `except BaseException as exc: self.last_error = exc`, u ne-`TaskRunError` navíc `traceback.print_exc()` na stderr.
- `busy() -> bool` a `wait(timeout: float | None = None) -> None` (join vlákna; potřebují ho testy a případně shutdown).
- Stdout enginu se **nepřesměrovává** (`redirect_stdout` je globální pro proces). Engine vypráví do terminálu serveru. Poznamenat to v docstringu.
- `note`: prázdný nebo jen z mezer text normalizovat na `None`.

### 2. `aifactory/src/aifactory/web/backlog.py`: nové funkce

**a) `run_check(repo, task_id) -> tuple[JsonDict, list[str]]`** (varování před spuštěním):
- `task = core.find_task(core.load_for_edit(repo), task_id, issues)`. Při neznámém tasku vyhodit `unknown_task` stejně jako `task_detail`.
- Config (D4):
  - `root = gitops.main_root(repo)`, `base = worktree_base(root)`, `sha = resolve_commit(root, base)`, `changes = config_changes(root, sha)`.
  - Výstup `config = {"base", "commit", "clean", "changes": [c.to_dict()]}`.
  - Při `ConfigError` nastavit `config = None` a přidat varování `f"config status: {exc}"`.
- Nesplněné závislosti proti base:
  - v `tempfile.TemporaryDirectory` provést `rc = load_run_config(main)` (při `ConfigError` vyhodit `TaskRunError("invalid_config", …)`), `gitops.extract_backlog(...)` a `load_backlog(dest, rc.config.settings)`;
  - `base_task = base.by_id.get(task_id)`; pokud to není `Task`, nastavit `in_base = False` a `unmet = []`;
  - jinak `unmet = [u.to_dict() for u in core.unmet(base, base_task)]`.
- Běžící běh: `running` jako `to_json()` řádku se stavem `running` z `existing_store(repo)` (`store.running(task_id)`), jinak `None`.
- Data: `{"task_id", "config", "in_base", "unmet", "running", "launcher_busy"}`. Varování: `change_warnings(...)` a případné problémy. Funkce dostane `launcher_busy: bool` parametrem z handleru.

**b) `start_run(repo, task_id, body, launcher) -> tuple[JsonDict, list[str]]`**:
- `_check_keys(body, ("note", "force"))`, `note = _opt_str(body, "note")`, `force = _opt_bool(body, "force")`.
- `row = launcher.start(repo, task_id, note=note, force=force)`.
- Data: `{"task_id", "run": row.to_json() if row else None, "pending": row is None, "force": force}`.

**c) `container_graph(repo, container_id) -> tuple[JsonDict, list[str]]`**:
- Najít kontejner přes `core.iter_containers(backlog.containers)` podle `id`. Když chybí, vyhodit `core.TaskEditError("unknown_container", f"no module or step '{container_id}'", id=container_id)`.
- Tasky podstromu: rekurzivně `container.tasks` a `children`. Zahrnout všechny, i `done` a `cancelled`, protože stav se zobrazí.
- `rt, warnings = _runtime(repo)`.
- Uzly tasků: `{"id", "title", "kind": "task", "board_state", "step": <id nejbližšího rodičovského kontejneru>, "external": False}`.
- Pro každou `dep` v `task.depends_on` přidat hranu `{"from": dep, "to": task.id}`. Pokud `dep` není uzel podstromu, přidat uzel přes `_depends_ref(backlog, dep, rt)`: `kind` je `task`, `container` nebo `unknown`, `state` nastavit jako `board_state` a `external=True`. U externího tasku je `board_state` jeho skutečný stav. U kontejneru nebo neznámého uzlu je v `board_state` text stavu (`"done"`, `"2/5"` nebo `"unknown"`), proto do uzlu přidat pole `state` a `board_state` nastavit na `None`.
- Data kontejneru:

  ```json
  {"id", "title", "level", "path",
   "auto_continue": <vlastní bool|None>,
   "effective_auto_continue": <bool, první bool od kontejneru přes parent řetěz, jinak False>,
   "can_toggle": container.index_path is not None}
  ```

- Výstup: `{"container": …, "nodes": [...], "edges": [...]}` s deterministickým pořadím: tasky podle `path`, externí uzly podle id.

**d) `auto_continue(repo, container_id, body) -> tuple[JsonDict, list[str]]`**:
- `_check_keys(body, ("mode",))`, `mode = _req_str(body, "mode")`.
- Když `mode` není `on`, `off` ani `inherit`, vyhodit `core.TaskEditError("invalid_value", "'mode' must be on, off or inherit")`.
- `result = core.set_auto_continue(repo, container_id, {"on": True, "off": False, "inherit": None}[mode])`. Ověřit, že je `set_auto_continue` exportovaný z `aifactory.backlog` (je v `__all__`).
- Data stejná jako u CLI JSON: `{changed, id, level, path, auto_continue, issues}` a navíc `effective_auto_continue`. Varování přes `_warnings(result.issues)`.

**e)** Do `_container_json` přidat `"auto_continue"` (vlastní bool nebo `None`), aby strom mohl ukázat indikátor. Změna je jen aditivní, existující testy nerozbije.

Pomocnou funkci `_effective_auto(container)` (walk přes `parent`) použít v c), d) i e).

### 3. `aifactory/src/aifactory/web/app.py`: routy a handlery

- V `create_app` nastavit `app.state.launcher = RunLauncher()`.
- Routy (v `Mount("/api")`):
  - `GET  /backlog/tasks/{task_id}/run-check` → `backlog_run_check`
  - `POST /backlog/tasks/{task_id}/run` → `backlog_run`
  - `GET  /backlog/containers/{container_id}/graph` → `backlog_graph`
  - `POST /backlog/containers/{container_id}/auto-continue` → `backlog_auto_continue`
- Všechny handlery jsou `async` a práci volají přes `await run_in_threadpool(...)`, protože git a čekání blokují. `backlog_run` tak čeká na `launcher.start` mimo event loop a server dál odpovídá.
- Chyby: `(TaskEditError, ConfigError, TaskRunError)` → `_edit_error`, `backlog.UsageError` → `_usage_error`.
- Do `_RUN_ERROR_STATUS` přidat:
  - `already_running: 409`, `unmet_dependencies: 409`, `task_not_in_base: 409`,
  - `no_writes: 422`, `no_workflow: 422`, `unknown_workflow: 422`, `invalid_workflow: 422`,
  - `unknown_task: 404`, `worktree_failed: 500`.
- Do `_EDIT_ERROR_STATUS` přidat `unknown_container: 404`, `no_index: 409`, `invalid_value: 400`.
- Úspěšný `POST .../run` vrací HTTP **202**.
- Doplnit docstring modulu o nové endpointy a o to, že běh jde přes `run_chain` na pozadí, jeden dashboardový chain najednou.
- Ve web kódu nepoužívat `Path.cwd()`, všude `request.app.state.repo`, protože běh mění cwd procesu.

## Frontend (`aifactory/web/src/`)

### 4. `lib/backlog.ts`

- Typy:
  - `RunCheck { task_id; config: { base; commit; clean; changes: {path; status}[] } | null; in_base: boolean; unmet: Unmet[]; running: TaskRun | null; launcher_busy: boolean }`
  - `RunStart { task_id; run: TaskRun | null; pending: boolean; force: boolean }`
  - `GraphNode { id; title: string | null; kind: 'task'|'container'|'unknown'; board_state: BoardState | null; state?: string; step?: string | null; external: boolean }`
  - `GraphEdge { from; to }`
  - `ContainerGraph { container: { id; title; level; path; auto_continue: boolean | null; effective_auto_continue: boolean; can_toggle: boolean }; nodes; edges }`
  - `AutoMode = 'on'|'off'|'inherit'`
  - `AutoContinueResult`
- `ContainerNode` doplnit o `auto_continue?: boolean | null`.
- Funkce `fetchRunCheck(id)`, `startRun(id, {note?, force?})`, `fetchGraph(containerId)` a `setAutoContinue(containerId, mode)` stavějí na existujících `getApi`/`postApi`.
- `autoMode(value: boolean | null): AutoMode`.

### 5. `lib/graph.ts` (nový, čistá logika, bez nových závislostí)

- `layoutGraph(nodes, edges) -> { nodes: (GraphNode & {x, y, layer})[], edges: {from, to, points}[], width, height }`.
- Vrstva uzlu je nejdelší cesta od kořene: relaxace nejvýš `nodes.length` průchodů, takže je odolná vůči cyklům (backlog check je hlásí, graf nesmí zamrznout). Hrany na neexistující uzel se zahodí.
- V rámci vrstvy řadit podle vstupního pořadí.
- Konstanty: šířka uzlu 200 px, výška 44 px, rozestup sloupců 80 px, rozestup řádků 16 px.
- `lib/graph.test.ts`: řetězec A→B→C dá vrstvy 0, 1, 2; nezávislé uzly skončí ve vrstvě 0; cyklus A↔B skončí bez zacyklení; hrana na chybějící uzel se zahodí.

### 6. `lib/router.ts`

- `export const GRAPH = 'graph'` a `graphHref(containerId)`, které vrací `#/backlog/graph/<id>`.
- Rozšířit `router.test.ts`.

### 7. Komponenty

- **`components/backlog/DependencyGraph.vue`**:
  - props `graph: ContainerGraph`;
  - SVG z `layoutGraph`: hrany jako `<path>` s šipkou (`<marker>`), uzly jako `<g>` s `<rect>` obarveným podle `board_state` (barvy převzít ze `StateChip.vue` nebo CSS proměnných) a textem `id` a `title` (zkrácený);
  - uzel tasku je obalený v `<a :href="taskHref(id)" data-test="graph-node" :data-node="id">`, takže klik otevře detail;
  - externí uzly mají čárkovaný okraj, kontejnery a neznámé uzly ukazují text `state` a nejsou klikací;
  - legenda stavů (`STATE_LABELS`), prázdný graf ukáže „Žádné tasky“.
  - Test `DependencyGraph.test.ts`: vykreslí uzly a hrany (počet `path.edge`), uzel tasku má `href` `#/backlog/<id>`, stavová třída odpovídá `board_state`.
- **`components/backlog/AutoContinueToggle.vue`**:
  - props `mode: AutoMode`, `effective: boolean`, `busy`, `disabled`; emit `change: [AutoMode]`;
  - tři tlačítka nebo segment: „Zděděno“, „Zapnuto“, „Vypnuto“ (`data-test="auto-on|off|inherit"`), vedle text „efektivně: zapnuto/vypnuto“.
  - Test: klik emituje správný mode a aktivní volba je zvýrazněná.
- **`components/backlog/RunDialog.vue`** (panel v detailu tasku):
  - props `check: RunCheck | null`, `loading`, `busy`, `error: WriteError | null`, `result: RunStart | null`; emit `start: [{ note?: string; force: boolean }]` a `cancel`;
  - textarea „Poznámka (volitelná)“ (`data-test="run-note"`);
  - blok D4 (`data-test="config-warning"`), když `check.config && !check.config.clean`: „Konfigurace .factory/ má necommitnuté změny, běh použije verzi z {base} ({commit[:7]})“ a seznam `status path`;
  - blok závislostí (`data-test="unmet-warning"`) se seznamem `unmet` (`id — reason`);
  - `!in_base` → varování „Task není commitnutý v base“;
  - `running` → info s odkazem `runHref(running.run_id)` a zakázané spuštění;
  - `launcher_busy` → info „Z dashboardu už běží jiný běh“;
  - tlačítka:
    - „Spustit“ (`data-test="run-start"`) je zakázané, když `unmet.length`, `running` nebo `busy`;
    - „Spustit přesto (--force)“ (`data-test="run-force"`) se zobrazí, když `unmet.length`, nebo když `error` má kód `unmet_dependencies`, protože base se mohl změnit mezi check a startem. `WriteError` na to rozšířit o volitelné `code` ve `flattenIssues`;
  - po úspěchu ukáže „Běh {run_id} spuštěn“ s odkazem `runHref`, nebo „spouští se…“ při `pending`.
  - Test `RunDialog.test.ts`: s D4 změnami je vidět varování; s `unmet` je „Spustit“ zakázané a „Spustit přesto“ emituje `force: true` s poznámkou; bez varování „Spustit“ emituje `force: false`.
- **`TaskDetail.vue`**:
  - v hlavičce tlačítko „Spustit“ (`data-test="run"`) emituje `open-run`;
  - nové props `run: { open, check, loading, busy, error, result }` (nebo samostatné props) a vykreslení `RunDialog`;
  - emitovat `run-start` a `run-cancel`.
  - Upravit `TaskDetail.test.ts`: tlačítko existuje a emituje.
- **`TreeNode.vue`**:
  - u kontejneru s `id` přidat odkaz „Graf“ (`graphHref(node.id)`, `data-test="graph-link"`);
  - když `node.auto_continue === true`, malý štítek „auto“ (`data-test="auto-badge"`).
  - Rozšířit `BacklogTree.test.ts`.
- **`views/BacklogView.vue`**:
  - `isGraph = target === GRAPH`, `graphId = params[1] ?? null`; `taskId` musí vyloučit `NEW_TASK` i `GRAPH`;
  - graf: načíst `fetchGraph(graphId)` a vykreslit hlavičku (level, id, title), `AutoContinueToggle` (jen když `can_toggle`), `DependencyGraph` a chybu přes `IssueList` (`flattenIssues`);
  - změna auto-continue zavolá `setAutoContinue` a znovu načte graf;
  - spuštění:
    - `openRun()` otevře panel a načte `fetchRunCheck(taskId)`;
    - `onRunStart({note, force})` volá `startRun(taskId, {note: note || undefined, force})`, výsledek uloží do `runResult` a znovu načte detail (runs, `board_state` = running);
    - chybu uloží do `runError` (s `code`);
  - `watch(target)` rozšířit i o `params[1]` (sledovat `params.value.join('/')`), aby přechod mezi grafy znovu načítal.
  - Upravit `BacklogView.test.ts`: routa `#/backlog/graph/M01` volá `/api/backlog/containers/M01/graph`; toggle volá POST `auto-continue` s `{"mode":"on"}`; Spustit → run-check → POST run s `note` a `force`. Mock `fetch` stejně jako stávající testy a fixtures dát do `test/backlogFixtures.ts`.

Texty UI jsou česky s diakritikou, v souladu se stávajícími obrazovkami.

### 8. Build

Po změnách frontendu spustit `just web-build`. `vite` s `emptyOutDir` přegeneruje `aifactory/src/aifactory/web/static/`. Nový bundle je součástí změny: staré hashované soubory v `static/assets` zmizí a nové se přidají.

## Testy backendu (`aifactory/tests/web/`)

### 9. `tests/web/test_web_task_run.py` (nový): falešný harness, žádný model

- Import helperů z `tests/run` stejně jako `tests/run/run_repo.py` importuje `tests/workflow`:

  ```python
  sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))
  from run_repo import T01, T02, Script, commit_all, fake_env, git, make_run_repo, ok, write  # noqa: E402
  ```

  `ruff` E402 řešit přes `# noqa: E402` jako v `run_repo.py`.
- Fixtures:
  - `script` = `yield from fake_env(monkeypatch)`;
  - `repo` = `make_run_repo(tmp_path / "repo")`;
  - klient `TestClient(create_app(repo, static_dir=tmp_path / "nostatic"), base_url="http://127.0.0.1:4700")`.
- Pomocná funkce `wait(app)` volá `app.state.launcher.wait(timeout=60)` a ověří `not launcher.busy()`. Volat ji v každém testu, který běh spustí, i ve `finally`, aby vlákno nepřežilo `fake_env` teardown (ten vrací cwd a signály).
- Testy:
  1. `test_run_from_api_creates_task_run`: planner zapíše `src/app/model.py` a vrátí `ok(artifacts=[], changed_files=[...], commit_message=...)`, vzor je `build()` v `tests/run/test_auto_continue.py`. `POST /api/backlog/tasks/M01-S01-T01/run` s `{"note": "z UI"}` vrátí 202, `data.run.task_id == T01`, `data.run.state == "running"` a `envelope_problems == []`. Po `wait` má `TaskRunStore(repo/".factory"/"trace.db").for_task(T01)` právě 1 řádek, `note == "z UI"` a `state == "succeeded"`.
  2. `test_server_answers_while_run_is_going`: effect planneru čeká na `threading.Event` (s timeoutem 30 s, aby test nezamrzl). Po POST run ověřit, že `GET /api/health` vrátí 200 a `GET /api/runs?task=T01` ukáže běh `running`. Pak `event.set()`, `wait`, a stav je `succeeded`.
  3. `test_second_dashboard_run_is_refused`: během blokovaného běhu vrátí `POST .../M01-S01-T02/run` s `{"force": true}` HTTP 409 `already_running`.
  4. `test_unmet_dependencies_and_force`:
     - `GET .../M01-S01-T02/run-check` vrátí `unmet[0].id == T01`, `in_base` true a `config.clean` true;
     - `POST .../T02/run` bez force vrátí 409 `unmet_dependencies` a v `task_runs` pro T02 nic nevznikne;
     - s `{"force": true}` vrátí 202 a po `wait` existuje řádek.
  5. `test_run_check_reports_uncommitted_config`: dopsat řádek do `.factory/config.yaml` nebo přidat necommitnutý soubor `.factory/workflows/x.yaml`. `run-check` pak vrátí `config.clean is False`, změna je v `changes` a ve `warnings` je text z `change_warnings`.
  6. `test_run_rejects_unknown_fields`: `{"bogus": 1}` vrátí 400 `usage_error`; `{"force": "yes"}` vrátí 400 `invalid_value`; neznámý task vrátí 404 `unknown_task`.

  Soubor označit `pytestmark = pytest.mark.xdist_group("web_task_run")`, pokud to kvůli globálnímu cwd a signálům používají podobné testy v `tests/run` (ověřit tam a řídit se tím).

### 10. `tests/web/test_web_backlog.py` (rozšířit, bez harnessu) nebo nový `test_web_backlog_graph.py`

Nad `make_backlog_repo` z `backlog_fixture.py` (zjistit, jaké kontejnery a závislosti obsahuje: `A1..A4`, `B1..B3`, `S1`, `S2`):
- graf stepu vrátí uzly jen z podstromu a hrany `depends_on`; závislost mimo podstrom je uzel s `external: true`; `board_state` odpovídá `GET /api/backlog`;
- graf modulu obsahuje tasky všech jeho stepů;
- neznámý kontejner vrátí 404 `unknown_container`;
- `POST .../auto-continue` s `{"mode":"on"}` zapíše do `index.md` `auto_continue: true` (ověřit přes `aifactory.backlog.load_backlog` a `container.defaults`), vrátí `changed: true` a `auto_continue: true`; opakování vrátí `changed: false`. `off` zapíše `false`, `inherit` klíč odstraní. Výsledek musí být stejný jako `factory backlog auto-continue ID --on --json` (porovnat obsah `index.md` po CLI v kopii repa, nebo aspoň stejná pole dat). `{"mode":"maybe"}` vrátí 400 `invalid_value`. Nic se necommitne (`git status` ukazuje jen `index.md`);
- `GET /api/backlog` obsahuje u kontejnerů klíč `auto_continue`.

## Ověření

```bash
just test        # pytest (celá sada) + web-test (vue-tsc + vitest)
just typecheck   # mypy
just lint        # ruff check + ruff format --check
just web-build   # přegenerovat static bundle
```

Všechny příkazy se posuzují podle exit kódu. Ručně (volitelně): `just dash`, na Backlogu otevřít „Graf“ u stepu, kliknout na uzel, přepnout auto-continue a zkontrolovat `git diff` v `index.md`.

## Rizika a rozhodnutí

- **Jeden dashboardový běh najednou.** Důvodem je globální `os.chdir` v `run_task` (a cwd, na kterém závisí gates). Druhý start z UI vrátí `already_running` (409). Paralelní běhy jdou dál přes CLI v jiných procesech. Plánovač přes moduly je mimo rozsah.
- Daemon vlákno: při ukončení serveru se běh přeruší. Řádek zůstane `running` s pid serveru, store podle `_alive` pozná mrtvý proces a `factory task clean` uklidí. Poznamenat to v docstringu `launcher.py`.
- Žádná změna core ani `skill/codes.py`: nové chybové kódy se nezavádějí.
