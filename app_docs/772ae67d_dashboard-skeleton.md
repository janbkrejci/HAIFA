# Dashboard: kostra (`factory obs`)

Lokální webový dashboard HAIFA. Backend je Starlette/uvicorn aplikace v balíčku `aifactory`, frontend je Vue 3 + Vite + TypeScript se vzhledem převzatým (zkopírovaným) z visualizeru sssf. Obrazovky jsou zatím prázdné; jejich obsah řeší úkoly 3.2 až 3.6.

## Spuštění

```bash
factory obs [--port N] [--no-open] [--repo PATH] [--json]
just dash [--port N] [--no-open]      # = uv run --project aifactory factory obs
```

- Server poslouchá **jen na `127.0.0.1`** (`web/server.py: HOST`, nejde změnit).
- Port: `--port`, jinak `port` z `.factory/local.yaml` (`load_local(root).port`, výchozí 4700).
- Před startem `check_port` zkusí port zabrat; když je obsazený, příkaz skončí kódem 2 (`port_in_use`). Port mimo 1–65535 → `invalid_value`, mimo git repo → chyba z `ConfigError`.
- Bez `--no-open` otevře prohlížeč až poté, co uvicorn nastartuje (vlákno čeká max. 10 s).
- S `--json` vypíše před startem obálku `{url, host, port, repo, version}`, jinak `HAIFA dashboard: <url>  (Ctrl+C ukončí)`.

## Backend — `aifactory/src/aifactory/web/`

- `app.py` — `create_app(repo, *, static_dir=None)`:
  - `GET /api/health` → `envelope_ok({"version", "repo"})`, tedy stejná obálka `{ok, data, error, warnings}` jako `--json` CLI.
  - Chyby pod `/api/` jsou také obálky: 404 → `not_found`, jiné HTTP chyby (např. 405) → `usage_error`, výjimky → `internal_error` (500).
  - `/` servíruje build frontendu ze `STATIC_DIR` (`web/static/`). Chybí-li `index.html`, `/` vrátí 503 s textem „run: just web-build“.
  - `TrustedHostMiddleware` povoluje jen hosty `127.0.0.1` a `localhost`.
- `server.py` — `HOST`, `dashboard_url`, `check_port`, `PortInUseError`, `serve(app, port, open_browser=...)`.
- `static/` — commitnutý build frontendu (index.html, JS/CSS, fonty Play, logo), takže `factory obs` za běhu nepotřebuje Node.
- `cli.py` — nový podpříkaz `obs` (`_add_obs_command`, `_obs`, dispatch).
- `skill/codes.py` — nové chybové kódy `port_in_use` a `not_found`.
- `pyproject.toml` — závislosti `starlette`, `uvicorn`; dev závislost `httpx2` (pro `TestClient`). `uv.lock` aktualizován.

## Frontend — `aifactory/web/`

- `src/App.vue` — horní lišta (logo, „HAIFA“), navigace se čtyřmi obrazovkami s ikonami z `lucide-vue-next`, přepínač světlého/tmavého motivu a odznak s názvem repa a verzí z `/api/health` (při chybě „API nedostupné“).
- `src/lib/router.ts` — hash routing `#/backlog`, `#/runs`, `#/review`, `#/settings`; neznámý hash → backlog. Popisky: Backlog, Běhy, Review, Nastavení.
- `src/lib/api.ts` — `getApi<T>()` rozbalí obálku a při `ok: false` vyhodí `ApiError` s `error.code`; `fetchHealth()`.
- `src/lib/theme.ts` — motiv v `localStorage` (`haifa-theme`), jinak podle OS.
- `src/views/*View.vue` + `src/components/EmptyScreen.vue` — prázdné obrazovky.
- `src/style.css`, `src/main.ts` (font Play přes `@fontsource/play`), `index.html`, `public/logo.svg`.
- `vite.config.ts` — build do `../src/aifactory/web/static`; dev server na `127.0.0.1:4701` s proxy `/api` na `127.0.0.1:$PORT` (výchozí 4700); vitest s `happy-dom`.
- `package.json`, `bun.lock`, `tsconfig.json`; `.gitignore` ignoruje `aifactory/web/node_modules/`.

## Recepty v `justfile`

| Recept | Co dělá |
|---|---|
| `just dash` | `factory obs` |
| `just web-build` | `bun install --frozen-lockfile && bun run build` (vue-tsc + vite build do balíčku) |
| `just web-test` | `vue-tsc --noEmit` + `vitest run` |
| `just web-dev` | Vite dev server na :4701, `/api` proxy na běžící `just dash` |
| `just test` | nově závisí na `web-test`, pak pytest |

Pro build a testy frontendu je potřeba `bun`.

## Testy a ověření

- `aifactory/tests/web/test_web_app.py` — health, 404/405 obálky, servírování statiky, 503 bez buildu, odmítnutí cizího hostu, zabalený build.
- `aifactory/tests/web/test_web_server.py` — `HOST` je loopback, `check_port`, `serve` binduje na 127.0.0.1.
- `aifactory/tests/web/test_obs_cli.py` — JSON obálka, port z `local.yaml`, textový výstup, obsazený port, špatný port, spuštění mimo git repo. Pomocník: `tests/web/web_repo.py`.
- `aifactory/tests/test_smoke.py` — `obs` vyřazen z kontroly „not implemented yet“.
- Vitest: `App.test.ts` (4 obrazovky v navigaci, přepnutí na hashchange, repo z health, nedostupné API), `lib/api.test.ts`, `lib/router.test.ts`.

Ověření: `just test && just typecheck && just lint`, pak `just dash` a v prohlížeči `http://127.0.0.1:4700/` nebo `curl http://127.0.0.1:4700/api/health`.

Po změně frontendu je nutné spustit `just web-build` a commitnout nový obsah `web/static/` (názvy assetů obsahují hash).

Specifikace: `specs/772ae67d_dashboard-skeleton_v2.md`.
