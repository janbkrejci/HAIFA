# HAIFA-S01-T08: Ochrana zápisových požadavků API (Origin, Sec-Fetch-Site, JSON)

## Proč

Dashboard poslouchá na `127.0.0.1`, ale prohlížeč na něj umí poslat požadavek z libovolného webu.
Dřív `TrustedHostMiddleware` kontroloval jen jméno hostitele bez portu a `_json_body` přijal jakékoli tělo.
Cizí stránka tak mohla poslat zápis, například formulářem nebo `fetch` s `text/plain`.
Až bude dashboard přidávat repozitáře a instalovat do nich factory, šlo by tudy zapisovat a pushovat.

## Co se změnilo

**`aifactory/src/aifactory/web/guard.py`** (nový soubor) obsahuje čistě ASGI middleware `WriteGuardMiddleware`.
Kontroluje každý `POST`, `PUT`, `PATCH` a `DELETE` na cestě `/api` nebo `/api/...` ještě před routováním, takže se handler nespustí.
Pravidla jsou ve funkci `write_problem(headers)` a uplatní se v tomto pořadí:

1. `Origin`, pokud přijde, se musí rovnat `http://<Host>` požadavku (velikost písmen se ignoruje). Jinak 403 `cross_origin`.
   Odmítne se tedy `localhost` proti `127.0.0.1`, jiný port i `Origin: null`.
2. `Sec-Fetch-Site`, pokud přijde, musí být `same-origin`. Jinak 403 `cross_origin` (to platí i pro `same-site`).
3. `Content-Type` musí být `application/json`. Parametry jako `; charset=utf-8` jsou povolené.
   Jiný typ (formulář, multipart, `text/plain`) vrátí 415 `unsupported_media_type`.
   Totéž dostane tělo bez `Content-Type`. Tělo se pozná podle nenulového `Content-Length` nebo přítomného `Transfer-Encoding`.

Odpověď při odmítnutí je běžná obálka `envelope_fail(code, message)`.

Beze změny projdou:
- `POST` bez těla a bez `Content-Type` (dnešní Zastavit a Schválit),
- požadavky bez `Origin` i `Sec-Fetch-Site` (CLI, curl, TestClient),
- každý `GET` a zápisy mimo `/api/`.

**`aifactory/src/aifactory/web/app.py`**: `create_app` přidává `WriteGuardMiddleware` za `TrustedHostMiddleware`.
Kontrola hostitele tak dál běží jako první a cizí `Host` dostane 400.
`_is_api` teď volá sdílené `is_api_path` z `guard.py`. Docstring modulu popisuje novou kontrolu.

**`aifactory/src/aifactory/skill/codes.py`**: do sekce Dashboard přibyly kódy `cross_origin` (HTTP 403) a `unsupported_media_type` (HTTP 415).

**`aifactory/web/vite.config.ts`**: proxy `/api` pro `just web-dev` posílá hlavičku `Origin: http://127.0.0.1:<PORT>`, tedy původ cílového API (`API_TARGET`).
Díky tomu zápisy z vývojového serveru na portu 4701 projdou.

## Ověření

```sh
just test        # mimo jiné aifactory/tests/web/test_web_write_guard.py
just typecheck && just lint && just e2e
```

`aifactory/tests/web/test_web_write_guard.py` pokrývá:
- matici hlaviček a těl pro `POST /api/backlog/tasks`:
  - projdou: bez hlaviček, stejný původ, stejný původ se `same-origin`, JSON s `charset`,
  - odmítnou se: cizí původ, `localhost` proti `127.0.0.1`, jiný port, `null`, `cross-site`, `same-site`, formulář, `text/plain`, multipart a tělo bez `Content-Type`,
- prázdné `POST /api/runs/r1/stop` bez hlaviček, z dashboardu a z cizího původu,
- `PUT`, `PATCH` a `DELETE`,
- `GET` s cizími hlavičkami a zápis mimo `/api/`,
- zachovanou kontrolu hostitele (400),
- registraci obou kódů.

Testy nahrazují `aifactory.web.backlog.add` a `aifactory.run.stop.stop_run` spy funkcemi.
Ty ověřují, že se při odmítnutí nezavolá žádná funkce core.

Ruční kontrola s běžícím `just dash`:

```sh
curl -i -X POST -H 'Origin: http://evil.example' http://127.0.0.1:4700/api/runs/x/stop   # 403 cross_origin
curl -i -X POST -H 'Content-Type: text/plain' -d '{}' http://127.0.0.1:4700/api/backlog/tasks  # 415
```
