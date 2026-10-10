Postav minimální review stránku prototypu: `haifa-proto serve [--port N]` spustí lokální server se seznamem otevřených PR a tlačítky Schválit a Vrátit.

Where: `prototype/src/haifa_proto/web.py`, jedna HTML šablona v `prototype/src/haifa_proto/templates/`, testy v `prototype/tests/`.

Done means:
- Server je Starlette (rozhodnutí D3 v `docs/product-brief.md`). Výchozí port bere z `.factory/local.yaml`, jinak 4700.
- Stránka vypíše otevřené PR z `task_runs` a z providera: task id a titulek, modul a step, větev, diff stat, výsledky gates a testů, náklady, harness a model každého kroku.
- Schválit volá tutéž funkci jako `haifa-proto task approve`, Vrátit tutéž jako `haifa-proto task return` s poznámkou z formuláře. Výsledek operace se ukáže na stránce.
- Testy přes Starlette TestClient s providerem `local`: GET vypíše PR ze vzorového stavu, POST schválení vede na merge a `status: done` v `base`, POST vrácení spustí nový běh s poznámkou (falešný harness).

Out of scope: ostatní obrazovky dashboardu, Vue frontend, editory, přihlašování.

Pevná omezení:
- Stránka nemá vlastní logiku. Vše volá funkce core, které používá CLI.
- Testy nevolají model.
- `vendor/` se neupravuje.
