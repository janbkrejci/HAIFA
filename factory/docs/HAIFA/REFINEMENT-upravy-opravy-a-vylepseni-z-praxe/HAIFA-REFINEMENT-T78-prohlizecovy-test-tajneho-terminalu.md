# T78 — Implementace a ověření

Přidány dva prohlížečové scénáře tajného terminálu. První ověřuje otevření sekvencí modifikátorů, automatický fokus, skutečný výstup `echo haifa-terminal`, změnu cwd po `cd` do adresáře s mezerou a zavření pomocí Escape. Kontrola stdout je oddělená od přepisu příkazu, který obsahuje stejný text. Druhý ověřuje zrušení rozpracované sekvence klávesou A.

Lokální fixture používá existující dočasný repozitář, loopback dashboard a spouštěč Chrome/Chromium. Každý scénář má nový prohlížeč; fixture po testu zavře prohlížeč i server. Testy volají skutečný backend bez mockování terminálu a bez živých modelů. Produkční soubory a ostatní testy zůstaly beze změn. Vyhledání v celém `aifactory/tests/` našlo použití nové fixture pouze v novém souboru; žádné další přímé volající není třeba ověřovat.

## Kontroly

- `just pytest tests/e2e/test_terminal_browser.py -n0` — oba testy prošly, 12,69 s, macOS / Python 3.12.13.
- Z `aifactory`: `uv run ruff check tests/e2e/test_terminal_browser.py` a `uv run ruff format --check tests/e2e/test_terminal_browser.py` — úspěšné.
- Z `aifactory`: `MYPYPATH=tests:tests/e2e uv run mypy --follow-imports=silent tests/e2e/test_terminal_browser.py` — úspěšné, jeden zdrojový soubor. Původní spuštění bez těchto voleb hlásilo nedohledané importy sdílených helperů (`advice_fixture`, `advice_server`, následně `run_repo` a `workflow_fakes`). Opravený příkaz nastavuje cesty k přímým helperům a omezuje diagnostiku na změněný soubor; pytest tyto importy řeší svou konfigurací a existujícími úpravami `sys.path`.

Kontroly jsou omezené na nový testovací soubor. Celou e2e sadu ani frontendové kontroly tato změna nevyžaduje. Test neodhalil chybu backendu či frontendu.
