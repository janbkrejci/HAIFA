# Diagnostika rychlého retry

Retry z detailu běhu i Backlogu musí při přijatém novém pokusu vrátit HTTP 202. Odmítnutý start musí zachovat svůj chybový kód a původní pokus. Registrace pending operace a úklid po claimu nebo exitu zůstávají součástí životního cyklu.

Browser assertion pro POST retry při neočekávaném statusu vypíše HTTP status, celé tělo odpovědi a `server.report(task_id)` včetně serverového logu a logů subprocessů. Test neopakuje POST.

Řízené testy launcheru ověřují dokončení subprocessu před registrací operace, pro úspěšný claim i odmítnutý retry. Další test pozdrží úklid původního procesu až za claim nového pokusu stejného run ID. Kontroluje zachování nového vlastníka a pokusu a prázdnou tabulku operací po úklidu. Synchronizaci určují události vláken.
