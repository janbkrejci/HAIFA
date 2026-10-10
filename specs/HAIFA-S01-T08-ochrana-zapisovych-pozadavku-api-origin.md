# HAIFA-S01-T08: Ochrana zápisových požadavků API (Origin, Sec-Fetch-Site, JSON)

## Cíl

Každý zápisový požadavek (POST, PUT, PATCH, DELETE) pod `/api/` projde před handlerem
kontrolou původu a typu těla. Cizí web (CSRF z prohlížeče) dostane 403 `cross_origin`
nebo 415 `unsupported_media_type`. CLI, curl, TestClient a dnešní frontend fungují dál.

## Současný stav (zjištěno)

- `aifactory/src/aifactory/web/app.py`:
  - `create_app()` skládá `Starlette(..., middleware=[Middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)], exception_handlers=...)`.
  - `_json_body()` (ř. ~277) čte libovolné tělo bez ohledu na `Content-Type`.
  - Chyby API vrací `JSONResponse(envelope_fail(code, message), status_code=...)`
    (`from aifactory.skill.envelope import envelope_fail`).
  - `_is_api(request)` testuje `path == "/api" or path.startswith("/api/")`.
  - Zápisové routy: jen POST (stop, backlog tasks/edit/link/commit/run, auto-continue,
    review approve/return/resolve, settings). Stop a approve se volají bez těla.
- Frontend `aifactory/web/src/lib/api.ts` posílá POST s `Content-Type: application/json`
  jen když má tělo; bez těla bez hlavičky. Neměnit (`aifactory/web/src/` je mimo rozsah).
- `aifactory/web/vite.config.ts`: proxy `/api` → `http://127.0.0.1:${API_PORT}`,
  `changeOrigin: true` (přepíše `Host`, ale ne `Origin` → dnes by Origin
  `http://127.0.0.1:4701` neodpovídal Hostu `127.0.0.1:4700`).
- `aifactory/src/aifactory/skill/codes.py`: tabulka `_CODES`, sekce `# Dashboard.`
  (`port_in_use`, `not_found`). Skill (`render.py`) i `test_skill.py` berou kódy
  automaticky z `ERROR_CODES` — stačí přidat řádky.
- Testy: `aifactory/tests/web/test_web_app.py` používá
  `TestClient(create_app(root, static_dir=...), base_url="http://127.0.0.1:4700")`,
  `git_repo` z `web_repo.py`. Vzor spy: `monkeypatch.setattr("aifactory.run.stop.stop_run", spy)`
  v `test_web_runs.py`. Jediný test s ručním tělem posílá `Content-Type: application/json`.
- e2e (`tests/e2e`) otevírá `http://127.0.0.1:{port}` — prohlížeč pošle
  `Origin: http://127.0.0.1:{port}` a `Sec-Fetch-Site: same-origin` → projde.

## Změny

### 1. `aifactory/src/aifactory/skill/codes.py`

V sekci `# Dashboard.` za `not_found` přidat:

```python
("cross_origin", "2", "dashboard API: a write from another origin (Origin or Sec-Fetch-Site) was rejected (HTTP 403)"),
("unsupported_media_type", "2", "dashboard API: a write body that is not application/json (HTTP 415)"),
```

(Řádky zalomit podle ruff — délka řádku; použít stejný víceřádkový tvar jako `backlog_invalid`.)

### 2. `aifactory/src/aifactory/web/app.py` — čistý ASGI middleware `WriteGuardMiddleware`

Napsat jako čistou ASGI třídu (ne `BaseHTTPMiddleware`, ať se nesahá na streamování
`/api/live`). Umístit nad `create_app` (nebo do nového modulu
`aifactory/src/aifactory/web/guard.py` — preferováno kvůli délce `app.py`; pak import
v `app.py`). Typy ze `starlette.types` (`ASGIApp`, `Scope`, `Receive`, `Send`),
hlavičky přes `starlette.datastructures.Headers(scope=scope)`.

```python
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

class WriteGuardMiddleware:
    """Reject writes under /api/ from another origin or with a non-JSON body, before routing."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in WRITE_METHODS and _is_api_path(scope["path"]):
            problem = write_problem(Headers(scope=scope))
            if problem is not None:
                code, status, message = problem
                response = JSONResponse(envelope_fail(code, message), status_code=status)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
```

