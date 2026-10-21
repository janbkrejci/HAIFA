# Výsledek vyšetření retry HTTP 500

CI běhu 39521521254 na main 421d714 zaznamenalo HTTP 500 u varianty `backlog` testu `test_retry_from_run_and_task_detail`. Soubor `/tmp/haifa-main-final-failure.log` obsahuje pouze status a traceback browser assertion; neobsahuje JSON odpovědi ani log neúspěšného subprocessu. API GitHub Actions pro tento běh nevrátilo žádné uložené artefakty.

Obě varianty v `/tmp/haifa-retry-diagnosis` mají úspěšné retry. Také dodatečný operátorův trasovaný běh `/tmp/haifa-retry-traced.log` prošel. V tomto worktree prošlo deset spuštění obou původních variant v Chrome (20 scénářů) a jedno spuštění obou variant v bundlovaném Chromiu (2 scénáře). Tento výsledek nedokazuje odstranění původního selhání.

Doplněná assertion při neúspěchu zachová tělo HTTP odpovědi a report serveru, který obsahuje serverový log i logy spuštěných procesů. Nové testy launcheru vynucují exit dítěte před registrací operace a úklid starého procesu po claimu retry. Ověřují HTTP 202 pro claim, HTTP 409 pro odmítnutí, zachování původního odmítnutého pokusu a úklid operací. Všechny tyto stavy prošly i bez změny backendu.

Cílené ověření `test_web_launcher.py`, `test_web_runs.py`, `test_task_operation_store.py` a `test_task_retry.py` prošlo: 94 testů. Lint a kontrola formátu i mypy byly omezeny na změněné Python soubory podle pravidel builderu; mypy používá `MYPYPATH=tests:tests/run:tests/workflow` pro existující testovací helpery.

Konkrétní příčina původní HTTP 500 nebyla zachycena a oprava backendu není součástí tohoto výsledku. Registrace, úklid, claim a ochrany tasků v produkčním kódu se neměnily.
