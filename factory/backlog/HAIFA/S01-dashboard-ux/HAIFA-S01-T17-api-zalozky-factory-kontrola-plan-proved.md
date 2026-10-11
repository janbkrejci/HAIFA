---
id: HAIFA-S01-T17
title: "API záložky Factory: kontrola, plán, provedení a dorovnání base"
status: done
workflow: plan-build-test
depends_on: [HAIFA-S01-T13, HAIFA-S01-T14]
---

## Zadání
Zpřístupni kontrolu, instalaci, aktualizaci, commit konfigurace a dorovnání base přes API repa. Endpointy volají tytéž funkce core jako `factory check`, `factory init`, `factory update` a `factory config commit|pull` a vrací stejné obálky.

Where: `aifactory/src/aifactory/web/app.py`, registr a aplikace pro více repozitářů z M3, kontrola, init, aktualizace a zveřejnění commitu z M6 až M9 a HAIFA-S04-T01 v `aifactory/src/aifactory/`, `aifactory/src/aifactory/skill/codes.py`, testy v `aifactory/tests/web/`.

Done means:
- `GET /api/repos/{id}/factory/check?offline=&fresh=` vrátí zprávu `factory check` doplněnou o nález `trace_db_shared` z registru. Výsledek drží 60 s, `fresh=1` ho obnoví.
- `POST /api/repos/{id}/factory/plan {action, options}` s `action` `init`, `update` nebo `config_commit` jen čte a vrátí plán s `digest`. U `init` vrátí i `detected` a `available` a přijme volby `agents`, `bind` (harness, model a thinking po agentech), `workflows`, `base`, `provider`, `azure`, `backlog_dir`, `specs_dir` a `docs_dir`. U `update` přijme `take`, `merge` a `migrate`.
- `POST /api/repos/{id}/factory/apply {action, digest, options, target, message}` plán přepočítá. Jiný digest vrátí 409 `plan_changed` s novým plánem, blokátor 409 se svým kódem a odmítnutý push 502 `push_failed`. Úspěch vrátí `{commit, pushed, pr, warnings}`.
- `POST /api/repos/{id}/config/pull` dorovná lokální base jako `factory config pull`.
- V jednom repu běží nejvýš jedno provedení nebo dorovnání najednou, druhé dostane 409 `busy`.
- Tytéž trasy fungují i v `create_app(repo)` pod `/api/`.
- Testy (pytest) přes TestClient nad dvěma repy s holým remote: instalace s builderem na jiném harnessu, odmítnutý push a PR se stejným digestem, `plan_changed`, `busy`, `run_in_progress`, aktualizace s `take` a `migrate`, commit konfigurace, dorovnání a izolace rep.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: frontend, nová logika core, správa položek a onboarding (L12).

Pevná omezení:
- Provedení nevezme z požadavku cesty ani obsah souborů, jen volby plánu, cíl, zprávu a digest.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-07 · workflow plan-build-test · PR https://github.com/janbkrejci/HAIFA/pull/77 · náklady $3.69
