# HAIFA-S01-T23: Review – zobrazit i hotové PR

## Co se změnilo

Obrazovka Review má novou volbu **„Zobrazit hotové“**. Po zapnutí se pod otevřenými PR objeví sekce **„Hotové“** se sloučenými a zavřenými PR tasků z tabulky `task_prs`, nejnovější nahoře. Detail hotového PR je jen pro čtení. Výchozí odpověď API se nemění, hotové PR vrací jen na vyžádání.

### Backend

- `aifactory/src/aifactory/run/store.py`: nová metoda `TaskRunStore.done_prs()` vrací řádky `task_prs` se stavem `merged` nebo `closed`, řazené podle `COALESCE(merged_at, updated_at) DESC` (pak `created_at`, `rowid`).
- `aifactory/src/aifactory/web/review.py`: `review_list(repo, include_done=False)`. S `include_done` přidá do dat klíč `done`, který plní `_done_list()`. Pro každý task se vezme jen jeden PR (nejnovější). Tasky, které už mají otevřený PR, se přeskočí (sdílí množinu `seen` s otevřenými PR). Položka obsahuje `task_id`, `task_title`, `module_id`, `provider_state`, `done_at` (`merged_at`, jinak `updated_at`), `cost`, `tokens` a `pr` bez `body`. Provider se na hotové PR neptá. Bez trace DB je `done` prázdné pole `[]`.
- `aifactory/src/aifactory/web/app.py`: `GET /api/review` čte query parametr `done`. Hodnoty `1`, `true` a `yes` zapnou `include_done`. Bez parametru nebo s `done=0` odpověď klíč `done` vůbec neobsahuje.

### Frontend (`aifactory/web/src/`)

- `lib/review.ts`:
  - typ `ReviewDonePr` a volitelné pole `ReviewList.done`;
  - `fetchReviews({ done })` volá `/review?done=1`;
  - `loadShowDone()` a `saveShowDone()` ukládají volbu do `localStorage` pod klíčem `haifa.review.showDone` (`'1'`/`'0'`); když úložiště není dostupné, volba platí jen pro aktuální návštěvu;
  - `doneLabel()` převádí stav na popisek (`merged` → „sloučeno“, `closed` → „zavřeno“);
  - `isReadOnly()` vrátí true, když je `provider_state` nebo `pr.state` `merged` či `closed`.
- `views/ReviewView.vue`: na seznamu (ne v detailu) je checkbox `data-test="show-done"`. Stav `showDone` se načte z `localStorage`. Změna volbu uloží a znovu načte seznam. `loadList` i `refreshList` posílají `done` podle volby. Výchozí stav je vypnuto.
- `components/review/ReviewList.vue`: nová prop `showDone`. Sekce `data-test="done"` „Hotové (N)“ se zobrazí až za otevřenými PR. Má sloupce Task (odkaz na detail), Modul, Stav (chip, sloučeno zeleně), Datum (`fmtTime(done_at)`), Náklady a PR. Odkaz na PR se otevírá v novém okně, `local:` URL se ukazuje jako text. Řádky se na klientu ještě jednou seřadí podle `done_at` sestupně. Když nejsou žádné hotové PR, sekce ukáže „Nic“.
- `components/review/ReviewDetail.vue`: u sloučeného nebo zavřeného PR se místo `ReviewActions` zobrazí poznámka `data-test="read-only"`: „PR je sloučeno/zavřeno (datum) – jen pro čtení, akce nejsou dostupné.“ Nejsou tedy dostupné Schválit, Vrátit, Vyřešit konflikt ani Dorovnat s base. Detail otevřeného PR zůstává beze změny.
- `aifactory/src/aifactory/web/static/`: přebuildovaný frontend (nové `index-V9wNmXBa.js`, `index-CV-_NYVF.css` a odkazy na ně v `index.html`).

Změnilo se i chování: po schválení (merge) se v detailu tlačítko Schválit už nezobrazuje ani zakázané, místo něj se ukáže poznámka jen pro čtení. Upravený test je v `ReviewView.test.ts`.

## Testy

- `aifactory/tests/web/test_web_review.py`:
  - `test_list_done_only_on_request`: bez parametru a s `done=0` odpověď `done` neobsahuje, s `done=1` ano;
  - `test_list_done_without_trace_db_is_empty`;
  - `test_done_lists_closed_newest_first`;
  - `test_done_detail_is_read_only`: `actions` jsou všechny false.
- `ReviewList.test.ts`: sekce chybí bez `showDone`; jsou ověřené pořadí, sloupce, štítky, datum a odkaz; sekce se ukáže i bez otevřených PR a bez hotových PR ukáže „Nic“.
- `ReviewDetail.test.ts`: detail sloučeného i zavřeného PR je jen pro čtení, otevřený PR akce zachovává.
- `ReviewView.test.ts`: volba je ve výchozím stavu vypnutá; po zapnutí se načte `?done=1` a volba se uloží; zapamatovaná volba platí po startu; v detailu checkbox není.
- `test/reviewFixtures.ts`: nová fixture `donePr()`.

## Jak ověřit

```sh
just test && just typecheck && just lint && just e2e
curl 'http://<host>/api/review'          # bez klíče "done"
curl 'http://<host>/api/review?done=1'   # s polem "done"
```

V dashboardu otevřete Review a zaškrtněte „Zobrazit hotové“. Pod otevřenými PR se objeví sekce „Hotové“. Volba vydrží i po obnovení stránky. Když otevřete hotový PR, akce v detailu nejsou dostupné.
