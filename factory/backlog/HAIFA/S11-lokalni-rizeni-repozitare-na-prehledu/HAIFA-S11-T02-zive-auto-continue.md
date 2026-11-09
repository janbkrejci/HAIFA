---
id: HAIFA-S11-T02
title: Auto continue s okamžitou bariérou dalších startů
status: todo
depends_on: [HAIFA-S11-T01]
writes: [aifactory/]
test_timeout: 1200
---

## Zadání

Napojit run/queue.py, members.py, heal.py, retry.py a spouštěcí cesty CLI/web na lokální repo politiku z T01 místo effective(task, auto_continue). Dohledat run_chain, select_next/select_ready, start_factory, publish, approve, blokátory, needs_environment, návrat z kvóty a paralelní refill. Repo přepínač platí napříč projekty, nemění rozsah výběru dosavadního řetězu.

Potvrzené off zastaví všechny další automatické starty v tomto repo. Rozhodnutí o přijetí startu synchronizovat s update nastavení, ověřit i v child procesu/claim cestě; nestačí read před výběrem ani cache při startu řetězu. Již přijaté běhy doběhnou, nevzniká další refill, retry/heal ani navazující task po publish/approve. Vnitřní opravy/fáze současného běhu pokračují. --auto nesmí obejít lokální off; převést na deprecated kompatibilní parametr s jasnou zprávou a bez tichého zapínání. Ruční spuštění jednoho tasku zůstává možné při off. Zapnutí samo nevytvoří nový řetěz.

Hotovo: změna za běhu funguje bez restartu/commitu u sekvenčního i paralelního řetězu, stop důvod je srozumitelný. Deterministické regrese pro off během běhu, čekání na CI, mezi select a claim/spawn, při lock retry, pro --auto a automatický heal; již běžící členy nezabít. Otestovat i on, dvě repo, dvě instance workeru a restart. Kandidáti v tests: run/test_auto_continue.py, test_parallel_chain.py, test_chain_parts.py, test_factory_start.py, test_queue_busy.py, test_auto_heal.py, test_task_publish.py a review/test_approve_continue.py; vybrat dotčené případy a spustit každý editovaný soubor.

## Běhy

<!-- doplňuje HAIFA při schválení PR -->

