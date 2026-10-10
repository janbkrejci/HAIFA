# Plán: obrazovka Review (seznam PR, detail s diffem, Schválit / Vrátit / Vyřešit konflikt)

Zdroj: `docs/product-brief.md`, tabulka „Dashboard“ (řádek Review) a kroky 5 a 6 v sekci „Běh úkolu“.
Mimo rozsah: odeslání approve review v hostingu jménem uživatele (OB3 / D11). `vendor/` a `prototype/` se nemění. Testy nevolají model ani síť.

## Kontext (co už existuje – NEPŘEPISOVAT, jen použít)

- **Core review** – `aifactory/src/aifactory/review/flow.py` (export z `aifactory.review`):
  - `approve_task(repo, task_id, *, provider=None) -> ApproveResult` (`reviewed` je vždy `False`, `to_json()`); při `conflict` hází `ReviewError("conflict", ...)`. Rychlé (commit done + merge), synchronní.
  - `return_task(repo, task_id, note, *, provider=None, code=None) -> TaskRunResult` – předkontroly (`missing_note`, `no_pr`, `pr_not_open`, `already_running`, `dirty_worktree`, `branch_checked_out`) hází `ReviewError`, pak **synchronně spustí celý běh** (`run_task`, mění cwd procesu!).
  - `resolve_task(repo, task_id, *, provider=None, code=None) -> TaskRunResult` – totéž, workflow `resolve`.
  - `ReviewError(code, message)` v `review/errors.py`. Kódy už jsou v `skill/codes.py` (sekce „Review, PR and provider“).
  - CLI: `cli.py::_task_approve|_task_return|_task_resolve` – importují `from aifactory.review import approve_task` atd. **uvnitř funkce** → test CLI monkeypatchuje `aifactory.review.<fn>`. Web musí volat stejně: přes atribut modulu `aifactory.review` (např. `import aifactory.review as review_core` a `review_core.approve_task(...)` v okamžiku volání), aby šel stejný monkeypatch.
- **Provider** – `aifactory/providers/`: `get_provider(settings, root)`, `provider.status(pr) -> PrStatus(state, mergeability, head_sha, merge_sha)`; `mergeability ∈ {mergeable, conflict, unknown}`. `local` počítá mergeabilitu lokálně (`git.trial_merge`), otevřený PR nikdy `unknown`. `ProviderError(code, message)`.
- **Store** – `aifactory/run/store.py::TaskRunStore`: `open_prs()`, `latest_pr(task_id)`, `pr_for_branch(branch)`, `runs_on_branch(branch)` (TaskRunRow: `run_id, task_id, workflow, state, branch, worktree, started_at, ended_at, note, error, base_sha, head_sha, pid…`), `running(task_id)`, `TaskPrRow` (`branch, task_id, provider, pr_id, url, base, base_sha, title, body, state, created_at, updated_at, merged_at, merge_sha`, `to_json()`, `request()`). Otevření bez vytvoření DB: `existing_store(repo)` v `run/task.py` (použito ve `web/runs.py::_open_run`).
- **Trace čtení** – `review/prbody.py`: `run_checks(trace_db, run_id) -> list[CheckInfo(kind 'gate'|'test', name, phase, passed, detail)]`, `branch_cost(trace_db, run_ids) -> (cost, tokens)`, `run_cost`. Verdikt revieweru = envelope s `payload.approved` (typ `ReviewOutput`: `approved`, `findings[{requirement, met, evidence}]`, `blocking[]`, `summary`) v tabulce `envelopes` (`adw_id, phase_id, agent, output_type, payload_json, valid, attempt, created_at`). Vzor čtení envelopes/JSON: `web/runs.py::_envelopes`, `_parse_json`, `_has_table`.
- **Vlastník** – `web/backlog.py::_owner(task)` = `core.effective(task).get("owner")` (dědí se z `index.md` modulu/stepu); `backlog_view` vrací seznam `owners`. Backlog se načítá přes `aifactory.backlog.load_backlog` / helper `_runtime` v `web/backlog.py` (podívej se, jak `backlog_view` načte backlog a nastavení, a udělej totéž).
- **Launcher** – `web/launcher.py::RunLauncher`: jeden dashboardový běh naráz na daemon vlákně; `start(repo, task_id, note=, force=)` volá `run_queue.run_chain`, počká na nový řádek `task_runs`, propaguje jen `TaskRunError`. `app.state.launcher`; testy volají `launcher.wait()`.
- **App** – `web/app.py`: obálky `envelope_ok/envelope_fail`, `_run_error`, `_edit_error`, `_json_body`, `_usage_error`, `run_in_threadpool`; routy pod `Mount("/api")`. Docstring modulu vyjmenovává endpointy – doplň.
- **Frontend** – Vue 3 + vitest + happy-dom, alias `@`. `lib/api.ts` (`getApi`, `postApi`, `ApiError`), `lib/format.ts` (`fmtCost`, `fmtTokens`, `fmtTime`, `fmtDuration`, `prettyJson`), `lib/router.ts` (`parseRoute`, `useRouteParams`, `runHref`, `taskHref`), `components/runs/StatusChip.vue`, `DetailSection.vue`, `views/ReviewView.vue` je zatím `EmptyScreen`. Vzory testů: `views/RunsView.test.ts`, `components/runs/*.test.ts`, fixtures `src/test/runsFixtures.ts`. Žádná markdown knihovna → popis PR zobraz jako `<pre class="…" style="white-space: pre-wrap">` (nepřidávej závislosti).
- **Build** frontendu je commitnutý v `aifactory/src/aifactory/web/static/` (test `test_packaged_build_is_served`). Po změně frontendu `just web-build`, commitni nový build (staré hashované assety zmizí).
- **Testy běhů bez modelu**: `tests/run/run_repo.py` (`make_run_repo`, `fake_env`, `Script`, `ok`, `write`, `commit_all`, `git`, `T01`, `T02`), vzor webového testu s launcherem `tests/web/test_web_task_run.py` (`sys.path.insert` na `tests/run`, fixtures `script/repo/app/client`, `wait(app)`), vzor konfliktu `tests/run/test_task_resolve.py` (`run_both`, `ResolveCode`, `resolver`, `settle`, monkeypatch `aifactory.review.resolve_task` s `code=`). Provider v `make_run_repo` je výchozí `local`. `index.md` modulu M01 v `run_repo` **nemá owner** – v testech ho dopiš do `backlog/M01-core/index.md` a commitni (`commit_all`) před během.

