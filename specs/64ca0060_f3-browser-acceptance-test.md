# Plán 3.8: Akceptační test F3 v prohlížeči

## Cíl

Pytest test s Playwrightem (Python, sync API) spustí `factory obs` nad dočasným repem (provider `local`, falešný harness). Celý tok úkolu pak projde **jen přes prohlížeč**: založení dvou tasků, vazba, commit backlogu, spuštění prvního, sledování v Běhy, schválení v Review, spuštění druhého a jeho schválení. Nakonec test ověří `status: done` v `base` i v obrazovce Backlog. `just e2e` spustí jen tento test; `just test` ho spouští automaticky, protože `testpaths = ["tests"]`.

## Zjištěná mezera, kterou je nutné zavřít (jinak kritérium „bez terminálu“ nejde splnit)

Dashboard dnes backlog nikdy necommituje. `add`, `edit` a `link` zapisují jen do working tree (`src/aifactory/web/backlog.py`, docstring). Běh ale čte backlog z `base` (`run/task.py`, chyba `task_not_in_base`, 409). Task založený v UI proto bez `git commit` z terminálu nejde spustit. Run dialog na to jen upozorní (`[data-test=not-in-base]`).

**Řešení (minimální, v duchu D4 „uložit do souboru, tlačítkem commitnout do base“):** nová core funkce `commit_backlog`. Stejnou funkci volá nové CLI `factory backlog commit` i nový endpoint `POST /api/backlog/commit`, protože backend podle pravidel fáze nemá vlastní logiku. V run dialogu přibude uvnitř varování `not-in-base` tlačítko „Commitnout backlog do base“. Jde to za rámec „Where“ (`tests/e2e/`, `justfile`), ale bez toho kritérium „žádný krok nepotřeboval terminál“ splnit nejde. Builder to má uvést v závěrečném shrnutí.

## Kroky

### 1. Core: `src/aifactory/backlog/commit.py` (nový)

```python
@dataclass(frozen=True)
class BacklogCommit:
    committed: bool          # False = v backlog_dir nebylo co commitnout
    commit: str | None       # sha nového commitu
    base: str
    paths: list[str]         # relativní cesty změněných souborů (git status)
    pushed: bool
    def to_json(self) -> dict[str, Any]: ...

def commit_backlog(repo: Path, message: str | None = None) -> BacklogCommit
```

Chování:

1. `main = gitops.main_root(repo)`, `rc = load_run_config(main)`, `base = rc.base`, `backlog_dir = rc.config.settings.backlog_dir`. `ConfigError` převeď na chybu `invalid_config`.
2. Backlog musí být validní: `core.load_for_edit(repo)` + `check_backlog`. Při chybách vyhoď `TaskEditError` s kódem `backlog_invalid` a issues, stejně jako ostatní zápisy (viz `backlog/edit.py`, třída `TaskEditError` na ř. 58; použij její existující signaturu).
3. Hlavní checkout musí stát na `base`: `gitops.symbolic_head(main)` se musí rovnat `base` (ověř, zda vrací `refs/heads/x` nebo `x`). Jinak vyhoď `TaskEditError("not_on_base", "main checkout is on <x>, not <base>; commit the backlog there")`.
4. `git status --porcelain --untracked-files=all -- <backlog_dir>`. Pokud je prázdný, vrať `committed=False` (není to chyba).
5. `git add -A -- <backlog_dir>` a pak `git commit -q -m <msg> -- <backlog_dir>`. Pathspec zajistí, že se commitne jen backlog; jiné staged změny zůstanou staged. Výchozí zpráva: `backlog: <n> file(s) from factory` (nebo `message`, pokud je neprázdná).
6. Pokud `providers.git.has_remote(main, settings.remote)`, udělej `providers.git.push(main, remote, base)` a nastav `pushed=True`.
7. Vystav z `aifactory.backlog` (`__init__.py`): `commit_backlog`, `BacklogCommit`.

### 2. CLI: `factory backlog commit`

