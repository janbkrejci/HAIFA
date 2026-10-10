# Odstranění vlastníka modulu (`owner`)

Engineer 2026-10-01 rozhodl, že se vlastník modulu nepoužívá. Pole `owner` v `index.md` modulu, stepu nebo v tasku proto už nemá v produktu žádný význam. Backlog ani Review ho nevracejí, nezobrazují a nefiltrují podle něj. Starší soubory, které pole `owner` obsahují, zůstávají platné a pole se v nich jen ignoruje.

## Co se změnilo

### Backlog – model a loader
- `aifactory/src/aifactory/backlog/model.py`: `owner` bylo odebráno z `INHERITED_KEYS`. Loader (`loader.py`, ten se neměnil) přebírá do `task.own` a do `container.defaults` jen klíče z `INHERITED_KEYS`. Pole `owner` se tedy tiše zahodí a `effective(task)` ho nevrací. `factory backlog check` ho neodmítne.

### API
- `aifactory/src/aifactory/web/backlog.py`, funkce `backlog_view(repo, *, status=None)`:
  - odpadl parametr `owner` a pomocná funkce `_owner`;
  - z JSON tasků a kontejnerů zmizel klíč `owner`;
  - z odpovědi zmizelo pole `owners`;
  - `filters` je teď jen `{"status": ...}`.
- `aifactory/src/aifactory/web/review.py`, funkce `review_list(repo)`:
  - odpadly parametr `owner` a funkce `_owner`, `_owners`, `_git_value` a `_me`, takže párování přes `git config user.email`/`user.name` a `$USER` už neexistuje. Odpadl i import `os`;
  - shrnutí PR (a tím i detail) už nemá klíč `owner`;
  - odpověď seznamu už nemá klíče `owners`, `me` ani `filters`;
  - text varování, které vznikne, když se backlog nepodaří načíst, zní teď „task titles and modules are not shown“.
- `aifactory/src/aifactory/web/app.py`: `GET /api/backlog` i `GET /api/review` už nečtou `?owner=`. Pokud parametr přijde, ignoruje se. Spolu s tím se upravily docstringy.

### Frontend (`aifactory/web/src/`)
- **Backlog:**
  - `BacklogFilters.vue` už nemá výběr „Vlastník“ ani prop `owners`;
  - `TreeNode.vue` a `KanbanBoard.vue` už neukazují `@owner`;
  - `TaskDetail.vue` už nemá řádek „Vlastník“;
  - `BacklogView.vue` komponentě filtrů nepředává `owners`;
  - `lib/backlog.ts`: z typů `TaskNode`, `ContainerNode`, `BacklogFilters` a `BacklogData` zmizely `owner` a `owners` a `fetchBacklog` už neposílá `owner`.
- **Review:**
  - `ReviewList.vue`: odstraněn celý blok filtrů (select „Vlastník“, tlačítko „Jen moje moduly“, hláška o git config) a s ním i jeho CSS a sloupec „Vlastník“. Sekce se jmenuje „Čeká na review“ (dříve „Čeká na mé review“);
  - `ReviewDetail.vue`: z hlavičky zmizel údaj „vlastník“;
  - `ReviewView.vue`: odstraněno čtení a zápis `factory.review.owner` do localStorage, logika výchozí hodnoty `me` i handler `onOwner`;
  - `lib/review.ts`: `fetchReviews()` je bez parametru a typy už nemají `owner`, `owners`, `me` ani `filters`.
- Testovací fixtures (`test/backlogFixtures.ts`, `test/reviewFixtures.ts`) a unit testy komponent, view a lib byly upravené podle nových typů.

### Další soubory
- `aifactory/src/aifactory/skill/skill.md`: z příkladu `index.md` a ze seznamu sdílených výchozích hodnot zmizel `owner`. `factory --skill` tak vlastníka nezmiňuje.
- `aifactory/src/aifactory/web/static/`: frontend je znovu sestavený. Vznikly nové `index-D0BspTTL.js` a `index-8fuBraTE.css`, staré soubory `index-CDxbqDSR.js` a `index-C3LPdPPO.css` byly nahrazeny a `index.html` odkazuje na nové soubory.

### Co zůstalo beze změny
`owner` ve významu vlastníka fáze v enginu a trace se nemění. Diff se ho nedotýká.

## Testy, které změnu hlídají
- `tests/backlog/test_backlog_load.py::test_owner_field_is_ignored`: `owner` v `index.md` modulu, stepu i v tasku. Ověřuje, že `check_backlog` nehlásí žádné problémy a že `owner` není v `effective`, `own` ani `defaults`.
- `tests/backlog/test_backlog_cli.py::test_check_accepts_legacy_owner`: `factory backlog check --json` vrací pro vzorový repozitář s `owner` výsledek `ok`, bez issues a bez varování.
- `tests/web/test_web_backlog.py`: odpověď API neobsahuje `owner` ani `owners` a `?owner=` výsledek nemění.
- `tests/web/test_web_review.py::test_owner_query_is_ignored`: i při nastaveném `git config user.name` a dotazu `?owner=bob` se vrátí všechna PR a v odpovědi chybí `owners`, `me` i `filters`.
- `tests/e2e/test_f3_browser.py`: z kroku schválení zmizel výběr v `owner-filter`.
- `tests/web/backlog_fixture.py`: indexy záměrně dál obsahují `owner`, aby testy pokryly starší data.

## Ověření
```
just test && just typecheck && just lint && just e2e
```
Ruční kontrola:
- na obrazovce Review není výběr vlastníka a horní sekce se jmenuje „Čeká na review“;
- na obrazovce Backlog je jen filtr „Stav“ a přepínač zobrazení;
- `curl localhost:<port>/api/review` nevrací `owners`, `me` ani `filters`.
