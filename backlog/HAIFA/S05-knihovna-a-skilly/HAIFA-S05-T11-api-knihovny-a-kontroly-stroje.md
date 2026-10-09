---
id: HAIFA-S05-T11
title: API knihovny a kontroly stroje
status: done
workflow: plan-build-test
depends_on: [HAIFA-S01-T13, HAIFA-S07-T02, HAIFA-S05-T06, HAIFA-S05-T09, HAIFA-S05-T10]
---

## Zadání
Zpřístupni knihovnu a kontrolu stroje přes globální API dashboardu. Endpointy volají tytéž funkce core jako `factory library …` a `factory check` mimo repo a vrací stejné obálky.

Where: `aifactory/src/aifactory/web/app.py`, aplikace pro více repozitářů a registr z M3, `aifactory/src/aifactory/library/` (z L2, L3, L9 a L10), kontrola z M6 a P2, `aifactory/src/aifactory/skill/codes.py`, testy v `aifactory/tests/web/`.

Done means:
- `GET /api/machine/check?offline=&fresh=` vrátí zprávu `factory check` mimo repo (stroj a knihovna), drží ji 60 s a `fresh=1` ji obnoví.
- `GET /api/library` vrátí stav knihovny (`factory library status` bez fetch) a položky s verzí, datem, autorem a počtem registrovaných rep, která je používají. Bez knihovny vrátí `{exists: false}`.
- `GET /api/library/items/{type}/{name}?version=` vrátí soubory, historii a použití v registrovaných repech se stavem.
- `POST /api/library/plan {action, options}` s `action` `init`, `clone`, `import` nebo `seed` jen čte a vrátí plán s digestem. `POST /api/library/apply {action, digest, options}` plán přepočítá, jiný digest vrátí 409 `plan_changed`, blokátor 409 se svým kódem a odmítnutý push 502 `push_failed`. `POST /api/library/pull` a `POST /api/library/push` dělají totéž co CLI.
- Import bere cestu jen pod domovem (403 `outside_home`). Zápisy projdou kontrolou z M1 a najednou běží nejvýš jeden zápis knihovny (409 `busy`).
- Testy (pytest) přes TestClient s dočasným `HAIFA_HOME` a holým remote: kontrola s falešnými binárkami, prázdný domov, init a clone přes plán, import, `plan_changed`, `busy`, pull a push, použití ve dvou repech.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: frontend, položky repa a akce záložky Factory (L12), nová logika core.

Pevná omezení:
- Provedení nevezme z požadavku obsah souborů, jen volby plánu a digest.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-08 · workflow plan-build-test · PR https://github.com/janbkrejci/HAIFA/pull/88 · náklady $0.00