## Rozhodnutí

1. **Identita „já“** (pro filtr „moje moduly“): hosting identitu nemá (OB3), proto:
   - API vrací `owners` (všichni vlastníci z backlogu) a `me` = odhad: první z `git config user.email`, `git config user.name`, `$USER` (v hlavním checkoutu, `subprocess.run`, posuzuj exit status), který se **přesně** shoduje s nějakým ownerem; jinak `null`.
   - Filtr je parametr `?owner=<jméno>`; UI má select vlastníka s předvolbou `me` (a volbou „všechny“), volbu si pamatuje v `localStorage` (`factory.review.owner`). Checkbox/přepínač „Jen moje moduly“ = filtr na zvoleného vlastníka.
2. **„PR čekající na mé review“**: bez approve review v hostingu (OB3) čeká na review vlastníka modulu každý otevřený PR jeho modulu, na kterém právě neběží běh. Každá položka má `awaiting_review: bool` (`state == open` u provideru a `running is None`); UI má dvě sekce: „Čeká na mé review“ (awaiting_review) a „Ostatní otevřené PR“ (běží běh / stav provideru není open). Obě respektují filtr vlastníka.
3. **Nový modul `aifactory/src/aifactory/web/review.py`** – čisté funkce (bez Starlette) pro seznam a detail. Akce volají `aifactory.review.*` (žádná kopie logiky).
4. **Vrátit a Vyřešit** jsou běhy → pouštějí se na vlákně přes rozšířený `RunLauncher` (jako Spustit v Backlogu), HTTP 202 s nově založeným během. **Schválit** je synchronní (threadpool), HTTP 200.
5. **OB3 v UI**: u tlačítka Schválit trvalá poznámka „Schválení zatím neposílá approve review v hostingu (OB3) – rovnou přidá commit `status: done` a merguje.“ API ji vrací i v datech (`approve_review_sent: false`, `approve_note`), aby text měl jeden zdroj.

## Část A – backend

