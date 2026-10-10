# Plán 3.1: Kostra dashboardu (Starlette + Vue z visualizeru, `factory obs`)

## Cíl

`factory obs [--repo PATH] [--port N] [--no-open] [--json]` spustí Starlette/uvicorn server **jen na
`127.0.0.1`** (port z `.factory/local.yaml`, výchozí 4700), servíruje přibalený build Vue frontendu
a API pod `/api/` (zatím `GET /api/health`) se stejnou obálkou jako `--json` CLI
(`aifactory.skill.envelope`). Frontend je kopie vzhledu visualizeru sssf se čtyřmi prázdnými
obrazovkami: Backlog, Běhy, Review, Nastavení. `just dash` volá `factory obs`, `just web-build`
buildí frontend do balíčku, `just test` spouští i `vue-tsc` a vitest.

Mimo rozsah: obsah obrazovek (3.2–3.6). `vendor/` a `prototype/` se nemění, visualizer se
**kopíruje** (ne import, ne symlink). `just obs` (visualizer vývojové factory) zůstává beze změny.

## Zjištěné souvislosti (nečti znovu, pokud nemusíš)

- CLI: `aifactory/src/aifactory/cli.py`. Seznam příkazů `SUBCOMMANDS` (ř. ~34), `build_parser`
  (ř. ~59) větví podle jména na `_add_*_commands`, `_dispatch` (ř. ~1171) volá handlery.
  Obálky: `_emit_ok(data, warnings)`, `_emit_fail(code, message, exit_code=..., ...)`,
  chyby konfigurace přes `_fail_from_exception(exc, as_json, label)` (ConfigError → `invalid_config`).
  `_backlog_root(repo)` ukazuje, jak se řeší `--repo`.
- Obálka: `aifactory/src/aifactory/skill/envelope.py` — `envelope_ok`, `envelope_fail`,
  `envelope_problems` (validátor; **vyžaduje, aby `error.code` byl v `ERROR_CODES`**).
- Registr kódů: `aifactory/src/aifactory/skill/codes.py` (`_CODES`, trojice code/exit/meaning).
  `usage_error` a `internal_error` už existují. `tests/test_skill.py::test_error_codes_complete`
  skenuje literály prvního argumentu `_emit_fail`/`envelope_fail` **v `cli.py`** → každý nový
  kód použitý v `cli.py` musí být v `_CODES`.
- `tests/test_skill.py::test_every_command_has_json` vyžaduje `--json` u **každého** listového
  příkazu → `factory obs` musí mít `--json`. `test_every_command_is_in_skill` kontroluje, že
  skill obsahuje všechny volby; sekce příkazů se generují automaticky (`skill/commands.py`),
  takže stačí mít help texty.
- `tests/test_smoke.py::test_subcommands_not_implemented` volá `main([name])` pro neimplementované
  příkazy → `obs` přidat do výčtu přeskočených (a **nikdy** nevolat `main(["obs"])` bez
  zapatchovaného serveru).
- Nastavení: `aifactory.config.settings.LocalSettings.port` (default 4700), `load_local(root)`,
  `aifactory.config.repo_root(start)` (vyhodí `ConfigError` mimo git).
- `aifactory.__version__` v `aifactory/src/aifactory/__init__.py`.
- pyproject: hatchling, `packages = ["src/aifactory"]`; mypy strict nad `src`, `tests`,
  `validation`; ruff `E,F,I,UP,B`, line-length 100. pytest běží s `-n auto` (xdist).
  Testovací adresáře nemají `__init__.py` → použij unikátní jména souborů testů.
- Visualizer (`vendor/sssf/apps/visualizer`): bun (`bun.lock`), `vite ^7`, `@vitejs/plugin-vue ^6`,
  `vue ^3.5`, `vue-tsc ^3`, `typescript ^5.7`, `lucide-vue-next ^1`, `@fontsource/play ^5.3`.
  Vzhled = `src/style.css` (CSS proměnné, dark/light) + scoped styly topbaru v `src/App.vue`
  (`.topbar`, `.logo`, `.brand`, `.view-toggle`, `.theme-toggle`, `.live-dot`...) + `src/lib/theme.ts`.
  Routing je hash-based (`src/lib/router.ts`). `bun`, `node`, `npm` jsou na PATH.
- `adws/adw_modules/quality.py`: testovací fáze ADW volá `just test`, `just typecheck`, `just lint`.

## Rozhodnutí

