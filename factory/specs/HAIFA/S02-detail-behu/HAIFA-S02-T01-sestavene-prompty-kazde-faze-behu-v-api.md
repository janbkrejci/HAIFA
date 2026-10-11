# HAIFA-S02-T01 — Sestavené prompty každé fáze běhu v API

## Problém

`engine/agents.py::execute` ukládá vykreslené prompty do
`<session_dir>/<agent>/prompts/{system,user}.md`. Další fáze téhož agenta
(build → revise_1, review_1 → review_2) soubory přepíše, takže pro dřívější fázi
zůstane jen prompt té poslední. Dashboard prompty fází vůbec nevidí.

## Cíl

1. Engine navíc uloží prompty každé fáze zvlášť:
   `<session_dir>/<agent>/prompts/phases/<phase_name>/{system,user}.md`
   (`phase_name` = `phase.params.name`, unikátní v rámci běhu, např. `build`,
   `revise_1`). Dnešní `<agent>/prompts/{system,user}.md` se zapisují dál beze změny.
2. `GET /api/runs/{run_id}/phases/{phase_id}/prompts` vrací system a user prompt fáze.
3. Session adresář se odvozuje z konfigurace běhu (`data_dir` z `.factory/agents.yaml`,
   výchozí `.factory/data`) přes existující `run/task.py::data_dir`, ne z umístění trace DB.

Mimo rozsah: UI, `context_handoff/`, `raw_output.jsonl`. `vendor/` a `prototype/` se nemění.

## Kontext (co už existuje)

- `engine/runner.py:88` — `phase_id = f"{adw_id}_{seq:02d}_{params.name}"`; tabulka
  `phases` v trace DB má sloupce `phase_id, adw_id, seq, name, kind, owner, …`.
  `owner` je u agentní fáze jméno agenta = jméno adresáře `<session_dir>/<owner>/`.
- `engine/runner.py:55` — `session_dir = <cfg.defaults.data_dir>/sessions/<adw_id>`.
- `run/task.py:220` — `data_dir(main, rc)`; `run/task.py:508` —
  `session_dir = data_dir(main, rc) / "sessions" / row.run_id` (run_id == adw_id).
- `run/task.py:345` — `_load(main)` (RunConfig, chyba → `TaskRunError("invalid_config")`);
  `run/task.py:625` — `existing_store(repo)` ukazuje, jak získat `main` přes
  `gitops.main_root(repo)` s fallbackem na `repo.resolve()`.
- `web/runs.py` — `_open_run(repo, run_id)` (unknown_run → 404), `_has_table`, `_rows`.
- `web/app.py` — `_RUN_ERROR_STATUS` (řádek ~98: `unknown_run: 404`, `invalid_value: 400`),
  `_run_error`, handlery `run_detail` apod., routy kolem řádku 613.
- Vzor: `vendor/sssf/apps/visualizer/server/index.ts` route
  `/api/sessions/:adw_id/agents/:agent/prompts` (segment check, containment check,
  chybějící soubor = `null`).

## Změny

### 1. `aifactory/src/aifactory/engine/prompts.py`

Přidat (s komentářem `# aifactory 2.10:` — značka `# aifactory` je povinná u každé
změny logiky v `engine/`; použij stejný styl jako `# aifactory 2.9:`):

```python
PHASES_DIR = "phases"  # aifactory 2.10: <agent>/prompts/phases/<phase>/ — one copy per phase

def phase_dir(prompts_dir: str | Path, phase_name: str) -> Path:
    """aifactory 2.10: where one phase's prompts live, so a later phase of the same
    agent does not overwrite them."""
    return Path(prompts_dir) / PHASES_DIR / phase_name
```

`render` a `save` se nemění.

### 2. `aifactory/src/aifactory/engine/agents.py` (`execute`, ř. ~115–118)

Za dva stávající `prompts.save(...)` přidat:

```python
    # aifactory 2.10: each phase keeps its own copy; the agent-level files above stay
    # (last phase wins there) for readers that know only them.
    phase_prompts = prompts.phase_dir(agent_dir / "prompts", phase.params.name)
    prompts.save(phase_prompts, "system.md", system_text)
    prompts.save(phase_prompts, "user.md", user_text)
```

Nic jiného v engine neměnit. (Jméno fáze je kódem daný krátký identifikátor; pokud
by obsahovalo `/` nebo `..`, API ho stejně odmítne — viz níže.)

### 3. `aifactory/src/aifactory/run/task.py`

Přidat veřejnou funkci (poblíž `data_dir`/`existing_store`):

```python
def session_dir_of(repo: Path, run_id: str) -> Path:
    """The session directory of run `run_id`: ``<data_dir>/sessions/<run_id>``.

    Resolved from the run config of the main checkout (agents.yaml ``data_dir``, else
    ``.factory/data``), the same way `_execute` lays it out — never next to the trace DB.
    """
    try:
        main = gitops.main_root(repo)
    except TaskRunError:
        main = repo.resolve()
    return data_dir(main, _load(main)) / "sessions" / run_id
```

Volitelně refaktor `_execute` (ř. 508), aby používal stejný výraz — není nutné.
Ověř, že `load_run_config` funguje i v testovém repu, které má jen
`.factory/config.yaml` (fixture `make_repo`); pokud ne, test připraví minimální
`.factory/agents.yaml`.

### 4. `aifactory/src/aifactory/web/runs.py`

Nové konstanty a funkce:

```python
MAX_PROMPT_BYTES = 256 * 1024
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
```

