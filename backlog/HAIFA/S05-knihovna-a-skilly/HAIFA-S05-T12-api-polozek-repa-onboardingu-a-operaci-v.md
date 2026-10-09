---
id: HAIFA-S05-T12
title: "API položek repa, onboardingu a operací ve více repech"
status: done
workflow: plan-build-test
depends_on: [HAIFA-S01-T17, HAIFA-S05-T08, HAIFA-S05-T09, HAIFA-S06-T02, HAIFA-S06-T03, HAIFA-S06-T04]
---

## Zadání
Rozšiř API repa o stavy položek a o akce plánu pro správu položek, onboarding a převzetí a přidej plán přidání nebo aktualizace položky knihovny ve více repech. Endpointy volají tytéž funkce core jako CLI.

Where: `aifactory/src/aifactory/web/app.py`, API záložky Factory z M10, `aifactory/src/aifactory/library/` (z L4, L7, L8 a L9), `aifactory/src/aifactory/onboard/` (z O1, O2 a O4), `aifactory/src/aifactory/skill/codes.py`, testy v `aifactory/tests/web/`.

Done means:
- `GET /api/repos/{id}/factory/items` vrátí stavy jako `factory config items`.
- `POST …/factory/plan` a `…/factory/apply` přijmou akce `add`, `set`, `remove`, `export`, `revert`, `onboard` a `adopt` s volbami jako CLI. Obálky, 409 `plan_changed`, blokátory, 502 `push_failed` a 409 `busy` jsou jako v M10. Plán `onboard` nese část knihovny, část repa a zprávu po kódech.
- `POST /api/library/repos-plan {action, type, name, repos, options}` s `action` `add` nebo `update` vrátí plán pro každé zvolené repo (L9). Provádí se po repech přes `…/factory/apply`.
- Tytéž trasy fungují v `create_app(repo)` pod `/api/`.
- Testy (pytest) přes TestClient nad dvěma repy, dočasnou knihovnou a holými remote: add a set, export a add do druhého repa, update s `take`, onboard fixtury sssf, `onboarded_in_remote`, adopt, plán pro více rep se zablokovaným repem.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: frontend, nová logika core.

Pevná omezení:
- Provedení nevezme z požadavku cesty ani obsah souborů, jen volby plánu, cíl, zprávu a digest.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-08 · workflow plan-build-test · PR https://github.com/janbkrejci/HAIFA/pull/89 · náklady $0.00