`_is_api_path(path)`: `path == "/api" or path.startswith("/api/")` (stejná logika jako
`_is_api`; `_is_api` může volat tuto funkci).

`write_problem(headers) -> tuple[str, int, str] | None` (čistá funkce, snadno testovatelná):

1. `host = headers.get("host", "")`.
2. `origin = headers.get("origin")`: pokud není `None` a
   `origin.lower() != f"http://{host}".lower()` → `("cross_origin", 403, f"Origin {origin!r} does not match http://{host}")`.
   (Origin `null` tím taky spadne do 403.)
3. `site = headers.get("sec-fetch-site")`: pokud není `None` a
   `site.strip().lower() != "same-origin"` → `("cross_origin", 403, f"Sec-Fetch-Site {site!r} is not same-origin")`.
4. Typ těla:
   - `ctype = headers.get("content-type")`, `media = ctype.split(";", 1)[0].strip().lower()` pokud je.
   - `has_body = headers.get("content-length", "0").strip() not in ("", "0") or "transfer-encoding" in headers`.
   - Pokud `ctype is not None and media != "application/json"` → 415.
   - Pokud `ctype is None and has_body` → 415.
   - Zpráva: `f"the request body must be application/json, got {ctype or 'no Content-Type'}"`,
     kód `unsupported_media_type`.
5. Jinak `None`.

Pořadí: nejdřív původ (403), pak typ (415). Volání `envelope_fail("cross_origin", ...)`
s literálem jako prvním argumentem (sken v `test_skill.py` hledá literály u `ERROR_CLASSES`/
`EMITTERS`; kódy jsou v registru tak jako tak).

Prázdný POST bez `Content-Type` a bez `Content-Length`/s `Content-Length: 0` projde
(Zastavit, Schválit). Požadavky bez `Origin` i `Sec-Fetch-Site` projdou. GET/HEAD/OPTIONS
se nekontrolují.

V `create_app` rozšířit middleware (pořadí: první je vnější, hostitel se kontroluje první):

```python
middleware=[
    Middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS),
    Middleware(WriteGuardMiddleware),
],
```

`ALLOWED_HOSTS` a `TrustedHostMiddleware` beze změny. `_json_body` může zůstat, jak je
(typ už hlídá middleware). Do modulového docstringu `app.py` přidat odstavec
„Write guard“: každý POST/PUT/PATCH/DELETE pod `/api/` — `Origin`, pokud přijde, musí být
`http://<Host>`, `Sec-Fetch-Site`, pokud přijde, `same-origin`, jinak 403 `cross_origin`;
tělo jiného typu než `application/json` 415 `unsupported_media_type`; požadavky bez
těchto hlaviček (CLI, curl) a POST bez těla projdou; GET se nekontroluje.

### 3. `aifactory/web/vite.config.ts`

Proxy musí posílat `Origin` cílového serveru:

