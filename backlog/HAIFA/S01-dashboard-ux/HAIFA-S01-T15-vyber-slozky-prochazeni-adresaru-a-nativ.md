---
id: HAIFA-S01-T15
title: "Výběr složky: procházení adresářů a nativní dialog"
status: done
depends_on: [HAIFA-S01-T13]
---

## Zadání
Přidej endpointy pro výběr složky při přidání repa: procházení adresářů pod domovem uživatele a nativní dialog systému, který otevře server. Webová stránka sama absolutní cestu ke složce nezíská.

Where: `aifactory/src/aifactory/web/app.py`, aplikace pro více repozitářů z M3, `aifactory/src/aifactory/skill/codes.py`, testy v `aifactory/tests/web/`. Nový modul v `aifactory/src/aifactory/web/`.

Done means:
- `GET /api/fs/dirs?path=` vrátí `{path, parent, entries: [{name, path, is_git, has_factory}], truncated}`: jen adresáře, bez skrytých, nejvýš 500 položek, bez `path` domov uživatele. `is_git` a `has_factory` se zjistí jen ze `stat`. Cesta mimo domov po rozbalení symlinků vrátí 403 `outside_home`.
- `GET /api/fs/pick` vrátí `{available}`. `POST /api/fs/pick` otevře dialog výběru složky (macOS `osascript`, Linux `zenity` nebo `kdialog`) s pevnými argumenty bez dat z požadavku, na pracovním vlákně s limitem 300 s a nejvýš jeden najednou (`picker_busy`). Vrátí `{path}` nebo `{cancelled: true}`. Bez grafického sezení (SSH, chybí `DISPLAY`) je `available: false` a POST vrátí `picker_unavailable`.
- GET nic neotevře ani nezapíše. POST projde kontrolou z M1.
- Nové kódy jsou v `skill/codes.py`.
- Testy (pytest) s falešnými `osascript` a `zenity` na PATH: výběr, zrušení, souběžný dialog, limit a nedostupnost. Limity a skryté položky v `fs/dirs`, cesta mimo domov a symlink ven z domova.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: frontend, Windows, cokoli, co do vybrané složky zapisuje.

Pevná omezení:
- Server dál poslouchá jen na `127.0.0.1`.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/61 · náklady $1.15
