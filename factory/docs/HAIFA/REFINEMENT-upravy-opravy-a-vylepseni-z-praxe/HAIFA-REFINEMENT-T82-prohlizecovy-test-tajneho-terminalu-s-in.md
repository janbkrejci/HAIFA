# HAIFA-REFINEMENT-T82 — Implementace a ověření

Stávající test již používal xterm.js. Doplněna je explicitní kontrola `.xterm`, skutečného TTY a interaktivního programu přes interpret `sys.executable`. Dočasný Python skript čeká na vstup `q` a následně na Esc. Aserce výsledku 27 dokládá, že Esc dorazil programu; overlay přitom zůstává otevřený.

Další krok spustí `sleep 100` (na Windows Python `time.sleep(100)`), po potvrzení připravenosti odešle Ctrl+C a ověří odpověď shellu na další příkaz. Výsledkové markery nejsou doslova obsažené v zadávaných příkazech. Zůstává test vimu, změny adresáře, zavření tajnou sekvencí a sekvence přerušené klávesou A. Fixture na Windows přeskočí testy pouze tehdy, když úspěšné `GET /api/terminal` oznámí `pty: false`.

Vyhledání přímých volajících v celém `aifactory/tests/` našlo použití upravené fixture pouze v tomto souboru. Ostatní soubory e2e ani implementace terminálu se nemění.

Ověření na macOS s Pythonem 3.12:

- `just pytest tests/e2e/test_terminal_browser.py -n0` — všechny tři testy prošly.
- `cd aifactory && uv run ruff check tests/e2e/test_terminal_browser.py` — cílený lint.
- `cd aifactory && uv run ruff format --check tests/e2e/test_terminal_browser.py` — kontrola formátování.
- `cd aifactory && MYPYPATH=tests:tests/run:tests/e2e uv run mypy --follow-imports=silent tests/e2e/test_terminal_browser.py` — bez typových chyb. MYPYPATH zpřístupňuje sdílené testovací helpery při kontrole jediného souboru.

Windows větev nebyla na tomto stroji spuštěna. Backendová ani frontendová chyba se při ověření neprojevila.