1. **Závislosti Pythonu:** do `[project].dependencies` přidat `starlette` a `uvicorn`; do dev
   skupiny `httpx` (vyžaduje ho `starlette.testclient`). `uv lock` / `uv sync` v `aifactory/`.
2. **Build se commituje:** Vite buildí do `aifactory/src/aifactory/web/static/` (mimo gitignore),
   hatch ho tak přibalí do wheelu a `factory obs` funguje z čistého klonu bez Node.
   `aifactory/web/node_modules/` přidat do `.gitignore`. Builder **musí spustit `just web-build`**
   a výsledek nechat ve stromu (commitne se s prací).
3. **Bezpečnost:** `HOST = "127.0.0.1"` je konstanta v `web/server.py`, žádná volba ho nemění.
   Navíc `TrustedHostMiddleware(allowed_hosts=["127.0.0.1", "localhost"])` proti DNS rebindingu
   (testy proto používají `TestClient(app, base_url="http://127.0.0.1:4700")`).
4. **Nové chybové kódy** v `skill/codes.py`:
   - `("port_in_use", "2", "the dashboard port is already taken (factory obs --port N)")`
   - `("not_found", "2", "dashboard API: no such endpoint (HTTP 404)")`
   (API chyby musí projít `envelope_problems`, proto musí být kód registrován.)
5. **`--json` u `factory obs`:** po úspěšné kontrole portu vypíše jednu obálku
   `{"url", "host", "port", "repo", "version"}` a pak blokuje na serveru (logy uvicornu jdou na
   stderr). Chyby (`invalid_config`, `port_in_use`, `invalid_value` pro port mimo 1..65535) jako
   obvyklá chybová obálka s exit 2. Bez `--json` vypíše na stdout jeden řádek
   `HAIFA dashboard: http://127.0.0.1:PORT/  (Ctrl+C ukončí)`.
6. **Frontend package manager:** bun (stejně jako visualizer), `bun.lock` se commituje.
   Unit testy: vitest + `@vue/test-utils` + `happy-dom`. Oxlint a bun server/`shared/` z
   visualizeru se **nepřebírají**.

## Kroky

### 1. Backend `aifactory/src/aifactory/web/`

**`web/__init__.py`**
```python
"""Local dashboard: Starlette app serving the packaged Vue build and the /api/ endpoints."""
from aifactory.web.app import STATIC_DIR, create_app
from aifactory.web.server import HOST, PortInUseError, check_port, dashboard_url, serve
__all__ = [...]
```

**`web/app.py`**
- `STATIC_DIR = Path(__file__).parent / "static"`.
- `create_app(repo: Path, *, static_dir: Path | None = None) -> Starlette`
  (`static_dir=None` → `STATIC_DIR`; parametr existuje kvůli testům).
- `app.state.repo = repo` (resolved `Path`).
- Routy:
  - `Mount("/api", routes=[Route("/health", health, methods=["GET"]), Route("/{path:path}", api_not_found, methods=[všechny běžné])])`.
  - `health` → `JSONResponse(envelope_ok({"version": __version__, "repo": str(request.app.state.repo)}))`.
  - `api_not_found` → `JSONResponse(envelope_fail("not_found", f"no API endpoint {method} {path}"), status_code=404)`.
  - Frontend: pokud `static_dir / "index.html"` existuje → `Mount("/", app=StaticFiles(directory=static_dir, html=True), name="static")`;
    jinak `Route("/", frontend_missing)` vracející `PlainTextResponse` 503 s textem
    `"dashboard frontend is not built; run: just web-build"`.
- `exception_handlers`:
  - `HTTPException`: pokud `request.url.path.startswith("/api/")` → envelope
    (`"not_found"` pro 404, jinak `"usage_error"`), status zachovat; jinak `PlainTextResponse(detail, status)`.
  - `Exception` → pro `/api/` `envelope_fail("internal_error", f"{type(exc).__name__}: {exc}")`, 500.
- `middleware=[Middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])]`.
- Obálky vždy přes `aifactory.skill.envelope` — žádná vlastní struktura.

**`web/server.py`**
- `HOST: Final = "127.0.0.1"`.
- `class PortInUseError(Exception)` s atributem `port`.
- `dashboard_url(port: int) -> str` → `f"http://{HOST}:{port}/"`.
- `check_port(port: int) -> None`: `socket.socket(AF_INET, SOCK_STREAM)`, **bez** `SO_REUSEADDR`,
  `bind((HOST, port))`, zavřít; `OSError` s `errno.EADDRINUSE` (nebo `EACCES`) → `PortInUseError`.