```ts
const API_TARGET = `http://127.0.0.1:${API_PORT}`;
...
proxy: {
  "/api": {
    target: API_TARGET,
    changeOrigin: true,
    // The API rejects writes whose Origin is not its own host (cross_origin).
    headers: { Origin: API_TARGET },
  },
},
```

(`headers` z http-proxy přepíše odchozí hlavičky; `Sec-Fetch-Site` z prohlížeče na
:4701 je `same-origin`, takže projde.) Ověřit `bun run typecheck` (součást `just test`).

### 4. Nové testy `aifactory/tests/web/test_web_write_guard.py`

Pomocníci: `BASE = "http://127.0.0.1:4700"`, `ORIGIN = BASE`, klient
`TestClient(create_app(root, static_dir=tmp_path / "nostatic"), base_url=BASE)`, `root = git_repo(tmp_path / "repo")`.

Spy, který dokládá, že se nezavolala funkce core:
- `monkeypatch.setattr("aifactory.web.backlog.add", spy_add)` — `spy_add(repo, body)` přidá
  volání do seznamu a vrátí `({"spy": True}, [])` (handler `backlog_add` volá `backlog.add`
  přes modul, takže setattr zabírá).
- `monkeypatch.setattr("aifactory.run.stop.stop_run", spy_stop)` — `spy_stop` jen zaznamená
  volání a vyhodí `TaskRunError` s kódem `unknown_run` (zjistit konstruktor v
  `aifactory/run/errors.py`) → handler vrátí 404; pro průchozí případ stačí ověřit, že spy
  byl zavolán a status není 403/415.

Parametrizovaná matice pro `POST /api/backlog/tasks` s `json={"title": "x"}` (pokud
není řečeno jinak):

| případ | hlavičky / tělo | očekávání |
|---|---|---|
| bez hlaviček (CLI) | jen JSON | 200, spy zavolán |
| stejný původ | `Origin: http://127.0.0.1:4700` | 200, spy zavolán |
| stejný původ + `Sec-Fetch-Site: same-origin` | | 200 |
| `Content-Type: application/json; charset=utf-8` | `content=b'{"title":"x"}'` | 200 |
| cizí původ | `Origin: http://evil.example` | 403 `cross_origin`, spy nezavolán |
| localhost proti 127.0.0.1 | `Origin: http://localhost:4700` | 403 |
| jiný port | `Origin: http://127.0.0.1:4701` | 403 |
| `Origin: null` | | 403 |
| `Sec-Fetch-Site: cross-site` (bez Origin) | | 403 |
| `Sec-Fetch-Site: same-site` | | 403 |
| stejný Origin + `Sec-Fetch-Site: cross-site` | | 403 |
| formulářové tělo | `data={"title": "x"}` (→ `application/x-www-form-urlencoded`) | 415 `unsupported_media_type` |
| `text/plain` | `content=b'{"title":"x"}', headers={"Content-Type": "text/plain"}` | 415 |
| `multipart/form-data` | `files=...` | 415 |
| tělo bez Content-Type | `content=b'{"title":"x"}'` bez hlavičky (ověřit, že httpx nepřidá Content-Type; jinak vynechat) | 415 |

U každého odmítnutí: `envelope_problems(body) == []`, `body["ok"] is False`,
`body["error"]["code"]` dle tabulky, seznam volání spy je prázdný.

Další testy:
- Prázdný `POST /api/runs/r1/stop` bez hlaviček → spy `stop_run` zavolán (status ≠ 403/415).
- Prázdný POST se `Sec-Fetch-Site: same-origin` a stejným Origin → projde (simulace
  tlačítek Zastavit/Schválit z prohlížeče).
- Prázdný POST s cizím Origin → 403, spy nezavolán.
- Ostatní metody: `client.request("DELETE"|"PUT"|"PATCH", "/api/backlog/tasks", headers={"Origin": "http://evil.example"})` → 403 `cross_origin` (kontrola běží před routováním).
- GET s cizím Origin a `Sec-Fetch-Site: cross-site` → `GET /api/health` 200 (GET se nekontroluje).
- POST mimo `/api/` (např. `/` bez buildu) s cizím Origin → není 403 `cross_origin` JSON
  (guard se týká jen `/api/`).
- Kontrola hostitele zůstává: `TestClient(app, base_url="http://evil.example").post("/api/runs/x/stop", headers={"Origin": "http://evil.example"})` → 400.
- Jednotkové testy `write_problem(Headers(...))` jsou volitelné.
- `ERROR_CODES` obsahuje `cross_origin` a `unsupported_media_type` (krátký assert).

Stávající testy API se nemění a musí projít.

### 5. Dokumentace (volitelně v této fázi)

`app_docs/HAIFA-S01-T08-ochrana-zapisovych-pozadavku-api-origin.md` — krátký popis
pravidel guardu, kódů a změny proxy (pokud workflow nemá samostatnou fázi dokumentace).

## Ověření

Z kořene worktree:

```
just lint        # ruff check + ruff format --check
just typecheck   # mypy (strict) — typy ASGI z starlette.types
just test        # web-test (vue-tsc, vitest) + pytest
just e2e         # Playwright přes factory obs — zápisy z prohlížeče musí projít
```

Při selhání `ruff format --check` spustit `cd aifactory && uv run ruff format <soubory>`.

## Omezení

- Server dál jen na `127.0.0.1` (`server.py` neměnit).
- Neměnit `vendor/`, `prototype/`, `aifactory/web/src/`. Žádné CORS hlavičky, žádný token.
- Testy bez modelu a sítě.
- Měnit jen: `aifactory/` (konkrétně `src/aifactory/web/app.py`, případně nový
  `src/aifactory/web/guard.py`, `src/aifactory/skill/codes.py`, `web/vite.config.ts`,
  `tests/web/test_web_write_guard.py`), `app_docs/...`, spec.
