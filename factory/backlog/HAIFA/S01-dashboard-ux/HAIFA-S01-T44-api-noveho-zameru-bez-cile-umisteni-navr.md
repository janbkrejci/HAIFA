---
id: HAIFA-S01-T44
title: "API Nového záměru bez cíle: umístění navrhne agent"
status: done
archived: true
workflow: build-test-review
depends_on: [HAIFA-S01-T43]
writes: [aifactory/src/aifactory/web/intent.py, aifactory/src/aifactory/web/app.py, aifactory/tests/web/test_web_intent.py]
---

## Zadání
## Zadání

`POST /api/backlog/intent` nově přijme samotné `{intent}` a umístění nechá na agentovi (automatický režim z HAIFA-S01-T43).

1. `aifactory/src/aifactory/web/intent.py`:
   - `_target` povolí tělo bez `project` i `step`, výsledek je `Target()`. Oba najednou zůstávají chybou `UsageError`. Explicitní `project` nebo `step` funguje dál.
   - `IntentJob.json()` vrací v `target` vyřešené umístění posledního návrhu (`{project, step, new_project, new_step}`), dokud návrh není hotový, `{project: null, step: null}`. Zadaný cíl jde do pole `requested`.
   - `refine` a `apply` pracují s původním `Target` jobu. Upravený návrh (`edited`) si nechá umístění, které agent navrhl. `apply` zapíše i nový projekt a commitne backlog jako dnes.
2. Docstring Nového záměru v `aifactory/src/aifactory/web/app.py` popíše tělo `{intent}` bez cíle.

Mimo rozsah: frontend.

Hotovo znamená:
- `aifactory/tests/web/test_web_intent.py` s fake runnerem pokrývá:
  - start bez cíle,
  - stav jobu s vyřešeným umístěním,
  - upřesnění, které umístění změní,
  - `apply` návrhu s novým projektem včetně commitu backlogu,
  - že `project` + `step` najednou je 400.
- `just lint`, `just typecheck` a `just pytest tests/web/test_web_intent.py` projdou.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-17 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/103 · náklady $1.08
