# HAIFA-REFINEMENT-T41: rozlišit „Čeká na review“ a „Čeká na automerge PR“

## Cíl

Task s otevřeným PR dnes všude vypadá jako „Čeká na review“ / „V review“, i když má zapnutý
automerge a uživatel nemusí nic dělat. Backend (API přehledu, review a backlogu) má u každého
tasku s otevřeným PR říct, na co čeká, a UI má na všech místech používat přesně tyto texty:

- **Čeká na review**: otevřené PR, uživatel musí zasáhnout.
- **Čeká na automerge PR**: otevřené PR, factory ho mergne sama.

## Pravidlo (jedno, sdílené všemi API)

Task s otevřeným PR čeká na **automerge**, když platí obojí:

1. efektivní `auto_merge` tasku je `True` (`core.effective(task).get("auto_merge") is True`,
   dědí task → step → projekt; stejný výraz už používá `web/backlog.py::_task_json` pro
   `effective_auto_merge`),
2. nejnovější otevřené PR tasku nemá zapsané `task_prs.auto_merge_error`.

Jinak čeká na **review**. Bod 2 je nutný: `review/automerge.py` zkouší merge jednou po běhu;
když se nepovede (CI červené, konflikt, workflow bez review…), PR zůstane otevřené s
`auto_merge_error` a čeká na ruční schválení (guide 07-review.md: „PR čeká na ruční schválení“).
Takový task patří do „Čeká na review“. Neznámý task (backlog se nenačetl, task chybí) = review.

Sdílená funkce v `aifactory/src/aifactory/web/backlog.py` (vedle `board_state`):

```python
def waits_for_automerge(task: Task | None, auto_merge_error: str | None) -> bool:
    """An open PR of `task` is merged by the factory itself: effective auto_merge, no error."""
    return task is not None and core.effective(task).get("auto_merge") is True and not auto_merge_error
```

Sloty (`run.queue.Slots`, `factory.in_review`, `chains.in_review`) se **nemění**: PR čekající na
automerge dál drží slot. `run/queue.py` ani skip reason `in_review` neměnit.

## Backend

### 1. `aifactory/src/aifactory/web/backlog.py` – nový stav boardu

- `BOARD_STATES`: přidat `"awaiting merge"` hned za `"in review"`.
- `_Runtime`: přidat `merge_blocked: set[str]` (task ids, jejichž nejnovější otevřené PR má
  `auto_merge_error`).
- `_runtime()`: z `store.open_prs()` (newest first) pro každý task vzít první řádek; `in_review`
  zůstává množina všech tasků s otevřeným PR, do `merge_blocked` přidat ty s `row.auto_merge_error`.
- `board_state()`: místo `return "in review"`:
  ```python
  if task.id in rt.in_review:
      blocked = task.id in rt.merge_blocked
      return "awaiting merge" if waits_for_automerge(task, "x" if blocked else None) else "in review"
  ```
  (nebo čistěji: helper `_merge_waits(task, rt)`; výsledek musí odpovídat pravidlu výše).
- Upravit modulový docstring (popis stavů: `in review` = otevřené PR čekající na uživatele,
  `awaiting merge` = otevřené PR s efektivním `auto_merge` bez `auto_merge_error`).
- Filtr `status=` v API přijme nový stav automaticky přes `BOARD_STATES`.

### 2. `aifactory/src/aifactory/workflow/adaptive.py`

Řádek 85: do množiny zakázaných stavů přidat `"awaiting merge"`.

### 3. `aifactory/src/aifactory/web/overview.py`

- `_read_trace`: do SELECTu `task_prs` přidat `auto_merge_error` volitelně, stejně jako
  `merged_at` (`"auto_merge_error" if ... in _columns(...) else "NULL AS auto_merge_error"`).
- `_task_summary`: naplnit `rt.merge_blocked` z `trace.prs` (pro každý task nejnovější otevřené PR
  podle `created_at`, rowid; s neprázdným `auto_merge_error`). Počty `tasks` pak obsahují i
  `"awaiting merge"`.
- `_lists`: dostane navíc `backlog: Backlog | None` (volání v `Overview.repo` předá
  `tasks.backlog`). Seznam otevřených PR rozdělit: položka (stejný tvar jako dnes) jde do
  `automerge`, když `waits_for_automerge(task, pr["auto_merge_error"])` (task z
  `backlog.by_id.get(task_id)`, jen instance `Task`), jinak do `review`. Do `lists` přidat klíč
  `"automerge"`. Řazení obou seznamů stejné jako dnes.
- `_stub`: přidat `"automerge": []`.
- Pokud `totals` existuje na backendu (najdi, kde se sčítá `review` do souhrnu odpovědi, test
  `test_web_overview.py` ř. ~166 očekává `"review": 2`), přidat oddělený počet `"automerge"`;
  `review` nesmí zahrnovat automerge PR.
- Docstring modulu: popsat `review` (čeká na uživatele) a `automerge` (otevřené PR tasků s
  efektivním `auto_merge` bez `auto_merge_error`) a nový stav v `tasks`.