### A1. `web/launcher.py` – obecný start úlohy
- Přidej `start_job(self, repo, task_id, job: Callable[[], object], *, label: str, timeout: float = 30.0) -> TaskRunRow | None`; stávající `start()` ho zavolá s `lambda: run_queue.run_chain(repo, task_id, note=note, force=force)` (chování i signatura `start` beze změny; `run_queue.run_chain` se musí dál volat přes atribut modulu kvůli existujícím testům).
- `_work` volá `job()`; `last_result: object | None` (uprav typ; kde se `last_result` čte jako `ChainResult`, přetypuj/zkontroluj `isinstance`).
- Propagace chyb před claimem: vedle `TaskRunError` propaguj i `ReviewError` (`aifactory.review.errors.ReviewError`) beze změny. Hláška `already_running` zmíní `label` (např. „return M01-S01-T01“).
- Docstring modulu doplň (return/resolve z Review).

### A2. `web/review.py` (nový)
Typ `JsonDict = dict[str, Any]`, mypy strict.

```python
APPROVE_NOTE = ("Schválení zatím neposílá approve review v hostingu (OB3): "
                "rovnou přidá commit se status: done a PR merguje.")

def review_list(repo: Path, *, owner: str | None) -> tuple[JsonDict, list[str]]
def review_detail(repo: Path, task_id: str) -> tuple[JsonDict, list[str]]
def approve(repo: Path, task_id: str) -> tuple[JsonDict, list[str]]
def start_return(repo: Path, task_id: str, body: JsonDict, launcher: RunLauncher) -> tuple[JsonDict, list[str]]
def start_resolve(repo: Path, task_id: str, body: JsonDict, launcher: RunLauncher) -> tuple[JsonDict, list[str]]
```

**Společné načtení** (`_context(repo)`): `gitops.main_root(repo)`, `load_run_config(main)` (ConfigError propaguj), `existing_store(main)` (None → prázdný seznam / `no_pr` u detailu), backlog přes stejný postup jako `web/backlog.py` (chyba načtení backlogu → vlastník/titul `null` + warning, ne pád), provider `get_provider(settings, main)` (`ProviderError` → warning a mergeability `unknown`).

**`review_list`**:
- Pro každý `store.open_prs()` (poslední PR tasku; pokud má task víc otevřených, ber `latest_pr`):
  ```
  {task_id, task_title|null, module_id|null, owner|null,
   pr: TaskPrRow.to_json() bez "body",
   provider_state: "open"|"merged"|"closed"|null,      # z provider.status; null při chybě
   mergeability: "mergeable"|"conflict"|"unknown",
   running_run: {run_id, workflow, started_at}|null,     # store.running(task_id)
   awaiting_review: bool,
   cost: float, tokens: int,                             # branch_cost(trace_db, runs_on_branch)
   runs: int, last_run: {run_id, state, workflow, ended_at}|null}
  ```
  `provider.status` volej pro každý PR zvlášť v `try` (`ProviderError` → warning `f"PR {url}: {code}: {message}"`, mergeability `unknown`). **Nezapisuj** stav do `task_prs` (čtení je bez vedlejších efektů; zápis dělají akce core).
- `module_id`: nejbližší předek úrovně modul (první úroveň stromu) – použij rodiče tasku v načteném backlogu (viz `_nearest_id`/`_container_info` ve `web/backlog.py` jako vzor).
- Filtr `owner` (přesná shoda; `None` = vše). Neznámý owner → prázdný seznam, ne chyba.
- Řazení: `awaiting_review` napřed, pak `pr.created_at` sestupně.
- Návrat: `{"prs": [...], "owners": [...všichni vlastníci backlogu, seřazení], "me": str|null, "filters": {"owner": owner}, "provider": settings.git_provider, "approve_review_sent": False, "approve_note": APPROVE_NOTE}`.
- `me`: helper `_me(main, owners)` dle rozhodnutí 1 (`subprocess.run(["git","config",key], cwd=main, capture_output=True, text=True)`, `returncode == 0`).

**`review_detail(task_id)`**:
- `row = store.latest_pr(task_id)`; `None` → `ReviewError("no_pr", ...)` (HTTP 404). Neznámý task a žádný PR → `no_pr`.
- Data:
  ```
  {task_id, task_title, owner, module_id,
   pr: TaskPrRow.to_json() (včetně body = popis PR),
   provider_state, mergeability, running_run, awaiting_review, cost, tokens,
   runs: [{run_id, workflow, state, started_at, ended_at, note, error, cost, tokens, href_run_id}],  # runs_on_branch, nejnovější první; run_cost
   diff: {base: row.base, merge_base: sha|null, stat: {files, additions, deletions},
          files: [{path, old_path|null, status: "added"|"modified"|"deleted"|"renamed", additions, deletions, binary, patch, truncated}]},
   checks: [{kind, name, phase, passed, detail, run_id}],   # run_checks pro poslední běh ve stavu succeeded na větvi (jinak poslední běh)
   review: {approved, summary, blocking[], findings[], agent, run_id, created_at}|null,
   actions: {approve: bool, return: bool, resolve: bool},  # viz níže
   approve_review_sent: False, approve_note: APPROVE_NOTE}
  ```
