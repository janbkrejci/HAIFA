# Diagnostika retry a souběžný životní cyklus

Browser test retry z detailu běhu i Backlogu při neočekávaném HTTP statusu vypíše status, celé tělo odpovědi a `server.report(task_id)`. Report zahrnuje dostupný stav běhů, serverový log a logy subprocessů. Očekávaná odpověď 202 i ostatní původní assertions zůstávají zachované; test neopakuje POST.

Integrační testy launcheru vynucují tři pořadí událostí: úspěšný claim a exit dítěte před registrací operace; odmítnutí a exit před registrací; úklid původního procesu až po claimu nového pokusu stejného run ID. Ověřují HTTP 202 pro claim, původní kód i zprávu odmítnutí s HTTP 409, zachování odmítnutého pokusu a zachování stavu, PID a čísla nového pokusu při starém úklidu. Kontrolují také prázdnou tabulku `task_operations` po úklidu. Pořadí určují události vláken a skutečné dokončení subprocessu, nikoli pevné prodlevy. Testy používají lokální stub bez živých modelů a služeb.

Podnětem bylo jednorázové HTTP 500 v CI běhu 39521521254 na main 421d714. Původní CI výstup neobsahuje JSON odpovědi ani log neúspěšného subprocessu. Vyšetřovací běh T23 ověřil 94 cílených testů a 22 browser scénářů, aniž původní selhání zachytil. Tato změna dodává diagnostiku a regresní pokrytí; nedokládá opravu konkrétní příčiny původní HTTP 500. Produkční registrace, úklid, claim a ochrany tasků zůstávají zachované.

Cílené ověření používá `test_web_launcher.py`, `test_web_runs.py`, `test_task_operation_store.py`, `test_task_retry.py` a oba scénáře `test_retry_browser.py`. Builder kontroluje lint, formát a mypy změněných Python souborů; mypy používá `MYPYPATH=tests:tests/run:tests/workflow` pro existující helpery. Globální `just lint`, `just typecheck` a cílené regrese provádí tester. Linux CI a publikaci zajišťuje workflow a operátor.