- `serve(app: ASGIApp, port: int, *, open_browser: bool) -> None`:
  `config = uvicorn.Config(app, host=HOST, port=port, log_level="warning")`,
  `server = uvicorn.Server(config)`; když `open_browser`, spustit daemon `threading.Thread`, který
  čeká (poll ~0.05 s, timeout ~10 s) na `server.started` a pak `webbrowser.open(dashboard_url(port))`;
  `server.run()`.
- Žádný parametr host nikde — nelze předat jiný.

### 2. CLI `factory obs` (`cli.py`)

- `SUBCOMMANDS`: přidat `("obs", "serve the local dashboard on 127.0.0.1 and open it")`.
- `build_parser`: `elif name == "obs": _add_obs_command(child)`.
- `_add_obs_command(parser)`: `--repo PATH` (help jako u jiných příkazů; default git repo cwd),
  `--port N` (`type=int`, default `None`, help „port (default: port in .factory/local.yaml, 4700)“),
  `--no-open` (`store_true`, „do not open the browser“), `--json` (`store_true`,
  „print the URL as a JSON envelope before serving“).
- `_obs(args) -> int`:
  1. `root = repo_root(Path(args.repo) if args.repo else Path.cwd())`, `port = args.port or load_local(root).port`;
     `ConfigError` → `return _fail_from_exception(exc, args.json, "factory obs")`.
  2. `args.port` mimo 1..65535 → `invalid_value` (json obálka / stderr), exit 2.
  3. `from aifactory.web import server as web_server` a `from aifactory.web import create_app`
     (**lazy import** — CLI zůstane rychlé; a volat `web_server.check_port`/`web_server.serve`
     přes modul, aby je testy mohly monkeypatchnout).
  4. `check_port(port)`; `PortInUseError` → `_emit_fail("port_in_use", f"port {port} on 127.0.0.1 is already in use; pick another with --port", exit_code=2)`
     (bez `--json`: hláška na stderr, return 2).
  5. `app = create_app(root)`; json → `_emit_ok({"url": dashboard_url(port), "host": HOST, "port": port, "repo": str(root), "version": __version__})` + `sys.stdout.flush()`;
     jinak jeden řádek s URL.
  6. `web_server.serve(app, port, open_browser=not args.no_open)`; `KeyboardInterrupt` → `return 0`; return 0.
- `_dispatch`: `if command == "obs": return _obs(args)`.
- `tests/test_smoke.py`: do výčtu implementovaných v `test_subcommands_not_implemented` přidat `"obs"`
  (a nevolat `main(["obs"])`).

### 3. Kódy chyb (`skill/codes.py`)

Přidat `port_in_use` a `not_found` (viz Rozhodnutí 4) do `_CODES`, do vhodné skupiny
(nový komentář `# Dashboard.`). Skill tabulka se vygeneruje sama.

### 4. Frontend `aifactory/web/`

Kopíruj z `vendor/sssf/apps/visualizer/` (cp, pak uprav), nové soubory piš.

- `package.json`: `name: "haifa-dashboard"`, `private`, `type: module`; scripts:
  `"dev": "vite"`, `"build": "vue-tsc --noEmit && vite build"`, `"typecheck": "vue-tsc --noEmit"`,
  `"test": "vitest run"`. Dependencies stejné verze jako visualizer (`vue`, `lucide-vue-next`,
  `@fontsource/play`); devDependencies `@vitejs/plugin-vue ^6`, `vite ^7`, `vue-tsc ^3`,
  `typescript ^5.7`, `vitest ^3.2`, `@vue/test-utils ^2`, `happy-dom` (aktuální major). Bez `@types/bun`.
- `bun install` → commitnout `bun.lock`.
- `tsconfig.json`: z visualizeru, ale `"types": ["vite/client"]`, `paths` jen `@/*`,
  `include: ["src/**/*.ts", "src/**/*.vue", "vite.config.ts"]`.
- `vite.config.ts`: `defineConfig` z `vitest/config` (nebo `/// <reference types="vitest/config" />`);
  plugin vue; alias `@` → `./src`; `server: { port: 4701, proxy: { "/api": "http://127.0.0.1:4700" } }`;
  `build: { outDir: fileURLToPath(new URL("../src/aifactory/web/static", import.meta.url)), emptyOutDir: true }`;
  `test: { environment: "happy-dom", include: ["src/**/*.test.ts"] }`.
