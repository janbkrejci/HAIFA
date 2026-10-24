# HAIFA-S01-T46 — Backend: příznak archivovaný u hotového tasku

## Cíl a smlouva API

Archivace je provozní preference v trace DB, nikoliv nový stav nebo změna souboru tasku. Backend přidá příznak do všech taskových JSON reprezentací vytvářených `_task_json`; tasky nadále vrací, nefiltruje je. Frontend a statický build řeší T47.

Význam `archived` určovat podle `task.status`, nikoli odvozeného `board_state`:

| status tasku | archived v JSON | ruční archivace |
| --- | --- | --- |
| cancelled | vždy true, bez zápisu preference | odmítnout |
| done | členství ID v `QueuePrefs.archived` | povolit true i false |
| ostatní | vždy false i při existující preferenci | odmítnout |

`POST /api/backlog/tasks/{task_id}/archive` přijímá pouze `{"archived": bool}`. Úspěch má HTTP 200 a standardní envelope s `data: {"task_id": id, "archived": bool}`. Stejná relativní route funguje pod `/api/repos/{id}/` díky sdílenému `_repo_routes()`. Chyby: neexistující task nebo ID kontejneru → `unknown_task`/404; task mimo status done → `invalid_value`/400; chybějící nebo neboolovské archived → `invalid_value`/400; další klíč → stávající `_check_keys`, tedy `usage_error`/400. Validace proběhne před otevřením zapisujícího store.

## Povolené změny

Implementace smí měnit pouze:

- `aifactory/src/aifactory/run/store.py`
- `aifactory/src/aifactory/web/backlog.py`
- `aifactory/src/aifactory/web/app.py`
- `aifactory/tests/run/test_queue_prefs.py`
- `aifactory/tests/web/test_web_backlog_queue.py`
- tento specifikační soubor `factory/specs/HAIFA/S01-dashboard-ux/HAIFA-S01-T46-backend-priznak-archivovany-u-hotoveho-t.md`
- realizační dokumentaci `factory/docs/HAIFA/S01-dashboard-ux/HAIFA-S01-T46-backend-priznak-archivovany-u-hotoveho-t.md`

Další zapisované cesty nejsou potřeba. Neměnit backlog, frontmatter, výběr tasků pro auto-continue ani frontend. Nepřidávat automatické mazání preference při změně statusu: mimo done ji JSON prostě ignoruje.

## 1. Trace DB a QueuePrefs

V `store.py`:

1. Do definice `task_queue` v `_SCHEMA` přidat `archived INTEGER NOT NULL DEFAULT 0`. V `TaskRunStore.__init__`, po vytvoření schématu, použít existující `_add_columns(self.conn, "task_queue", {"archived": "INTEGER NOT NULL DEFAULT 0"})`. Samotné CREATE TABLE starou tabulku nezmění.
2. Do zmrazeného dataclassu `QueuePrefs` přidat `archived: frozenset[str] = frozenset()` za stávající pole, aby zůstal zachovaný význam dosavadních pozičních argumentů order, excluded, priority. `queue_prefs()` načte archived společně s původními třemi sloupci a sestaví množinu ID s nenulovou hodnotou. Výsledek sestavit pojmenovanými argumenty včetně priority, aby se pole nezaměnila. Větev bez tabulky dál vrací prázdné preference s prioritami.
3. Přidat `set_archived(self, task_id: str, archived: bool) -> None` podle `set_excluded`: `_now()`, `_txn()`, INSERT s výchozím rank NULL a excluded 0; při konfliktu aktualizovat pouze archived a updated_at. Bool uložit jako `int(archived)`. Nakonec volat `_prune_queue()`.
4. `_prune_queue()` smí mazat jen `rank IS NULL AND excluded = 0 AND archived = 0`. Archivovaný task bez pořadí a vyloučení musí zůstat.
5. Stávající UPSERTy v `set_queue_order`, `queue_front`, `set_excluded` už aktualizují pouze vlastní pole a updated_at. Zachovat tento mechanismus: nový sloupec může při INSERT využít default, ale při konfliktu jej nesmí přepsat. Nepoužívat INSERT OR REPLACE ani plošné mazání řádků.
6. Stručně doplnit příslušné docstringy a popis task_queue o archivaci.

Ověření: preference přetrvá zavření a nové otevření store, změny order/front/excluded i migraci existující tabulky. Ostatní preference a priority se nemění.

## 2. Backlog serializace a zápis

V `web/backlog.py`:

1. Vedle `EXCLUDE_KEYS` přidat `ARCHIVE_KEYS = ("archived",)`.
2. V `_task_json` přidat `data["archived"] = task.status == "cancelled" or (task.status == "done" and task.id in rt.queue.archived)`. `_runtime()` už načítá QueuePrefs; není potřeba další dotaz pro každý task. Zrušený task při čtení nezapisovat do DB.
3. Vedle `auto_exclude` přidat `archive(repo: Path, task_id: str, body: JsonDict) -> tuple[JsonDict, list[str]]`. Postup shodný s auto_exclude: `_check_keys`, kontrola `isinstance(value, bool)`, `core.load_for_edit(repo)`, vyhledání skutečného `Task`, pak kontrola `task.status == "done"`. Použít `_queue_store(repo)`, `try/finally` se `store.close()` a `store.set_archived`. Vrátit `{task_id, archived}, []`.