### 4. `aifactory/src/aifactory/web/review.py`

- `_pr_summary`: spočítat `automerge = status.state == OPEN and running is None and
  waits_for_automerge(task, row.auto_merge_error)`; vrátit
  `"awaiting_automerge": automerge` a `"awaiting_review": status.state == OPEN and running is None and not automerge`.
- `review_list`: řazení `items.sort(key=lambda i: (not i["awaiting_review"], not i["awaiting_automerge"]))`
  (po řazení podle `created_at`), tj. review → automerge → ostatní.
- Import `waits_for_automerge` z `aifactory.web.backlog` (zkontroluj, že nevznikne cyklický
  import; `overview.py` už z `web.backlog` importuje, `review.py` případně také lze; jinak dát
  helper do neutrálního modulu, např. `aifactory/src/aifactory/web/prwait.py`, a importovat ho
  z obou).
- Docstring (pokud popisuje `awaiting_review`) doplnit o `awaiting_automerge`.

## Frontend (`aifactory/web/src/`)

Texty jednotně: **„Čeká na review“** a **„Čeká na automerge PR“**.

### `lib/backlog.ts`
- `BoardState` + `BOARD_STATES`: přidat `'awaiting merge'` za `'in review'`.
- `STATE_LABELS`: `'in review': 'Čeká na review'`, `'awaiting merge': 'Čeká na automerge PR'`.
- `STATE_TOOLTIPS`: přidat vysvětlení obou (`in review`: „Pull request čeká na tvoje review.“,
  `awaiting merge`: „Auto-merge je zapnutý, factory pull request mergne sama.“).

### `style.css` a `components/backlog/DependencyGraph.vue`
- Přidat `.state-chip.state-awaiting-merge` a v DependencyGraph `.state-awaiting-merge rect`,
  `.node-state`, `.legend .state-awaiting-merge .swatch` – odlišná barva od purple (např.
  `var(--cyan)` nebo tlumená zelenomodrá; použij existující CSS proměnnou, ověř v `style.css`).
  Legenda se generuje z `BOARD_STATES`, takže nový stav v ní bude sám.

### `components/backlog/TaskDetail.vue`, `TaskForm.vue`
- Všude, kde je seznam `['done','cancelled','running','in review']` nebo `state === 'in review'`,
  přidat `'awaiting merge'` (advice blocked, readiness banner, frozen). Readiness text používá
  `STATE_LABELS`, takže ukáže nový text.

### `lib/api.ts`
- `OverviewRepo`: přidat `automerge: OverviewReview[]` (volitelně `automerge?:` kvůli starším
  odpovědím; v helperu pak `repo.automerge ?? []`).
- `OverviewTaskCounts` (pokud vyjmenovává stavy) doplnit `'awaiting merge'`.

### `lib/overview.ts`
- `OverviewFilter`: přidat `'automerge'`; `TOTALS`: za `review` vložit
  `{ id: 'automerge', label: 'Čeká na automerge PR' }`.
- `Urgency`: přidat `'automerge'`, `URGENCY_ORDER = ['problems','failed','review','running','automerge','calm']`;
  `urgency()`: za `running` (a za pending control) `if (automergePrs(repo).length > 0) return 'automerge'`.
  Repo, které jen čeká na automerge, tak není řazené jako čekající na uživatele, ale zůstává
  mezi kartami (není „v klidu“, protože factory na něm ještě pracuje). Zkontroluj
  `OverviewView.vue` (`cards`/`calm` filtr podle `'calm'`) – funguje beze změny.
- Helper `automergePrs(repo) = repo.automerge ?? []`.
- `RepoCounts`: přidat `automerge`; `repoCounts`, `totals` (sum) doplnit. `matchesFilter`
  funguje přes `repoCounts[filter]`.
- Komentáře u `sortRepos` aktualizovat.