V `cli.py` `_add_backlog_commands` přidej subparser `commit` s `-m/--message`, `--json` a `--repo` (stejně jako ostatní; smyčka `for child in (check, list_, sync, auto)` → přidej `commit`). Handler volá `commit_backlog` a vrací obálku `{committed, commit, base, paths, pushed}`. Chyby a exit kódy mapuj podle `task add`/`link` (TaskEditError → rc 1/2 dle existující konvence). Help: „commit the backlog working-tree changes to base (only files under backlog_dir)“.

### 3. Web backend

- `src/aifactory/web/backlog.py`: `def commit(repo, body) -> tuple[JsonDict, list[str]]`. Klíče `("message",)` zkontroluj přes `_check_keys`, zavolá `core.commit_backlog`, vrátí `result.to_json()`. Uprav docstring modulu: kromě `commit` se nic necommituje.
- `src/aifactory/web/app.py`: `async def backlog_commit(request)` přes `run_in_threadpool`, se stejným ošetřením chyb jako `backlog_add`. Route `Route("/backlog/commit", backlog_commit, methods=["POST"])` přidej **před** `/backlog/tasks/{task_id}`. Do `_EDIT_ERROR_STATUS` přidej `"not_on_base": 409`. Pokud chybí, přidej i `"invalid_config"`, zkontroluj existující mapování.
- Commit v hlavním checkoutu vyvolá SSE `files` event, takže UI se obnoví samo.

### 4. Frontend (`aifactory/web/src`)

- `lib/backlog.ts`: typ `BacklogCommitResult` a funkce `commitBacklog(message?: string): Promise<BacklogCommitResult>` → `POST /api/backlog/commit` (stejný helper jako `linkTask`).
- `components/backlog/RunDialog.vue`: uvnitř `[data-test=not-in-base]` přidej `<button type="button" data-test="commit-backlog" :disabled="busy" @click="emit('commit')">Commitnout backlog do base</button>` a nový emit `commit: []`.
- `views/BacklogView.vue` (nebo `TaskDetail.vue`, podle toho, kde se dnes obsluhuje `start`/`cancel` z RunDialog): na `commit` zavolej `commitBacklog()` s busy stavem. Chybu ukaž jako `WriteError` (`flattenIssues`). Po úspěchu znovu načti run-check (`fetchRunCheck`) a detail, takže `not-in-base` zmizí a „Spustit“ je použitelné.
- Vitest: `RunDialog` nebo `BacklogView` test ověří, že tlačítko se ukáže jen při `in_base: false`, že klik zavolá `POST /api/backlog/commit` a že se pak znovu volá run-check. `lib/backlog.test.ts` ověří URL a metodu `commitBacklog`. Drž se existujících fixture (`src/test/backlogFixtures.ts`).
- **Přebuduj statický bundle:** `just web-build` a commitni změněné `src/aifactory/web/static/**`. `factory obs` servíruje build, ne zdrojáky, takže bez toho e2e test tlačítko neuvidí.

### 5. Python testy nové funkce (mimo e2e)

`tests/backlog/test_backlog_commit.py` (nebo vedle existujících testů edit):

- commitne jen `backlog/`, ostatní necommitnuté soubory zůstanou;
- vrátí `committed=False`, když není co commitnout;
- `backlog_invalid` při rozbitém backlogu (např. cyklus `depends_on`);
- `not_on_base`, když checkout stojí na jiné větvi;
- s bare remote udělá push (`git rev-parse origin/main` == HEAD po fetch);
- CLI `factory backlog commit --json` přes `cli_json.run_json`.

V `tests/web/test_web_backlog.py` přidej test `POST /api/backlog/commit` přes TestClient (200 + `committed: true`; 409 `not_on_base`).

### 6. Závislost Playwright

- `aifactory/pyproject.toml` `[dependency-groups].dev`: přidej `"playwright>=1.49"` a spusť `uv lock` (`cd aifactory && uv add --dev playwright`). Balíček je typovaný (`py.typed`), mypy strict ho vezme. Pokud mypy přesto hlásí chybějící stuby, přidej cílený `[[tool.mypy.overrides]]`, ne `ignore_errors`.
- Prohlížeč: primárně **systémový Google Chrome** (`p.chromium.launch(channel="chrome")`). Na stroji je Chrome 150 a stroj je macOS 12, kam bundled prohlížeče Playwrightu nejdou. Pokud channel `chrome` nejde spustit, zkus bundled `p.chromium.launch()`. Pokud nejde ani ten, `pytest.fail(...)` se zprávou „nainstaluj Google Chrome nebo spusť `just e2e-install`“. **Neskipuj**, test je brána F3. Proměnná `HAIFA_E2E_CHANNEL` volbu přebije (`chrome`, `chromium`, `msedge`; prázdná = bundled).
- `headless=True`.