Ověření: archivace ani odarchivace nemění soubory tasků a běžný GET nevytváří chybějící trace DB. JSON task detailu používá stejnou funkci jako backlog seznam a strom.

## 3. HTTP route

V `web/app.py`:

1. Přidat `backlog_archive` podle `backlog_auto_exclude`: `_repo(request)`, task_id z path_params, `_json_body`, `run_in_threadpool(backlog.archive, ...)`, shodné zachycení UsageError, TaskEditError, ConfigError a TaskRunError a `envelope_ok`.
2. Do `_repo_routes()` vedle auto-exclude přidat `Route("/backlog/tasks/{task_id}/archive", backlog_archive, methods=["POST"])`. Registrace na tomto místě zajistí oba režimy routování a stávající WriteGuardMiddleware; nepřidávat vlastní bezpečnostní mechanismus.
3. V modulovém docstringu poblíž popisu queue/auto-exclude popsat tělo nové route, omezení na status done a pravidla JSON pole archived včetně cancelled.

## 4. Regresní testy v povolených souborech

`tests/run/test_queue_prefs.py`:

- Prázdné preference mají archived prázdné. Nastavení true je idempotentní, přetrvá nové otevření store, nastavení false ho odstraní.
- Archived-only řádek přežije `set_queue_order([])` i pořadí, které jeho ID neobsahuje; zkontrolovat také konflikt při zařazení již archivovaného ID.
- `queue_front` uchová archivaci přesunutého ID i jiného archivovaného ID mimo frontu a zachová původní order/excluded.
- `set_excluded(id, True)` a následné False uchovají archivaci. Opačně `set_archived` true/false nepoškodí rank a excluded.
- Po odarchivaci odstranit nepotřebný řádek; ranked nebo excluded řádky zachovat.
- Přidat migraci vedle stávajícího testu chybějící tabulky: sqlite3 vytvoří starou task_queue se sloupci task_id, rank, excluded, updated_at a vloží stará data. Otevření přes TaskRunStore přidá sloupec (PRAGMA table_info), původní řádky mají archived 0, order/excluded se zachovají. Uložit archivaci, znovu otevřít a ověřit ji. Původní test chybějící celé tabulky ponechat.

`tests/web/test_web_backlog_queue.py` využije existující fixture bez změn: importovat také A1 (done); A4 je cancelled, B1 je todo.

- Bez trace DB má A1 false, A4 true, B1 false. Zkontrolovat neexistenci `.factory/trace.db` i po GET; před touto kontrolou nevolat `_prefs`, který by DB vytvořil.
- POST A1 true → 200 a přesný data objekt, `_prefs(root).archived` obsahuje A1, následné GET backlogu a task detailu vrací true. POST false vrátí false a následný GET to potvrdí. Porovnat obsah backlog souborů před a po zápisech.
- A4 zůstává true bez uložené preference a po odarchivaci A1. Pokud preference pro B1 vznikne přímo přes store, jeho JSON pořád vrací false.
- Pro true i false odmítnout B1 (todo) a A4 (cancelled) s invalid_value/400; neznámé ID a ID kontejneru s unknown_task/404.
- Parametrizovat chybějící pole, null, číslo, řetězec: invalid_value/400; další klíč: usage_error/400. Odmítnuté požadavky nesmí uložit preferenci.
- Novou route ověřit proti cizímu Origin (403 cross_origin); podle stávajícího guardu také cizí Sec-Fetch-Site a ne-JSON tělo (415 unsupported_media_type). U zamítnuté archivace zůstane preference prázdná.

Testy používají dočasné lokální repozitáře a sqlite, žádné živé služby nebo modely.

## 5. Ověření a realizační dokumentace

Plánovací fáze testy nespouští a implementaci nemění. Builder po změně spustí z kořene repozitáře:

1. `just pytest tests/run/test_queue_prefs.py tests/web/test_web_backlog_queue.py` — konkrétní akceptační testy.
2. `just lint` a `just typecheck` — povinné kontroly.
3. `just pytest tests/run tests/web` — regresní pokrytí změněného store, přímých volajících queue/task a backlog/HTTP API. Rozdělit podle adresářů, pokud to vyžaduje časový limit; počítat s několika minutami na adresář a rezervou. Nejde o celou testovací sadu.

Nespouštět web-build, web-test ani browser testy: frontend se nemění. Při selhání opravit pouze příčiny související s tímto úkolem a opakovat dotčené kontroly.

Do povoleného dokumentačního souboru zaznamenat výslednou DB migraci, pravidla archived podle statusu, route a chyby, zachování ostatních preferencí a skutečné výsledky ověření. Neuvádět neprovedené testy jako úspěšné. Úkol je hotový, když oba směry archivace fungují přes API, cancelled je archivovaný bez zápisu, nehotové tasky se odmítají, preference přežije všechny tři stávající zápisy a stará DB se migruje bez ztráty dat.
