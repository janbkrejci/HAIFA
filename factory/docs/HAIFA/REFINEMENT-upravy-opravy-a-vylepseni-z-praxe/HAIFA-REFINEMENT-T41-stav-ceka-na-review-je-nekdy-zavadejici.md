# HAIFA-REFINEMENT-T41: „Čeká na review“ vs. „Čeká na automerge PR“

## Co se změnilo a proč

Task s otevřeným PR se dřív všude ukazoval jako „Čeká na review“ (na Backlogu „V review“), i když měl zapnutý auto-merge a factory ho mergne sama. Dashboard teď rozlišuje dva stavy:

- **Čeká na review**: PR je otevřené a čeká na uživatele (schválit nebo vrátit).
- **Čeká na automerge PR**: PR je otevřené, task má efektivní `auto_merge: true` (vlastní nebo zděděné ze stepu/projektu) a PR nemá `auto_merge_error`. Uživatel nemusí nic dělat.

Když auto-merge selže (`task_prs.auto_merge_error` je vyplněné), vrátí se PR do **Čeká na review**.

## Backend (`aifactory/src/aifactory/web/`)

- `backlog.py`: nová funkce `waits_for_automerge(task, auto_merge_error)` je jediné místo, kde se o stavu rozhoduje (`core.effective(task)["auto_merge"] is True` a žádná chyba auto-merge). Nový board state `awaiting merge` v `BOARD_STATES` (za `in review`). `_Runtime` má nově `merge_blocked` (tasky, jejichž nejnovější otevřené PR má `auto_merge_error`); `board_state` vrací `awaiting merge` nebo `in review`.
- `overview.py`: každé repo má vedle `review` nový seznam `automerge` (stejný tvar položek), souhrn má samostatný počet `automerge`; `review` už PR čekající na auto-merge neobsahuje. Čtení `task_prs` snáší starší trace DB bez sloupce `auto_merge_error`. Výběr nejnovějšího otevřeného PR tasku je vytažený do `_newest_open_prs` a používá ho i počítání board states (`tasks`). Sloty `factory.in_review` počítají dál oba druhy PR.
- `review.py`: položka seznamu má nové pole `awaiting_automerge`; `awaiting_review` je nově `false` pro PR, které mergne factory. Řazení: review, pak automerge, pak ostatní.
- `aifactory/src/aifactory/workflow/adaptive.py`: rada k workflow se nenabízí ani ve stavu `awaiting merge` (konstanta `ADVICE_CLOSED_STATES`).

## Frontend (`aifactory/web/src/`)

- `lib/backlog.ts`: stav `awaiting merge` s popiskem „Čeká na automerge PR“, `in review` se přejmenoval z „V review“ na „Čeká na review“; oba mají tooltip. `awaiting merge` je v `OPTIONAL_STATES`, takže sloupec kanbanu a volba filtru se ukážou, jen když v nich nějaký task je. Barva chipu (`style.css`) a uzlu/legendy v `DependencyGraph.vue` je `--violet`.
- `lib/overview.ts`: filtr a souhrnné tlačítko `automerge`, `automergePrs()`, počet `automerge` v `repoCounts`/`totals`. Urgence `automerge` je řazená až za `running`, takže repo, které jen čeká na auto-merge, se neřadí mezi repa čekající na uživatele.
- `components/overview/RepoCard.vue`: sekce „Čeká na automerge PR“ (`data-test="automerge"`), řádky odkazují do Review.
- `components/RepoSwitcher.vue`: počet „Čeká na automerge PR“ u každého repa; popisky počtů začínají velkým písmenem a aria-label má tvar „Popisek: N“.
- `components/review/ReviewList.vue`: skupina „Čeká na automerge PR“ mezi „Čeká na review“ a „Ostatní otevřené PR“, jen když v ní nějaký PR je. `views/ReviewView.vue` po akci nabídne další PR v pořadí review → automerge → ostatní.
- `TaskDetail.vue`, `TaskForm.vue`: `awaiting merge` je, stejně jako `in review`, stav, ve kterém task nejde upravit ani spustit.
- `lib/api.ts`, `lib/review.ts`: typy pro `automerge` a `awaiting_automerge`; `fetchOverview` doplní chybějící `automerge` na `[]`.
- Přebuilděný `aifactory/src/aifactory/web/static/` (nové hashe assetů v `index.html`).

## Návod

Formulace jsou sjednocené v `guide/03-prvni-spusteni.md`, `04-dashboard.md` (souhrnná tlačítka, sekce karty, pořadí podle naléhavosti, význam obou stavů), `05-backlog.md` (tabulka stavů), `06-behy.md`, `07-review.md` (skupiny seznamu, chování při auto-merge) a `12-tym.md`.

## Ověření

- Backend: `cd aifactory && uv run pytest tests/web/test_web_backlog.py tests/web/test_web_overview.py tests/web/test_web_review.py tests/workflow/test_workflow_advice.py -n0`. Nové testy pokrývají PR bez auto-merge, se zděděným auto-merge, se selhaným auto-merge (zpět do review) a trace DB bez sloupce `auto_merge_error`.
- Frontend: `just web-test` (mimo jiné `overview.test.ts`, `RepoCard.test.ts`, `ReviewList.test.ts`, `OverviewView.test.ts`, `App.test.ts`, `StateChip.test.ts`).
- Ručně: v projektu nebo stepu zapni Auto-merge, nech task doběhnout do otevřeného PR a zkontroluj, že je na Přehledu, v přepínači rep, v Review i na Backlogu pod „Čeká na automerge PR“ a že se nezapočítává do „Čeká na review“.