### 7. E2E test: `aifactory/tests/e2e/`

Soubory:

- `tests/e2e/__init__.py` není potřeba: ostatní složky testů ho nemají, drž konvenci (zkontroluj `tests/web`).
- `tests/e2e/f3_repo.py`: stavba dočasného repa + fake skript + spuštění serveru.
- `tests/e2e/test_f3_browser.py`: samotný test.

#### 7a. Dočasné repo (`f3_repo.make_f3_repo(path) -> Path`)

Vyjdi z `tests/run/run_repo.py` `files("claude")` (import přes `sys.path.insert` na `tests/run`, jako to dělá `tests/web/test_web_task_run.py`). **Vynech oba task soubory** (`M01-S01-T01-schema.md`, `M01-S01-T02-loader.md`), protože tasky vytvoří UI. Zůstane:

- `.factory/config.yaml`: `base: main` (provider výchozí `local`; výslovně přidej `git_provider: local`)
- `.factory/agents.yaml` (harness `claude`), prompty, `.factory/workflows/plan-commit.yaml`
- `backlog/M01-core/index.md` s `workflow: plan-commit` a `backlog/M01-core/S01-model/index.md` s `writes: [src/app/]`
- `.gitignore`: `.factory/local.yaml`, `.factory/trace.db*`, `.factory/worktrees/`, `.factory/data/`, `__pycache__/`
- `README.md`, `src/app/__init__.py`

`git init -q -b main`, lokální `user.name`/`user.email`, `commit.gpgsign false`, commit `init`. **Bez remote**: PR je `local:<branch>` a `base` je lokální `main`. Nepoužívej `repo_templates.build` (jeden test, cache nepotřebuje), nebo ho použij se vlastním klíčem `e2e-f3`, obojí je v pořádku.

#### 7b. Fake skript (JSON pro `validation.fake`)

Workflow `plan-commit` volá jen agenta `planner`, jednou na běh. Jeden server = jeden skript pro celý test (čte se jednou do paměti), proto dvě položky:

```json
{"agents": {"planner": [
  {"envelope": {"status": "success", "summary": "t1", "artifacts": [], "changed_files": ["src/app/first.py"], "commit_message": "Add first"},
   "edits": [{"path": "src/app/first.py", "write": "FIRST = 1\n"}]},
  {"envelope": {"status": "success", "summary": "t2", "artifacts": [], "changed_files": ["src/app/second.py"], "commit_message": "Add second"},
   "edits": [{"path": "src/app/second.py", "write": "SECOND = 2\n"}]}
]}}
```

Formát ověř podle `validation/fake.py` a `validation/fake_scripts.py` (`_ok`, `_build`) a obálku podle toho, co přijímá plan fáze v `tests/web/test_web_task_run.py` (`build(script, name)`). Zápisy musí být pod `src/app/` (writes stepu), jinak je shodí write guard.

#### 7c. Spuštění serveru (fixture v `f3_repo.py`, contextmanager `obs_server(repo, script, log) -> Iterator[str]` vracející base URL)

