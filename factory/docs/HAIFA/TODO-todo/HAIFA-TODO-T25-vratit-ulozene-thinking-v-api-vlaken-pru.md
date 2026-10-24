# API průvodce vrací uložené thinking

Seznam, detail i vytvoření vlákna nyní vracejí `thinking` z daného vlákna. Změna je v `Thread.summary()`; `Thread.detail()` pole přebírá automaticky. Formát uložených vláken a výběr modelu zůstávají zachované.

Regresní testy porovnávají odpovědi API s uloženým vláknem pro zděděné `high` i fallback `medium`. Ověřují také zachování `high` při načtení z disku po změně nastavení. Testy používají lokální fake harness bez živých modelů a služeb.

Před opravou obě varianty regrese selhaly na chybějícím poli `thinking`. Po opravě prošlo všech 57 testů v `tests/web/test_web_assistant.py` (`uv run pytest tests/web/test_web_assistant.py -n0` z `aifactory/`), lint, kontrola formátu a mypy obou změněných Python souborů. Globální kontroly přísluší testovacímu kroku workflow.