- `index.html`: z visualizeru, `lang="cs"`, `<title>HAIFA</title>`, favicon `/logo.svg`.
- `public/logo.svg`: kopie (obrázky modelů zatím nekopírovat).
- `src/main.ts`: kopie (Play 400/700, `style.css`).
- `src/style.css`: **doslovná kopie** (to je „stejný vzhled“).
- `src/lib/theme.ts`: kopie, `STORAGE_KEY = 'haifa-theme'`.
- `src/lib/router.ts` (nový):
  `export type Screen = 'backlog' | 'runs' | 'review' | 'settings'`;
  `export const SCREENS: readonly { id: Screen; label: string }[]` = Backlog, Běhy, Review, Nastavení
  (v tomto pořadí); `parseHash(hash: string): Screen` (`#/runs` → `runs`, cokoli neznámého/prázdné → `backlog`);
  `hrefFor(screen) → '#/' + screen`; reaktivní `useRoute()` nad `hashchange` (vzor z visualizeru).
- `src/lib/api.ts` (nový): typy `Envelope<T> = { ok: boolean; data: T | null; error: ApiErrorBody | null; warnings: string[] }`,
  `ApiErrorBody = { code; message; path; id; issues }`; `class ApiError extends Error { code }`;
  `async function getApi<T>(path: string): Promise<T>` — `fetch('/api' + path)`, parse JSON, `ok:false` → throw `ApiError`,
  jinak vrátí `data`. `type Health = { version: string; repo: string }`, `fetchHealth()`.
- `src/App.vue`: struktura a scoped CSS topbaru z visualizeru (logo SVG, `.brand` s textem `HAIFA`,
  `.view-toggle` jako navigace, theme toggle). Navigace: 4 odkazy ze `SCREENS` s ikonami z
  `lucide-vue-next` (např. `ListTodo`, `Activity`, `GitPullRequest`, `Settings`), třída `active`
  podle route. Vpravo místo „live“ čip s názvem repa (poslední segment `health.repo`, `title` = celá cesta)
  a verzí; při chybě health text „API nedostupné“. `<main>` renderuje view podle obrazovky.
- `src/components/EmptyScreen.vue`: props `title`, `hint`; panel v duchu visualizeru
  (`var(--surface)`, `var(--border)`), text např. „Obsah přijde v úkolu 3.x“.
- `src/views/BacklogView.vue`, `RunsView.vue`, `ReviewView.vue`, `SettingsView.vue`: každá jen
  `<EmptyScreen>` s nadpisem (Backlog / Běhy / Review / Nastavení).
- Unit testy (vitest):
  - `src/lib/router.test.ts`: `parseHash` pro všechny 4 obrazovky, prázdný a neznámý hash → `backlog`; `hrefFor`; `SCREENS` labely.
  - `src/lib/api.test.ts`: `vi.stubGlobal('fetch', ...)` — ok obálka vrací `data`; `ok:false` vyhodí `ApiError` s `code`.
  - `src/App.test.ts`: mount `App` se stubnutým `fetch` (health obálka); 4 navigační odkazy s texty
    Backlog, Běhy, Review, Nastavení a href `#/backlog`…; po `window.location.hash = '#/runs'` + `hashchange`
    je aktivní Běhy a zobrazí se nadpis „Běhy“; po flushi promises je vidět název repa.
- Po dokončení `just web-build` → vznikne `aifactory/src/aifactory/web/static/{index.html,assets/...}` (včetně fontů Play).

### 5. `.gitignore`

Přidat `aifactory/web/node_modules/` (static build **ne**ignorovat).

### 6. `justfile` (sekce aifactory)

```just
# build the dashboard frontend into the aifactory package (needs bun)
web-build:
    cd aifactory/web && bun install --frozen-lockfile && bun run build

# typecheck and unit-test the dashboard frontend (vue-tsc, vitest)
web-test:
    cd aifactory/web && bun install --frozen-lockfile && bun run typecheck && bun run test

# frontend dev server on :4701, /api proxied to a running `just dash`
web-dev:
    cd aifactory/web && bun install --frozen-lockfile && bun run dev

# run the aifactory test suite: just test  (args go to pytest; frontend checks run first)
test *ARGS: web-test
    cd aifactory && uv run pytest "$@"

# open the HAIFA dashboard: just dash [--port N] [--no-open]
dash *ARGS:
    uv run --project aifactory factory obs "$@"
```
`obs` recept (visualizer) nechat beze změny.