- Port: volný port přes `socket.bind(("127.0.0.1", 0))` (vzor `tests/web/test_web_live.py` `_free_port`). `--port 0` CLI odmítá.
- Příkaz: `[sys.executable, "-m", "validation.worker", "obs", "--repo", str(repo), "--port", str(port), "--no-open"]`. `validation.worker` nainstaluje falešný harness z `HAIFA_VALIDATE_FAKE` a zavolá `aifactory.cli.main(["obs", ...])`, takže jde o skutečné `factory obs`, jen s fake harnessem ve stejném procesu. To je nutné, protože běhy dashboardu jedou ve vlákně serveru.
- `env = dict(os.environ)` plus:
  - `HAIFA_VALIDATE_FAKE=<script.json>`
  - `PYTHONPATH=<aifactory dir>` (+ původní hodnota)
  - `UV_NO_SYNC=1`
  - `ENGINEER_NAME=tester` a `GIT_AUTHOR_NAME/EMAIL`, `GIT_COMMITTER_NAME/EMAIL` (vzor `run_repo.fake_env`)
  - tripwire pro `CLAUDE_CODE_PATH`, `CODEX_PATH`, `PI_PATH`, `AIFACTORY_GH` (znovu použij `tripwire` z `tests/validation/local_validation.py`, import přes `sys.path` jako v `test_validation_local.py`, nebo ho zkopíruj do `f3_repo.py`, pokud by import táhl moc závislostí)
  - odeber `HAIFA_SANDBOX_REPO` a `HAIFA_VALIDATE_HIDDEN`
- stdout+stderr přesměruj do souboru `tmp_path/"obs.log"`, **ne do PIPE**: engine vypisuje na stdout serveru a plný pipe by server zasekl.
- Připravenost: polluj `GET http://127.0.0.1:<port>/api/health` (urllib, Host 127.0.0.1) až do 200, max 20 s. Když proces mezitím skončí, selži s koncem logu.
- Úklid ve `finally`: `proc.send_signal(SIGINT)`, `wait(10)`, jinak `kill()`.
- Při selhání testu přidej do assertion message posledních ~80 řádků `obs.log` (helper `log_tail`).

#### 7d. Prohlížeč

- `sync_playwright()`, launch viz krok 6, `context = browser.new_context(base_url=url)`.
- **Síť:** `context.route("**/*", handler)` propustí jen `http://127.0.0.1:<port>/...`, ostatní `route.abort()`. Aborty počítej a na konci asserni, že žádný nebyl (test nevolá síť).
- `context.set_default_timeout(15_000)`, pro čekání na běh 90 s.
- `page.on("dialog", lambda d: d.accept())`, protože „Schválit“ používá `window.confirm`.
- Selektory jsou `data-test` (ne `data-testid`): `page.locator('[data-test=save]')`, případně `playwright.selectors.set_test_id_attribute("data-test")` a `get_by_test_id`.

#### 7e. Scénář (test `test_f3_task_lifecycle_in_browser`, `@pytest.mark.xdist_group("e2e")`)

Od chvíle, kdy běží server, **test nespouští žádný git ani CLI příkaz, který mění repo**. Jen čte (`git show`, `git log`, `git ls-tree`) pro kontroly. Tím je „žádný krok nepotřeboval terminál“ vynucené strukturou testu. Navíc na konci ověř, že každý commit na `main` po `init` vznikl z dashboardu (krok 9).

