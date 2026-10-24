# HAIFA-S01-T46 — Archivace hotových tasků v backendu

Archivace je provozní preference v trace DB. Nemění status ani soubory backlogu a API tasky nadále vrací všechny.

`task_queue.archived` má typ `INTEGER NOT NULL DEFAULT 0`. Při otevření store se chybějící sloupec doplní přes `_add_columns`, včetně existujících databází s uloženým pořadím a vyloučením. `QueuePrefs.archived` obsahuje ID s aktivním příznakem. Nové pole je za původními poli, takže zachovává jejich poziční argumenty.

`set_archived` mění pouze archivaci a čas aktualizace. Pořadí, přesun na začátek fronty a vyloučení archivaci zachovávají. Úklid odstraňuje pouze řádky bez pořadí, vyloučení i archivace.

V taskovém JSON seznamu, stromu i detailu platí podle skutečného `task.status`:

| Status | `archived` |
| --- | --- |
| `cancelled` | Vždy `true`, bez ukládání preference |
| `done` | Podle příznaku v trace DB |
| Ostatní | Vždy `false`, i při uložené preferenci |

`POST /api/backlog/tasks/{task_id}/archive` přijímá pouze `{"archived": true}` nebo `{"archived": false}`. Stejná relativní route je registrovaná i pod `/api/repos/{id}/`. Úspěch vrací HTTP 200 se standardním envelope a `data: {task_id, archived}`. Platí stávající ochrana zápisů podle Origin, Sec-Fetch-Site a Content-Type.

Neexistující task nebo ID kontejneru vrací `unknown_task` (404). Task mimo `done`, chybějící pole nebo neboolovská hodnota vrací `invalid_value` (400); další klíče vrací `usage_error` (400). Validace předchází otevření zapisujícího store. Čtení backlogu bez trace DB ji nevytváří.

## Ověření

- `just pytest tests/run/test_queue_prefs.py tests/web/test_web_backlog_queue.py`: 34 testů prošlo.
- Ruff lint a kontrola formátování pěti změněných Python souborů prošly.
- `uv run mypy` s explicitními cestami těchto pěti souborů: bez chyb.
- `git diff --check`: bez chyb.

Testy ověřují obousměrný zápis archivace přes API, detail a seznam tasků, pravidla podle statusu, zachování backlog souborů, zamítnuté požadavky a ochranu zápisů, persistenci po otevření DB, migraci staré tabulky a souběh s ostatními preferencemi.

## Ověření po návratu z testovací fáze

Testovací fáze potvrdila lint a celou webovou sadu (652 testů). Typová kontrola skončila limitem 60 s, sada přímých volajících limitem 160 s a run sada limitem 300 s. Log přímých volajících obsahoval chyby, ale timeout ukončil běh před výpisem tracebacků.

Při opakovaném ověření:

- `just pytest tests/test_remote_database.py -n0 -x --tb=short`: 17 testů prošlo za 18,52 s.
- `just pytest tests/run/test_queue_prefs.py tests/run/test_task_operation_store.py tests/run/test_followups_queue.py tests/web/test_web_backlog_queue.py`: 48 testů prošlo za 61,43 s, s 13 existujícími upozorněními Pydantic.
- `just pytest tests/backlog/test_cross_project_deps.py tests/config/test_config_publish.py tests/library/test_library_config_edit.py tests/providers/test_providers_publish.py tests/review/test_branch_cleanup.py tests/review/test_approve_merge_retry.py tests/review/test_ci_gate.py tests/demo/test_demo_web.py -x --tb=short`: 105 testů prošlo za 145,55 s, s 91 existujícími upozorněními Pydantic. Spolu se samostatně ověřenou vzdálenou DB tak prošlo všech 122 testů z původního neúspěšného příkazu; chyby se nereprodukovaly.
- Typová kontrola pěti změněných Python souborů, Ruff lint i kontrola formátování opět prošly.

Samotný timeout není důkaz chyby implementace. Celá run sada ani celoprojektová typová kontrola nebyly v builder fázi opakovány; jejich dokončení posuzuje navazující testovací fáze. Frontend a statický build zůstávají v rozsahu T47.

## Ověření po rebase na main 15f5cda

Kontrola aktuální implementace potvrdila migraci `task_queue`, zachování archivace při ostatních zápisech i registraci a validaci API. Testovací fáze `quality/16` dokončila lint, celoprojektovou typovou kontrolu (493 souborů), 122 testů přímých volajících a 165 testů fronty a jejích konzumentů.

Webová sada skončila výsledkem 651 prošlých a jednoho selhaného testu: `tests/web/test_web_fs.py::test_pick_one_at_a_time` překročil desetisekundové čekání na start falešného dialogu. Samostatné opakování příkazem `just pytest tests/web/test_web_fs.py::test_pick_one_at_a_time -n0 --tb=short` prošlo za 3,15 s. Cesta výběru složky nevolá archivaci ani trace DB; příčina původního prodlení nebyla reprodukována. Zdrojový kód ani test výběru složky proto nebyly změněny.

Po rebase opět prošlo všech 34 testů příkazem `just pytest tests/run/test_queue_prefs.py tests/web/test_web_backlog_queue.py`. Výsledek samostatného opakování nenahrazuje výsledek celé webové sady; její poslední běh měl výše popsané selhání.
