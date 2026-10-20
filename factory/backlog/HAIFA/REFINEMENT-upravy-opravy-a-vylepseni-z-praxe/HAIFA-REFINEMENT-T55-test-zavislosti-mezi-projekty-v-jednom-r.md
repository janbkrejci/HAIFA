---
id: HAIFA-REFINEMENT-T55
title: "Test: závislosti mezi projekty v jednom repu"
status: todo
workflow: build-test
depends_on: []
writes: [aifactory/tests/backlog/test_cross_project_deps.py]
---

## Zadání
Závislost `depends_on` na task jiného projektu (jiného kořene backlogu) ve stejném repu už dnes funguje. `Backlog.by_id` je společný pro celé repo, kontrola odkazů (`check_backlog`, kód `unknown_ref`) hledá id globálně, funkce `unmet` vyhodnocuje stav globálně a `select_ready` (factory start) prochází celé repo. `container_graph` zobrazí závislost mimo kontejner jako externí uzel a `link_task` dovolí přidat libovolné id. Žádný test to ale nehlídá.

Co udělat:
- Přidat jediný nový testový soubor `aifactory/tests/backlog/test_cross_project_deps.py` s backlogem o dvou projektech (např. A a B), kde task `B-S01-T01` má `depends_on: [A-S01-T01]`. Fixture si postav podle stávajících testů backlogu a fronty.
- Ověřit:
  - `check_backlog` nehlásí `unknown_ref`,
  - `unmet` vrací `not_done`, dokud `A-S01-T01` není `done`, a prázdný seznam po jeho dokončení,
  - `select_ready` task B nespustí, dokud blokátor není hotový, a po jeho dokončení ho nabídne,
  - `link_task` dovolí přidat závislost na task jiného projektu,
  - `container_graph` projektu B ukáže `A-S01-T01` jako externí uzel s hranou.
- Neměň produkční kód. Pokud některá kontrola odhalí chybu, nahlas ji jako follow-up a test označ `xfail` s odkazem na follow-up.

Mimo rozsah: auto-continue řetězu napříč projekty (samostatný task), změny UI a produkčního kódu.

Hotovo znamená:
- `aifactory/tests/backlog/test_cross_project_deps.py` existuje a jeho testy procházejí (případně jsou `xfail` s nahlášeným follow-upem).
- Ostatní testy zůstávají zelené.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
