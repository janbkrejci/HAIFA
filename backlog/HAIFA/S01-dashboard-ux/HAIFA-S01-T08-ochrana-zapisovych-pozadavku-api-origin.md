---
id: HAIFA-S01-T08
title: "Ochrana zápisových požadavků API (Origin, Sec-Fetch-Site, JSON)"
status: done
depends_on: []
---

## Zadání
Zabezpeč zápisové požadavky API dashboardu proti požadavkům z cizích webů. Dnes `_json_body` ve `web/app.py` přijme jakékoli tělo a `TrustedHostMiddleware` kontroluje jen jméno hostitele bez portu. Až dashboard bude přidávat repozitáře a instalovat do nich factory, mohl by cizí web zapisovat a pushovat do libovolné složky.

Where: `aifactory/src/aifactory/web/app.py`, `aifactory/web/vite.config.ts`, `aifactory/src/aifactory/skill/codes.py`, testy v `aifactory/tests/web/`.

Done means:
- Každý POST, PUT, PATCH a DELETE pod `/api/` projde kontrolou dřív, než se zavolá handler. `Origin`, pokud přijde, se musí rovnat `http://<Host>` požadavku a `Sec-Fetch-Site`, pokud přijde, musí být `same-origin`, jinak 403 `cross_origin`. Tělo s jiným `Content-Type` než `application/json` vrátí 415 `unsupported_media_type`.
- POST bez těla a bez `Content-Type` (dnešní Zastavit a Schválit) a požadavky bez `Origin` i `Sec-Fetch-Site` (CLI, curl, TestClient) projdou jako dnes. GET se nekontroluje. Kontrola hostitele zůstává.
- Proxy `just web-dev` posílá na API `Origin` cílového serveru, takže zápisy z vývojového serveru projdou.
- Oba kódy jsou v `skill/codes.py`.
- Testy (pytest): matice hlaviček pro POST (stejný původ, cizí původ, `localhost` proti `127.0.0.1`, `Sec-Fetch-Site` `cross-site` a `same-site`, formulářové a `text/plain` tělo, prázdné tělo bez hlaviček). Při odmítnutí se nezavolá žádná funkce core. Stávající testy API projdou beze změny.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: token pro jednotlivé spuštění dashboardu, CORS hlavičky, změny v `aifactory/web/src/`.

Pevná omezení:
- Server dál poslouchá jen na `127.0.0.1`.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-02 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/5 · náklady $1.60