- **Diff** (`_diff(main, base, branch)`): hlavní checkout, `git merge-base refs/heads/<base> refs/heads/<branch>` (neúspěch → `merge_base: null`, `files: []`, warning). Pak:
  - `git diff --numstat -z -M <merge_base> refs/heads/<branch>` → počty (binární = `-`),
  - `git diff --name-status -z -M …` → status (`A/M/D/R…`),
  - `git diff --patch -M --no-color <merge_base> refs/heads/<branch>` → rozděl podle řádků `diff --git a/… b/…` a přiřaď k souboru.
  - Patch souboru omez na 200 000 znaků (`truncated: true`), celkový diff na 2 000 000 znaků (další soubory bez patche, `truncated: true`).
  - Použij `providers.git.git(...)` / `git_ok` (podívej se na jejich chování při chybě; při chybě gitu → warning, prázdný diff, ne 500). Větev chybí (PR zavřený) → prázdný diff + warning.
- **Verdikt revieweru** (`_review_verdict(trace_db, run_ids)`): read-only sqlite (`file:…?mode=ro`, jako `prbody._trace`), `SELECT agent, payload_json, created_at, adw_id FROM envelopes WHERE adw_id IN (...) ORDER BY created_at DESC, rowid DESC`; první payload, který je dict s bool `approved`. Chybějící tabulka → `null`.
- **actions**: `approve = provider_state == "open" and mergeability != "conflict" and running_run is None`; `return = provider_state == "open" and running_run is None`; `resolve = provider_state == "open" and running_run is None` (resolve jde i u mergeable – jen dorovná větev; UI ho zvýrazní jen při `conflict`).

**`approve(repo, task_id)`**: `result = review_core.approve_task(repo, task_id)` (atribut modulu `aifactory.review`), vrať `result.to_json()` + `approve_review_sent: False`, `approve_note`. `result.warnings` → warnings obálky.

**`start_return`**: `_check_keys(body, ("note",))`, `note` povinný neprázdný string (jinak `UsageError`? – ne: nech core hodit `ReviewError("missing_note")`, ale nestringový typ → `backlog.UsageError`). Pak
`row = launcher.start_job(repo, task_id, lambda: review_core.return_task(repo, task_id, note), label=f"return {task_id}")` a vrať `{"task_id", "action": "return", "run": row.to_json()|None, "pending": row is None}`.
Pozor: `review_core.return_task` se musí dohledat **uvnitř lambdy / při volání** (kvůli monkeypatchi v testech).

**`start_resolve`**: totéž s `review_core.resolve_task(repo, task_id)`, `body` smí být prázdný objekt (žádné klíče).

Pozn.: předkontroly core (`no_pr`, `pr_not_open`, `already_running`, `dirty_worktree`, …) proběhnou na vlákně před claimem řádku; launcher je propaguje (A1) → HTTP chyba.

### A3. `web/app.py` – routy
Pod `Mount("/api")`:
- `GET /api/review?owner=` → `review_list` (threadpool – volá git/provider).
- `GET /api/review/{task_id}` → `review_detail`.
- `POST /api/review/{task_id}/approve` → `approve` (200).
- `POST /api/review/{task_id}/return` body `{note}` → `start_return` (202).
- `POST /api/review/{task_id}/resolve` body `{}` → `start_resolve` (202).
- Nový `_review_error(exc)` mapující `ReviewError` na HTTP: `no_pr` 404, `unknown_task` 404, `pr_not_open` 409, `conflict` 409, `already_running` 409, `dirty_worktree` 409, `branch_checked_out` 409, `missing_note` 400, `merge_failed` 502, `unknown_base` 500, `invalid_config` 500, `worktree_failed` 500, ostatní 500 (provider chyby typu `gh`/`az` → 502 je volitelné). `TaskRunError`/`ConfigError` → stávající `_run_error`; `backlog.UsageError` → `_usage_error`. Obálka chyby nese `code` a `message`.
- Rozšiř docstring modulu o Review endpointy (včetně věty, že volají `approve_task|return_task|resolve_task` jako `factory task approve|return|resolve` a že approve review se neposílá – OB3).
- Pokud nové kódy chyb vzniknou (neměly by), registruj je v `skill/codes.py` (hlídá `tests/test_skill.py`).