### `components/overview/RepoCard.vue`
- Sekce „Čeká na review“ zůstává pro `repo.review`.
- Nová sekce `<h3>Čeká na automerge PR</h3>` pro `automergePrs(repo)`, stejné řádky (odkaz na
  review, PR #, stáří, „podle trace“), `data-test="row-automerge"`, sekce
  `data-test="automerge"`. Umístit za sekci review.

### `views/OverviewView.vue`
- Tlačítko totals se vykreslí z `TOTALS` samo; přidat CSS třídu `.total-automerge` (barva
  shodná s chipem awaiting merge), pokud existují třídy `.total-review` apod.

### `components/RepoSwitcher.vue`
- `COUNTS`: `{ key: 'review', label: 'Čeká na review' }`, přidat `{ key: 'automerge', label:
  'Čeká na automerge PR' }` za review; pro konzistenci velkým písmenem i `'Běží'`, `'Selhalo'`.
  Přidat `.count-automerge` (stejná barva jako chip awaiting merge).

### `components/review/ReviewList.vue`, `lib/review.ts`
- `ReviewPr`: přidat `awaiting_automerge: boolean`.
- Sekce: `awaiting` (`awaiting_review`) „Čeká na review“, `automerge` (`awaiting_automerge`)
  „Čeká na automerge PR“, `other` (ani jedno) „Ostatní otevřené PR“.
- `views/ReviewView.vue` ř. ~102: výchozí výběr `awaiting_review ?? awaiting_automerge ?? prs[0]`.
- Fixtures `test/reviewFixtures.ts`, `ReviewDetail.test.ts`, `ReviewView.test.ts`: doplnit
  `awaiting_automerge` (typová kontrola vue-tsc jinak selže).

### Návod (`aifactory/src/aifactory/guide/`)
- `04-dashboard.md`: přepínač rep (počty běžících, čekajících na review, čekajících na
  automerge PR a selhaných); Přehled: tlačítka **Běží**, **Čeká na review**, **Čeká na automerge
  PR**, **Selhalo**, **Problémy**; karta repa ukazuje PR čekající na review a zvlášť PR čekající na
  automerge; vysvětlit rozdíl (review = potřeba tvůj zásah; automerge = efektivní `auto_merge`,
  factory mergne sama; když automerge selže, PR se vrátí do „Čeká na review“).
- `07-review.md` ř. 7: tři skupiny **Čeká na review**, **Čeká na automerge PR**, **Ostatní
  otevřené PR**; v sekci auto-merge (ř. ~59–66) doplnit, že PR do pokusu/při úspěchu je v
  „Čeká na automerge PR“ a po neúspěchu v „Čeká na review“.
- `05-backlog.md` tabulka stavů (ř. 31): nahradit „V review“ řádky
  „Čeká na review | Task má otevřený pull request a čeká na tvoje review.“ a
  „Čeká na automerge PR | Task má otevřený pull request se zapnutým auto-merge; factory ho mergne sama.“
- `skill/skill.md` ř. ~200 jen pokud vyjmenovává board states: doplnit `awaiting merge`.

### Statický build
`aifactory/src/aifactory/web/static` je generovaný a commitovaný: po změnách frontendu spustit
`just web-build`.

## Testy

### Backend (`aifactory/tests/web/`)
- `test_web_backlog.py`: upravit očekávané `states` (nový stav). Nové testy `board_state`:
  task s otevřeným PR a `auto_merge` vypnutým → `"in review"`; s `auto_merge: true` zděděným ze
  stepu/projektu (`index.md`) → `"awaiting merge"`; s `auto_merge: true` a PR s
  `auto_merge_error` (`store.update_pr(branch, auto_merge_error="checks_failing: …")`) →
  `"in review"`.
- `test_web_overview.py` (+ `overview_fixture.py` podle potřeby): očekávané `tasks` počty
  (`"awaiting merge": 0`), nový klíč `automerge` ve stubu (`p["automerge"] == []`), totals.
  Nové testy: PR tasku s efektivním `auto_merge` je v `automerge`, ne v `review`, a počítá se do
  `tasks["awaiting merge"]`; s `auto_merge_error` je v `review`; trace DB bez sloupce
  `auto_merge_error` se dál čte. `factory.in_review` (sloty) dál počítá obě.
- `test_web_review.py`: `awaiting_review`/`awaiting_automerge` pro oba případy + pořadí
  review → automerge → ostatní.
- `tests/workflow/` (adaptive): pokud existuje test zakázaných stavů pro advice, přidat
  `awaiting merge`.
- Projít další soubory, které grep našel (`test_web_pr_refresh.py`,
  `tests/workflow/test_default_workflows_run.py`, `tests/run/test_factory_start.py`,
  `tests/e2e/test_multi_repo_browser.py`) a upravit tam, kde očekávají „V review“ / stará data.

### Frontend (vitest)
- `lib/overview.test.ts`: `taskSummary` labely, `stateClass('awaiting merge') ===
  'state-awaiting-merge'`, `urgency` (repo jen s automerge → `'automerge'`, řadí se za running),
  `totals`/`repoCounts`/`matchesFilter` oddělené (filtr review nezahrnuje automerge).
- `RepoCard.test.ts`: obě sekce s texty „Čeká na review“ a „Čeká na automerge PR“.
- `OverviewView.test.ts`: tlačítko `total-automerge`, filtr.
- `ReviewList.test.ts`: tři skupiny.
- `StateChip.test.ts`: `'Čeká na review 2'`, nový chip awaiting merge.
- `KanbanBoard.test.ts`, `backlogQueue.test.ts`, `BacklogView.test.ts`, fixtures
  (`backlogFixtures.ts` states, `overviewFixtures.ts` tasks): nový sloupec/stav.
- `TaskDetail.test.ts` `it.each` přidat `'awaiting merge'`.
- `overviewFixtures.ts`: `automerge: []` v repo fixture.

## Ověření
- `just lint`, `just typecheck`
- `just pytest tests/web tests/workflow` (backend změny v `web/` a `workflow/adaptive.py`)
- `just web-test`, `just web-build`
- `just pytest tests/e2e/test_multi_repo_browser.py -n0` (přehled/přepínač rep), případně e2e
  souboru backlogu/review, pokud kontroluje texty stavů.
