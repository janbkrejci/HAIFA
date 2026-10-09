---
id: HAIFA-S03-T17
title: "Souběžný řetěz: auto-resolve konfliktního PR"
status: done
depends_on: []
---

## Zadání
Sekvenční řetěz (`max_parallel_runs: 1`) při auto-merge konfliktní PR jednou vyřeší (`review.automerge.resolve_and_merge`, workflow `resolve-reviewed`) a pak ho sloučí. Člen souběžného řetězu (`factory task run --member`, `cli.py`) volá jen `try_auto_merge`, takže konfliktní PR zůstane otevřený a řetěz se zastaví (`not_merged`). Doplň do členského běhu stejný jeden pokus o auto-resolve.

Where: `aifactory/src/aifactory/cli.py` (členský běh), `aifactory/src/aifactory/run/members.py` (výsledek člena pro řetěz), `aifactory/src/aifactory/run/queue.py`, testy.

Done means:
- Člen souběžného řetězu s `auto_merge` při konfliktu PR jednou spustí `resolve_and_merge` a po úspěšném resolve PR sloučí, stejně jako sekvenční řetěz.
- Resolve běh patří do řetězu: je v jeho `run_ids` a dashboard ho u řetězu ukáže s výsledkem.
- Když resolve selže nebo review řešení zamítne, PR zůstane otevřený s důvodem v `auto_merge_error` a řetěz se zastaví `not_merged`.
- Sloučení po resolve jde pod merge zámkem store jako dnes, resolve sám zámek nedrží.
- Testy: konflikt v souběžném řetězu se vyřeší a sloučí, zamítnuté řešení nechá PR otevřený a zastaví řetěz.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: víc než jeden pokus o resolve, změny workflow `resolve-reviewed`.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/54 · náklady $1.81