## Část B – frontend (`aifactory/web/src/`)

### B1. `lib/review.ts` (nový)
- Typy: `Mergeability`, `ProviderState`, `ReviewPr` (položka seznamu), `ReviewList`, `DiffFile`, `ReviewDiff`, `CheckResult`, `ReviewVerdict`, `ReviewRun`, `ReviewDetail`, `ReviewActions`, `ActionStarted`.
- `fetchReviews(owner: string | null)`, `fetchReview(taskId)`, `approvePr(taskId)`, `returnPr(taskId, note)`, `resolvePr(taskId)` (přes `getApi`/`postApi`, `encodeURIComponent`).
- `diffLines(patch): {kind: 'add'|'del'|'hunk'|'meta'|'ctx', text}[]` pro obarvení diffu (+ unit test).

### B2. `lib/router.ts`
- `reviewHref(taskId)` → `#/review/<task_id>`; rozšiř `router.test.ts`.

### B3. Komponenty `components/review/`
- `MergeabilityChip.vue`: `mergeable` „lze mergovat“, `conflict` „konflikt“, `unknown` „neznámé“ (`data-test="mergeability"`, třída podle stavu).
- `ReviewList.vue`: props `list: ReviewList`, `owner: string | null`; emit `update:owner`. Select vlastníka (`data-test="owner-filter"`: „Všechny moduly“ + `owners`, u `me` přípona „(já)“) a přepínač/tlačítko „Jen moje moduly“ (`data-test="mine-only"`, nastaví owner = `me`; disabled, když `me` je null, s hintem „Vlastníka z git config se nepodařilo spárovat, vyber ho ručně“). Dvě tabulky: „Čeká na mé review“ (`data-test="awaiting"`) a „Ostatní otevřené PR“ (`data-test="other"`). Sloupce: Task (odkaz `reviewHref`, id + titul), Modul, Vlastník, Mergeabilita (chip), Běh (běží → odkaz `runHref`), Náklady (`fmtCost`), Tokeny, PR (odkaz `target="_blank" rel="noopener"`, u `local:` jen text). Prázdný stav „Žádné otevřené PR“.
- `DiffView.vue`: props `diff: ReviewDiff`; souhrn (souborů, +/−), seznam souborů (status, cesta, +/−), každý soubor v `DetailSection` s `<pre>` řádky obarvenými přes `diffLines` (`data-test="diff-file"`); binární „binární soubor“, `truncated` „diff zkrácen“.
- `ChecksList.vue`: gates a testy, ✓/✗, název, fáze, detail (`data-test="check"`); prázdné „Gates ani testy neběžely“.
- `ReviewVerdict.vue`: schváleno/neschváleno, souhrn, blokující body, findings (requirement, met, evidence); `null` → „Review neběželo“.
- `ReviewActions.vue`: props `detail: ReviewDetail`, `busy: boolean`; emity `approve`, `return(note)`, `resolve`.
  - **Schválit** (`data-test="approve"`), disabled dle `actions.approve`; `window.confirm` před emitem. Pod ním vždy `approve_note` (`data-test="ob3-note"`).
  - **Vrátit s poznámkou**: `<textarea data-test="return-note">` + tlačítko (`data-test="return"`), disabled při prázdné poznámce nebo `!actions.return`.
  - **Vyřešit konflikt** (`data-test="resolve"`): při `mergeability === 'conflict'` zvýrazněný banner „PR nejde mergovat do <base> – Vyřešit spustí workflow resolve (rebase + agent)“ a primární tlačítko; jinak méně výrazné tlačítko „Dorovnat s base“ (stejná akce) jen když `actions.resolve`. Disabled když `busy`.
  - Když běží běh (`running_run`): info „Na PR běží běh …“ s odkazem na běh, akce disabled.
