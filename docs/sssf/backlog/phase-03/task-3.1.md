Založ dashboard: Python backend ve Starlette a Vue frontend převzatý z visualizeru sssf, spuštěný příkazem `factory obs`.

Where: `aifactory/src/aifactory/web/` (backend), `aifactory/web/` (frontend), CLI, `justfile`, `aifactory/tests/web/`. Zdroj frontendu: `vendor/sssf/apps/visualizer/` (Vue 3, Vite, TypeScript, `lucide-vue-next`, font Play).

Done means:
- `factory obs [--port N] [--no-open]` spustí server na `127.0.0.1` (port z `.factory/local.yaml`, výchozí 4700) a otevře dashboard v prohlížeči. `just dash` volá `factory obs`.
- Frontend má kostru se čtyřmi obrazovkami v navigaci: Backlog, Běhy, Review, Nastavení (zatím prázdné) a stejný vzhled jako visualizer.
- Backend servíruje build frontendu z balíčku a má API pod `/api/`. `GET /api/health` vrací verzi a cestu k repu. Odpovědi API mají stejnou obálku jako `--json` CLI.
- Build frontendu se spouští jedním receptem a výsledek je součástí balíčku, takže `factory obs` funguje bez Node za běhu.
- `just test` spouští i typecheck frontendu (`vue-tsc`) a jeho unit testy (vitest). Testy backendu přes Starlette `TestClient`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: obsah obrazovek (3.2 až 3.6).

Pevná omezení:
- Server nikdy neposlouchá na jiné adrese než `127.0.0.1`.
- `vendor/` a `prototype/` se nemění. Visualizer se kopíruje, neimportuje.
