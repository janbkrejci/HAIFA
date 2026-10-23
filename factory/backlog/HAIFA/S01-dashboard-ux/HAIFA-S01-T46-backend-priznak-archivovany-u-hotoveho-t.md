---
id: HAIFA-S01-T46
title: "Backend: příznak archivovaný u hotového tasku (trace DB a API)"
status: todo
workflow: plan-build-test
depends_on: []
writes: [aifactory/src/aifactory/run/store.py, aifactory/src/aifactory/web/backlog.py, aifactory/src/aifactory/web/app.py, aifactory/tests/run/test_queue_prefs.py, aifactory/tests/web/test_web_backlog_queue.py]
---

## Zadání
Kanban má mít možnost schovat hotové a zrušené tasky, které si člověk prohlédl. Nebude to nový stav. Bude to příznak „archivovaný“. Jako pořadí fronty a Odloženo jde o provozní nastavení, ne o obsah tasku. Ukládá se proto v trace DB a nic se necommituje do backlogu.

Co udělat:
- `aifactory/src/aifactory/run/store.py`: do tabulky `task_queue` přidej sloupec `archived INTEGER NOT NULL DEFAULT 0`. Ve schématu ho přidej přes `_add_columns`, aby fungoval i u existujících databází. `QueuePrefs` dostane `archived: frozenset[str]`, které plní `queue_prefs()`. Přidej metodu `set_archived(task_id, archived)` podle vzoru `set_excluded`. Uprav `_prune_queue`, aby nemazal řádky s `archived = 1`. Zápisy `set_queue_order`, `queue_front` a `set_excluded` nesmí příznak archived přepsat ani smazat.
- `aifactory/src/aifactory/web/backlog.py`: `_task_json` vrací `archived: bool`. Zrušený task (`status: cancelled`) je archivovaný vždy, „rovnou“, a příznak nepotřebuje. Hotový task je archivovaný jen s příznakem v DB. Ostatní stavy mají vždy `false`. Přidej funkci `archive(repo, task_id, body)` s tělem `{archived: bool}` (ostatní klíče odmítne přes `_check_keys`). Pokud task neexistuje, vrátí chybu `unknown_task`. Pokud task není hotový (`done`), vrátí `invalid_value`, protože ručně se archivuje jen hotový task. Vrací `{task_id, archived}`.
- `aifactory/src/aifactory/web/app.py`: přidej route `POST /backlog/tasks/{task_id}/archive` podle vzoru `backlog_auto_exclude`, se stejnou ochranou zápisových požadavků. Doplň popis polí v docstringu modulu.
- Testy: `aifactory/tests/run/test_queue_prefs.py` (archived se uloží, přežije změnu pořadí i vyloučení, migrace staré tabulky bez sloupce) a `aifactory/tests/web/test_web_backlog_queue.py` (endpoint, `archived` v JSON backlogu, zrušený task je archivovaný bez příznaku, archivace tasku, který není hotový, se odmítne).

Mimo rozsah: frontend a statický build (řeší T47) a nový stav tasku v souborech backlogu.

Hotovo znamená:
- `POST /api/.../backlog/tasks/<id>/archive` s `{"archived": true}` u hotového tasku vrátí 200 a backlog API pak u tasku vrací `archived: true`. S `false` ho vrací zpátky.
- Zrušený task má v backlog API `archived: true` bez jakéhokoli zápisu, task ve stavu todo má `false`. Archivace tasku, který není hotový, vrátí chybu.
- Příznak přežije `set_queue_order`, `queue_front` i `set_excluded`. Stará trace DB bez sloupce se otevře a sloupec se doplní.
- Nové i dosavadní testy v `aifactory/tests/run/test_queue_prefs.py` a `aifactory/tests/web/test_web_backlog_queue.py` projdou.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