- `ReviewDetail.vue`: hlavička (task, titul, vlastník, PR odkaz, větev → base, `MergeabilityChip`, náklady/tokeny), sekce: Popis PR (`<pre>` s `pr.body`, `data-test="pr-body"`), Běhy (seznam `runs` s odkazy `runHref(run_id)` – „odkaz na běh“, `data-test="run-link"`), Gates a testy (`ChecksList`), Verdikt revieweru (`ReviewVerdict`), Diff (`DiffView`), Akce (`ReviewActions`).

### B4. `views/ReviewView.vue`
- `useRouteParams()`: bez parametru seznam, `[taskId]` detail.
- Seznam: `owner` z `localStorage` (`factory.review.owner`), při prvním načtení bez uložené volby použij `me` z odpovědi (znovu načti s ním); `<h1>Review</h1>` vždy; tlačítko „Obnovit“; chyba → banner.
- Detail: `fetchReview`; akce:
  - approve → `approvePr`, pak banner „Sloučeno (merge <sha7>)“ + `approve_note` a znovu načti detail (PR už nebude open → akce zmizí; ošetři chybu `no_pr`/`pr_not_open` zobrazením stavu, ne pádem);
  - return / resolve → `returnPr`/`resolvePr`, banner „Spuštěn běh <run_id>“ s odkazem `runHref`, znovu načti detail;
  - `ApiError` → banner s `message` (u `conflict` text doplň „použij Vyřešit konflikt“).
- Odkaz zpět `#/review`.
- `App.test.ts`: pokud stub `fetch` vrací health data pro každou URL, ReviewView musí s tím přežít (chybějící `prs` → prázdné seznamy). Test „switches screens“ čeká h1 – ověř, že „Review“ se vykreslí.

### B5. Unit testy (vitest, vzor `components/runs/*.test.ts`, fixtures do `src/test/reviewFixtures.ts`)
- `lib/review.test.ts`: `diffLines`; `fetchReviews` skládá URL s `owner`.
- `components/review/ReviewList.test.ts`: rozdělení na awaiting/other, sloupce vlastník/mergeabilita/náklady (`fmtCost`), změna selectu emituje `update:owner`, „Jen moje moduly“ emituje `me`, disabled bez `me`, prázdný stav.
- `components/review/ReviewActions.test.ts`: OB3 poznámka je vidět; Schválit disabled při `conflict` a Vyřešit je zvýrazněný; confirm → emit `approve`; Vrátit disabled bez poznámky, s poznámkou emituje `return` s textem; při `running_run` vše disabled.
- `components/review/DiffView.test.ts`: soubory, +/−, obarvené řádky, binární/zkrácený.
- `components/review/ReviewDetail.test.ts`: popis PR, checks, verdikt, odkaz na běh `#/runs/<id>`.
- `views/ReviewView.test.ts`: stub `fetch` podle URL; seznam; detail; klik Schválit volá `POST /api/review/<id>/approve`, pak `GET /api/review/<id>`; Vrátit posílá `{note}`; Vyřešit volá `/resolve`; chyba API se ukáže v banneru.

### B6. Build
`just web-build` a commitnout `aifactory/src/aifactory/web/static/`.

## Část C – testy API (`aifactory/tests/web/test_web_review.py`, provider `local`, fake harnessy)

Vzor fixtures z `tests/web/test_web_task_run.py` (`sys.path.insert(0, …/"run")`, `from run_repo import …`, `fake_env`, `make_run_repo`, `wait(app)`) a z `tests/run/test_task_resolve.py`. Pomocník `set_owner(repo, "alice")`: přepíše `backlog/M01-core/index.md` na frontmatter s `owner: alice` a `commit_all`. Pro druhého vlastníka lze přidat modul M02 s ownerem `bob` a jedním taskem (write + commit) – nebo filtr testuj na `alice` vs. `nobody`.

