# Běžící operace tasků

`task_operations` v trace DB drží `operation_id`, `task_id`, `action`, `pid` a `started_at`. Spuštění přes dashboard a členové paralelní fronty vytvářejí evidenci hned po spuštění procesu; publikace z CLI ji vytváří při vstupu do publikačního toku.

Přehled a kanban používají stejný read-only snapshot a stejné odvození stavu. Živá operace znamená „běží“ i bez nového běhu, při retry starého běhu a při opakovaném publish s uloženým `pr_error`. Čtení původní chybu nemaže. Skutečný živý běh má přednost a zachová fázi, cenu i pauzu.

Frontend identifikuje pending řádek stabilním `operation_id` a odkazuje na detail tasku v Backlogu. Po claimu přejde na identitu a detail skutečného běhu; jeho fáze, pauza i cena zůstanou zachovány. Ovládání pause/resume/stop se nabízí pro skutečné běhy.

Položka přehledu před claimem vrací `run_id: null` a samostatné `operation_id`; pole `workflow` obsahuje akci. Skončená operace se nezobrazuje. Launcher ji odstraní po skončení procesu, ProcessRunner po claimu nebo neúspěšném startu a store při úklidu mrtvých lokálních procesů. Zobrazení samotné DB nemění.

Evidence operací neovlivňuje alokaci slotů: rozhodují skutečné živé `task_runs` a otevřené PR. Starší databáze bez `task_operations` zachovají dosavadní chování; zapisující store tabulku vytvoří automaticky.

Cílené ověření: `test_task_operation_store.py`, `test_web_launcher.py`, `test_web_overview.py`, `test_web_backlog.py`, `test_parallel_chain.py` a `test_task_publish.py`.

Regresní testy kontrolují přímo řádky `task_operations` po claimu, exitu, chybě publikace a ukončení procesu. Deterministický test timeoutu ProcessRunner ověřuje také ukončení a čekání na proces. Překryv živého běhu s operacemi testuje zachování workflow, fáze, pauzy, ceny a jediného slotu. Frontendové testy ověřují dva pending řádky, jejich taskové odkazy a nahrazení jedné operace skutečným během při změně pořadí.
