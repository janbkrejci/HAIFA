# T78 — Prohlížečový test tajného terminálu

Testy ověřují distribuovaný statický dashboard přes Playwright a skutečné API terminálu. Používají existující `advice_server.dashboard`, který spouští Uvicorn na `127.0.0.1` s dynamickým portem a dočasným repozitářem i HAIFA home, a `_launch` ze stávajícího prohlížečového testu. Nevyžadují model ani externí službu.

První scénář po načtení dashboardu stiskne samostatně Control, Shift, Control, Shift, ověří viditelný dialog a fokus příkazového vstupu. Zadá `echo haifa-terminal`, ověří skutečný stdout, počká na dokončení příkazu a zadá `cd` do dočasného adresáře s mezerou v názvu. Prompt musí zobrazit jeho absolutní cestu. Escape dialog odstraní.

Druhý scénář v čerstvé stránce stiskne Control, Shift, A, Control, Shift. Po vykreslovacím snímku musí overlay stále chybět. Stisky používají klávesnici prohlížeče, nikoli syntetické DOM události.

Rozsah tvoří pouze nový `aifactory/tests/e2e/test_terminal_browser.py`, tato specifikace a dokumentace T78. Sdílené helpery, ostatní testy, backend ani frontend se nemění. Nový soubor má vlastní marker `browser` a skupinu `e2e`.

Ověření: `just pytest tests/e2e/test_terminal_browser.py -n0`. Lint, formátování a mypy se cílí na nový soubor. Pro mypy použít z `aifactory` příkaz `MYPYPATH=tests:tests/e2e uv run mypy --follow-imports=silent tests/e2e/test_terminal_browser.py`, který ověří nový soubor a potlačí diagnostiku nezměněných importovaných helperů s dynamickými úpravami `sys.path`.