Testy (každý bez sítě a modelu):
1. `test_list_shows_open_pr_with_owner_mergeability_cost` – `succeed` (planner zapíše spec) → `run_task(repo, T01)`; `GET /api/review` → 1 položka: `owner == "alice"`, `mergeability == "mergeable"`, `provider_state == "open"`, `awaiting_review is True`, `cost`/`tokens` čísla, `pr.url == "local:factory/…-1"`, `"body" not in pr`; `approve_review_sent is False`, `approve_note` obsahuje „OB3“; obálka projde `envelope_problems`.
2. `test_owner_filter` – `?owner=alice` → 1, `?owner=bob` → 0; `owners` obsahuje `alice`; `me` = `"alice"` když `git config user.name alice` v repu (nastav v testu), jinak `null`.
3. `test_detail_has_body_diff_checks_runs` – detail T01: `pr.body` obsahuje „## Zadání“; `diff.files` obsahuje spec soubor se `status == "added"`, `additions ≥ 1`, patch obsahuje `+# spec`; `runs[0].run_id` = run_id běhu; `checks` je list (u plan-commit mohou být gates prázdné – ověř typ a že každý má `kind`); `review` je `null` (workflow bez revieweru) – a samostatný unit test `_review_verdict` s ručně vloženým řádkem `envelopes` (`payload_json` s `approved: true, blocking: [], summary`) do trace DB vrátí verdikt.
4. `test_detail_unknown_task_is_404` – `no_pr`, 404.
5. `test_approve_calls_core_and_merges` – `monkeypatch.setattr(aifactory.review, "approve_task", spy)` kde spy zaznamená volání a deleguje na originál; `POST /approve` → 200, `data.pr.state == "merged"`, `data.reviewed is False`, `approve_review_sent is False`; spy volán s `(repo, T01)`; `git show main:<task file>` obsahuje `status: done`. Druhé approve → 409 `pr_not_open`.
6. `test_return_starts_run_on_same_branch` – po prvním běhu naskriptuj další odpověď planneru; spy na `aifactory.review.return_task` (deleguje); `POST /return {"note": "přidej test"}` → 202, `data.run.branch == "factory/T01-1"`; `wait(app)`; spy volán s notou; nový běh v `task_runs` má `note == "přidej test"`. `POST /return {}` / `{"note": ""}` → 400 `missing_note`; `{"note": 5}` → 400 `usage_error`.
7. `test_conflict_offers_resolve` – `run_both` (z `test_task_resolve`; zkopíruj helpery `plan`, `run_both`, `resolver`, `settle`, `ResolveCode` do testu nebo je importuj – `tests/run` je na `sys.path`, import `from test_task_resolve import …` je OK jen když nekoliduje s pytest sběrem; bezpečnější je zkopírovat malé helpery). `GET /api/review` → T02 `mergeability == "conflict"`, detail `actions.approve is False`, `actions.resolve is True`. `POST /approve` → 409 `conflict`. Monkeypatch `aifactory.review.resolve_task` na wrapper s `code=ResolveCode([True])`; naskriptuj builder (`resolver(script, settle, changed_files=[MODEL], commit_message=…)`); `POST /resolve {}` → 202, `run.workflow == "resolve"`; `wait(app)`; pak detail T02 → `mergeability == "mergeable"`.
8. `test_action_while_dashboard_run_busy` – (volitelné) druhý start při běžícím launcheru → 409 `already_running`.
9. `test_launcher_start_job_propagates_review_error` – unit test `RunLauncher.start_job` s jobem, který hodí `ReviewError("no_pr", …)` → propaguje se.

Stávající testy (`test_web_task_run.py`, `test_web_app.py`, `test_web_server.py`) musí dál projít (launcher `start` beze změny chování).

## Ověření

Z kořene repa:
- `just test` (běží i `web-test`: vue-tsc + vitest, pak pytest)
- `just typecheck` (mypy strict nad `aifactory`)
- `just lint` (ruff check + ruff format --check; případně `cd aifactory && uv run ruff format .`)
- `just web-build` a ověřit, že `test_packaged_build_is_served` projde s novým buildem.
Hodnoť podle exit statusu.

## Soubory

- Nové: `aifactory/src/aifactory/web/review.py`, `aifactory/tests/web/test_web_review.py`, `aifactory/web/src/lib/review.ts` (+ `review.test.ts`), `aifactory/web/src/components/review/{MergeabilityChip,ReviewList,DiffView,ChecksList,ReviewVerdict,ReviewActions,ReviewDetail}.vue` (+ testy dle B5), `aifactory/web/src/test/reviewFixtures.ts`, `aifactory/web/src/views/ReviewView.test.ts`.
- Změny: `aifactory/src/aifactory/web/launcher.py`, `aifactory/src/aifactory/web/app.py`, `aifactory/web/src/views/ReviewView.vue`, `aifactory/web/src/lib/router.ts` (+ test), případně `aifactory/web/src/App.test.ts`, build `aifactory/src/aifactory/web/static/`.
- Neměnit: `aifactory/src/aifactory/review/*` (logika core zůstává; jen se volá), `vendor/`, `prototype/`.