### 7. Testy backendu `aifactory/tests/web/`

Soubory s unikátními jmény (bez `__init__.py`, jako ostatní). Git repo pro testy: `tmp_path` +
`git init` (nebo existující helper z `tests/repo_templates.py`, pokud se hodí). Všechny typované (mypy strict).

- `test_web_app.py` (`TestClient(create_app(root, static_dir=...), base_url="http://127.0.0.1:4700")`):
  - `GET /api/health` → 200, `envelope_problems(body) == []`, `ok is True`,
    `data == {"version": aifactory.__version__, "repo": str(root)}`.
  - `GET /api/nope` → 404, `envelope_problems == []`, `error.code == "not_found"`.
  - `POST /api/health` → 405 obálka s `ok False` a validní dle `envelope_problems`.
  - `static_dir` s vlastním `index.html` → `GET /` vrací 200 a obsah; neexistující `static_dir` → `GET /` 503 s `just web-build`.
  - Host hlavička `evil.example` (`TestClient(..., base_url="http://evil.example")`) → 400.
  - Packaged build: `(STATIC_DIR / "index.html").is_file()` a `create_app(root)` (default static) vrátí na `GET /` 200 s `<div id="app">`.
- `test_web_server.py`:
  - `HOST == "127.0.0.1"`; `dashboard_url(4700) == "http://127.0.0.1:4700/"`.
  - `check_port` na obsazeném portu: otevřít socket `bind(("127.0.0.1", 0))` + `listen()`, pak `check_port(ten_port)` → `PortInUseError`; volný port (získaný a uvolněný) projde.
  - `serve`: monkeypatch `uvicorn.Server.run` (zaznamená `self.config`) a `webbrowser.open`;
    `serve(app, 4799, open_browser=False)` → `config.host == "127.0.0.1"`, `config.port == 4799`, prohlížeč nevolán.
- `test_obs_cli.py` (monkeypatch `aifactory.web.server.serve` a podle potřeby `check_port`; `capsys`):
  - `main(["obs", "--repo", str(root), "--no-open", "--json"])` → 0, obálka validní,
    `data.port == 4700`, `data.host == "127.0.0.1"`, `data.url == "http://127.0.0.1:4700/"`, `data.repo == str(root)`;
    zapatchovaný `serve` dostal `open_browser=False`.
  - `.factory/local.yaml` s `port: 4811` → port 4811; `--port 4999` přebije local.yaml.
  - bez `--no-open` → `open_browser=True`.
  - `check_port` vyhodí `PortInUseError` → exit 2, `error.code == "port_in_use"`.
  - `--port 0` / `70000` → exit 2, `invalid_value`.
  - adresář mimo git → exit 2, `invalid_config`.
- Existující `tests/test_skill.py` musí projít (ověří `--json`, skill a kódy).

### 8. Dokumentace

Nic povinného (documenter ADW). Volitelně krátká zmínka v help textech; `docs/product-brief.md` neměnit.

## Ověření

```bash
cd aifactory && uv sync            # starlette, uvicorn, httpx
just web-build                      # vytvoří src/aifactory/web/static/index.html
just test                           # web-test (vue-tsc + vitest) a pak pytest
just typecheck
just lint                           # ruff check + ruff format --check
cd aifactory && uv build --wheel -o /tmp/haifa-wheel && unzip -l /tmp/haifa-wheel/*.whl | grep 'aifactory/web/static/index.html'
just dash --no-open --port 4755 &   # pak:
curl -s http://127.0.0.1:4755/api/health    # {"ok": true, "data": {"version": "0.1.0", "repo": ...}, ...}
curl -s http://127.0.0.1:4755/ | grep 'id="app"'
lsof -iTCP:4755 -sTCP:LISTEN        # jen 127.0.0.1
kill %1
```
Hodnoť podle exit statusu příkazů. Na konci musí být ve stromu: `aifactory/web/**` (bez
`node_modules`), `aifactory/web/bun.lock`, `aifactory/src/aifactory/web/{__init__,app,server}.py`,
`aifactory/src/aifactory/web/static/**`, aktualizovaný `uv.lock`, `pyproject.toml`, `justfile`, `.gitignore`.
`vendor/` a `prototype/` beze změny (`git status vendor prototype` prázdné).
