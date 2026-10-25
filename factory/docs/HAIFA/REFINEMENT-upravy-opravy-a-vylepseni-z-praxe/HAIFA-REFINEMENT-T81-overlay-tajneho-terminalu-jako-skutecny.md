# HAIFA-REFINEMENT-T81 — Implementace a ověření

Řádkový overlay nahradil xterm.js 6.0.0 s addon-fit 0.11.0. Nepoužívaný frontendový exec klient byl odstraněn. Backend zůstává beze změny. Oba soubory THIRD_PARTY_NOTICES obsahují verze a úplné MIT licence obou balíčků.

Jednotkové testy ověřují rozměry při vytvoření, původní bajty streamu, pořadí vstupu, resize, fokus, zachování Esc, restart po EOF, ukončení při zavření/unmount/pagehide, úklid pozdního vytvoření a zprávy při nedostupnosti. App test ověřuje tajnou sekvenci z textarea, která zastavuje propagaci.

Prohlížečový test používá skutečný PTY a dodaný statický build. Ověřuje příkazy, změnu adresáře, tajnou sekvenci a vim včetně insert režimu, Esc a :q. Návrat z vimu potvrzuje marker vypsaný shellem jako pokračování původního příkazu; test tak neposílá nový vstup během obnovy terminálových režimů při ukončování vimu. Vim test se přeskočí pouze při chybějícím vim. POSIX fixture nastavuje /bin/sh, aby nezávisela na uživatelských shellových pluginech.

Cílené ověření:

- `cd aifactory/web && bun run test src/lib/terminal.test.ts src/components/terminal/TerminalOverlay.test.ts src/App.test.ts src/lib/secretKeys.test.ts`
- `just web-build` (zahrnuje vue-tsc --noEmit a sestavení distribuovaných assetů)
- `just pytest tests/e2e/test_terminal_browser.py -n0`
- `cd aifactory && uv run ruff check tests/e2e/test_terminal_browser.py && uv run ruff format --check tests/e2e/test_terminal_browser.py`
- `cd aifactory && MYPYPATH=tests:tests/run:tests/e2e uv run mypy --follow-imports=silent tests/e2e/test_terminal_browser.py`

MYPYPATH zpřístupňuje sdílené testovací helpery při kontrole jediného souboru; bez něj cílené mypy hlásí chybějící importy helperů.