- `_safe_segment(value: str) -> bool` — `_SAFE_ID.fullmatch(value)` a zároveň
  `".." not in value` (stačí zákaz `..`; `/`, `\`, NUL regex nepustí).
- `_read_prompt(root: Path, path: Path) -> tuple[str | None, bool]`:
  - `root_r = root.resolve()`, `target = path.resolve()` (resolve řeší i symlinky);
    pokud `not target.is_relative_to(root_r)` → `(None, False)` (cesta ven ze session
    adresáře se nikdy nečte).
  - `not target.is_file()` → `(None, False)`.
  - čte binárně max. `MAX_PROMPT_BYTES + 1` bajtů (`open(...,"rb").read(n)`); pokud
    je delší, ořízne na `MAX_PROMPT_BYTES` a vrací `truncated=True`;
    `decode("utf-8", errors="replace")`. `OSError` → `(None, False)`.
- `phase_prompts(repo: Path, run_id: str, phase_id: str) -> tuple[JsonDict, list[str]]`:
  1. Pokud `run_id` nebo `phase_id` neprojde `_safe_segment` →
     `raise TaskRunError("invalid_value", "invalid run_id or phase_id")` (→ 400).
     Validace PŘED otevřením DB.
  2. `store, row = _open_run(repo, run_id)` (neznámý běh → `unknown_run` 404); v
     `try/finally store.close()` načíst fázi:
     `SELECT phase_id, name, kind, owner FROM phases WHERE adw_id = ? AND phase_id = ?`
     (pokud tabulka `phases` neexistuje nebo řádek není →
     `raise TaskRunError("unknown_phase", f"no phase {phase_id} in run {run_id}")`).
  3. `session = session_dir_of(repo, run_id)` (import z `aifactory.run.task`).
  4. Pokud `owner` nebo `name` neprojde `_safe_segment` → `source = "none"`, oba
     prompty `None`, warning `"phase owner/name is not a safe path segment"`.
  5. Jinak:
     - `phase_dir = session / owner / "prompts" / "phases" / name`;
       přečti `system.md`, `user.md`. Pokud aspoň jeden existuje (není None) →
       `source = "phase"`.
     - jinak fallback `agent_dir = session / owner / "prompts"`; přečti
       `system.md`, `user.md`; pokud aspoň jeden existuje → `source = "agent"`
       (starší běh bez promptů po fázích).
     - jinak `source = "none"` (např. code fáze, smazaná session).
     Pro `kind == "code"` lze rovnou vrátit `source = "none"` bez čtení.
  6. Vrátit:
     ```json
     {
       "run_id": "...", "phase_id": "...", "phase": "<name>", "agent": "<owner>",
       "kind": "agent|code|...",
       "source": "phase" | "agent" | "none",
       "legacy": true|false,          // true právě když source == "agent"
       "system": "<text>" | null,
       "user": "<text>" | null,
       "truncated": {"system": bool, "user": bool},
       "max_bytes": 262144
     }
     ```
     Warnings: při `source == "agent"` přidat
     `"run has no per-phase prompts; showing the agent's last prompts"`.
  Aktualizuj docstring modulu (zmínit čtení session adresáře).

### 5. `aifactory/src/aifactory/web/app.py`

- Do `_RUN_ERROR_STATUS` přidat `"unknown_phase": 404` (`invalid_value: 400` už je).
- Handler:
  ```python
  def run_phase_prompts(request: Request) -> JSONResponse:
      repo: Path = request.app.state.repo
      try:
          data, warnings = runs.phase_prompts(
              repo, request.path_params["run_id"], request.path_params["phase_id"]
          )
      except (TaskRunError, ConfigError) as exc:
          return _run_error(exc)
      return JSONResponse(envelope_ok(data, warnings))
  ```
- Route: `Route("/runs/{run_id}/phases/{phase_id}/prompts", run_phase_prompts, methods=["GET"])`
  vedle ostatních `/runs/...` rout.
- Doplnit endpoint do docstringu modulu (seznam endpointů nahoře).
- Zkontroluj, že `TaskRunError` z `phase_prompts` s kódem `invalid_value` opravdu
  dává 400 přes `_run_error` (mapa `_RUN_ERROR_STATUS`).

### 6. Testy

#### `aifactory/tests/engine/test_phase_prompts.py` (nový; falešný harness z `engine_fakes`)

Importy jako v `test_task_run_hooks.py`
(`from engine_fakes import EngineEnv, engine_env_fixture, start  # noqa: F401`).
Fáze pro stejného agenta s různými jmény si postav přímo přes `PhaseParams` +
`run.phase(...)` + `ph.call(AgentCall(output_type=GenericOutput, prompt=...))`
(helper `agent_phase` dává `name=owner`, takže potřebuješ vlastní variantu s
parametrem `name`, nebo do `engine_fakes.agent_phase` přidej volitelný `name=`).

- `test_each_phase_keeps_its_own_prompts`: agent `free` (nebo jiný z fake configu),
  dvě fáze `build` (prompt "build it") a `revise_1` (prompt "fix it"); ověř, že
  `<run.session_dir>/free/prompts/phases/build/user.md` obsahuje "build it",
  `.../revise_1/user.md` "fix it", oba `system.md` existují, a
  `<run.session_dir>/free/prompts/user.md` obsahuje "fix it" (agentní kopie zůstává).

#### `aifactory/tests/web/test_web_phase_prompts.py` (nový)

Fixture: `make_trace_db(tmp_path / "repo", os.getpid())` z `trace_fixture`
(běh `r-ok` má fáze `p1` = plan/agent/planner, `p2` = test/code/tests).
Session dir v testech vždy získej přes `aifactory.run.task.session_dir_of(repo, run_id)`
NEBO, pro test konfigurace, zapiš `.factory/agents.yaml` s `defaults: data_dir: <x>`
(zjisti v `config/loader.py`, jaký tvar agents.yaml vyžaduje). Do trace DB dopiš
podle potřeby další fáze (`sqlite3` INSERT do `phases`, vzor v `trace_fixture.py`).
Klient jako v `test_web_runs.py` (`create_app(root, static_dir=...)`, `envelope_problems`).

1. `test_build_and_revise_of_one_agent_differ`: vlož fáze `pb` (name `build`, owner
   `builder`, kind `agent`) a `pr` (name `revise_1`, owner `builder`) pro `r-ok`;
   zapiš `<session>/builder/prompts/phases/build/{system,user}.md` a
   `.../revise_1/...` s různým obsahem (+ agentní `prompts/user.md` = revise).
   API pro `pb` vrací build prompt, pro `pr` revise prompt, `source == "phase"`,
   `legacy is False`.
2. `test_legacy_run_falls_back_to_agent_prompts`: jen `<session>/planner/prompts/{system,user}.md`;
   `p1` → obsah agentních souborů, `source == "agent"`, `legacy is True`, warning přítomen.
3. `test_missing_files_are_null`: jen `phases/plan/system.md` → `system` text,
   `user is None`, HTTP 200; a fáze bez jakýchkoli souborů (`p2` code nebo planner bez
   session) → oba `None`, `source == "none"`, 200.
4. `test_unknown_run_is_404`: `/api/runs/nope/phases/p1/prompts` → 404, `error.code == "unknown_run"`.
5. `test_unknown_phase_is_404`: `/api/runs/r-ok/phases/nope/prompts` → 404, `unknown_phase`.
   Také fáze jiného běhu (`p3` patří `r-run`) pod `r-ok` → 404.
6. `test_invalid_id_is_400`: např. `/api/runs/r-ok/phases/bad%20id/prompts` a
   `/api/runs/r-ok/phases/a..b/prompts` → 400 `invalid_value`; plus přímo
   `runs.phase_prompts(repo, "r-ok", "../etc")` a `runs.phase_prompts(repo, "../x", "p1")`
   vyhodí `TaskRunError` s `code == "invalid_value"`.
7. `test_path_cannot_escape_session_dir`: (a) fáze v DB s `owner = "../../outside"`
   a soubor tam opravdu existuje → odpověď má `system/user is None`, nic z něj nevrátí;
   (b) `phases/plan/user.md` je symlink na soubor mimo session dir (`tmp_path/secret.md`)
   → `user is None`.
8. `test_large_prompt_is_truncated`: `user.md` o velikosti `MAX_PROMPT_BYTES + 100` →
   `len(user.encode()) <= MAX_PROMPT_BYTES`, `truncated.user is True`, `truncated.system is False`.
9. `test_session_dir_follows_data_dir`: `.factory/agents.yaml` s vlastním `data_dir`
   (relativní, např. `custom-data`); prompty zapsané do `<repo>/custom-data/sessions/r-ok/...`
   API najde; prompty zapsané do `.factory/data/sessions/r-ok/...` (vedle trace DB) ne.
   Pokud je zápis agents.yaml v testu nepraktický, aspoň ověř
   `session_dir_of(repo, "r-ok") == repo/.factory/data/sessions/r-ok` a monkeypatchem
   `aifactory.run.task.data_dir` přesměruj.

Testy nesmí volat model (engine fixture již přepíná na `FakeHarness`, web testy model
vůbec nepotřebují).

## Ověření

Z kořene worktree:

```
just test
just typecheck
just lint
```

(`just lint` = `ruff check .` + `ruff format --check .` — po úpravách spusť
`cd aifactory && uv run ruff format <změněné soubory>`.)

## Kontrolní seznam

- [ ] `engine/prompts.py`, `engine/agents.py`: každá změna nese `# aifactory 2.10:`.
- [ ] `<agent>/prompts/{system,user}.md` se zapisují dál.
- [ ] Endpoint: 200 + `null` pro chybějící soubor, 404 `unknown_run`/`unknown_phase`,
      400 `invalid_value`; `source`/`legacy` označuje fallback.
- [ ] Session dir z `data_dir` konfigurace, containment přes `resolve()` + `is_relative_to`,
      ořez na `MAX_PROMPT_BYTES`.
- [ ] Žádné změny ve `vendor/`, `prototype/`, ani mimo povolené cesty.
- [ ] Dokumentace `app_docs/HAIFA-S02-T01-sestavene-prompty-kazde-faze-behu-v-api.md`
      (popis layoutu `prompts/phases/<phase>/` a endpointu s tvarem odpovědi) —
      pokud ji tato fáze má psát.