1. `page.goto("/#/backlog")`, počkej na `h1` „Backlog“.
2. **Založ T1:** klik `[data-test=new-task]` → `[data-test=step]` vyber `M01-S01` → `[data-test=title]` „First feature“ → `[data-test=body]` zadání → `[data-test=save]`. Počkej, až URL odpovídá `#/backlog/M01-S01-T01` (`page.wait_for_url`), a ověř `[data-test=task-id]` = `M01-S01-T01`. Id čti z URL, neodhaduj ho.
3. **Založ T2:** totéž, titulek „Second feature“ → `M01-S01-T02`.
4. **Vazba:** na detailu T2 napiš do `[data-test=link-input]` `M01-S01-T01` a klikni `[data-test=link-add]`. Ověř `li[data-dep="M01-S01-T01"]` v detailu T2. Na T1 by v sekci Blokuje mělo být `li[data-block="M01-S01-T02"]` (pokud existuje, ověř).
5. **Spusť T1:** otevři `#/backlog/M01-S01-T01` (klikem na řádek ve stromu `li.task[data-task=M01-S01-T01]` nebo `page.goto` hashe; obojí je UI) → `[data-test=run]` → dialog `[data-test=run-dialog]` ukáže `[data-test=not-in-base]` → klik `[data-test=commit-backlog]` → počkej, až `not-in-base` zmizí → `[data-test=run-start]` → počkej na `[data-test=run-result] a`, jeho text je `run_id`.
6. **Sleduj v Běhy:** klik na nav `a[data-screen="runs"]` → řádek `tr[data-run="<run_id>"]` → `expect(row.locator(".chip[data-status]")).to_have_attribute("data-status", "succeeded", timeout=90_000)`. Obrazovka se obnovuje přes SSE; jako fallback je povolený klik `[data-test=refresh]` (je to UI). Když stav skončí `failed`, selži s logem serveru.
7. **Schval v Review:** nav `a[data-screen="review"]` → `[data-test=owner-filter]` `select_option("")` (Všechny moduly; filtr jinak default „já“ a PR může schovat) → `tr[data-pr="M01-S01-T01"] a.task-link` → počkej na `[data-test=mergeability][data-value=mergeable]` a povolené `[data-test=approve]` → klik (confirm přijme handler) → `[data-test=notice]` obsahuje „Sloučeno“.
8. **Spusť T2:** nav Backlog → detail T2 → `[data-test=run]` → dialog: `not-in-base` ani `unmet-warning` nesmí být vidět (T1 je v base done) → `[data-test=run-start]` → run_id → Běhy → `succeeded` → Review → schválit jako v kroku 7.
9. **Kontroly:**
   - Backlog v prohlížeči: nav Backlog, `li.task[data-task="M01-S01-T01"] .chip` a totéž pro T02 mají `data-state="done"`. Přepni `[data-test=mode-kanban]` a ověř, že `section.column[data-column="done"]` obsahuje `a.card[data-card=...]` pro oba.
   - `base`: pro každé id najdi cestu `git ls-tree -r --name-only main backlog/` (soubor začínající `<id>-`). `git show main:<path>` → frontmatter (`yaml.safe_load` hlavičky mezi `---`) má `status: done` a sekce `## Běhy` obsahuje `PR local:`.
   - `src/app/first.py` a `src/app/second.py` existují v `main` (`git show main:src/app/first.py`).
   - Terminál: `git log --format=%s <init_sha>..main` obsahuje jen commity z dashboardu: commit backlogu (`backlog: …`) a dva squash merge commity (ty obsahují i `status done`). Asserni počet a to, že žádný nemá jiný původ. Přesné subjekty zjisti z `providers/git.merge_commit` a `review/flow.py`.
   - Fake: `<script>.calls.jsonl` má přesně 2 volání `planner`. Tripwire marker neexistuje (žádný skutečný harness ani `gh`).
   - Síť: 0 abortovaných požadavků mimo 127.0.0.1.

Timeout celého testu drž pod ~2 minuty. Plugin pytest-timeout tu není, takže všechna čekání musí mít vlastní timeout.

### 8. justfile

Do sekce aifactory přidej:

```just
# browser acceptance test of F3 (Playwright over `factory obs`, system Chrome): just e2e
e2e *ARGS:
    cd aifactory && uv run pytest tests/e2e -n0 "$@"

# install Playwright's bundled chromium for machines without Google Chrome
e2e-install:
    cd aifactory && uv run playwright install chromium
```

`just test` beze změny: e2e test je pod `tests/`, takže ho `pytest` najde. Uprav jen komentář u `test`, že zahrnuje i e2e test v prohlížeči.

## Omezení

- `vendor/` a `prototype/` se nemění.
- Testy nevolají model (fake harness + tripwire) ani síť (route abort + jen 127.0.0.1).
- Ruff `line-length 100`, `ruff format`, mypy strict pro `tests/` (typuj fixture a helpery, `Iterator[...]`, `Page`, `Locator`).

## Ověření

```bash
cd /Users/jbk/Documents/HAIFA
just web-build          # přebuduje static bundle s tlačítkem commit-backlog
just e2e                # projde; spusť 2× po sobě kvůli stabilitě
just test               # frontend (vue-tsc, vitest) + celý pytest včetně e2e
just typecheck
just lint
git status              # static/** commitnuté, uv.lock aktualizovaný
```

Ruční kontrola: `just dash` nad sandboxem, založit task, v run dialogu kliknout „Commitnout backlog do base“ → task jde spustit.
