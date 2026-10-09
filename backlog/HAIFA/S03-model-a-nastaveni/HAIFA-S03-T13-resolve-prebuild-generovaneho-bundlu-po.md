---
id: HAIFA-S03-T13
title: "Resolve: přebuild generovaného bundlu po vyřešení konfliktu"
status: done
depends_on: []
---

## Zadání
Resolve smí měnit jen soubory s konfliktem. Když konflikt zasáhne generovaný bundle frontendu (`aifactory/src/aifactory/web/static/`), znamená to, že frontend změnily obě strany a správný výsledek vyžaduje přebuild. Ten vytvoří nové soubory `static/assets/index-*.js|css` a smaže staré, hlídač je jako zásah mimo rozsah vrátí a běh selže. Stalo se 2026-10-03 u HAIFA-S03-T11 (run b80cf773): konflikt v `run/queue.py` a `static/index.html`, opravný agent přebuildil bundle a hlídač ho vrátil.

Where: `aifactory/src/aifactory/run/resolve.py`, `aifactory/src/aifactory/run/scope.py`, `aifactory/src/aifactory/defaults/workflows/resolve.yaml`, konfigurace v `aifactory/src/aifactory/config/`, testy v `aifactory/tests/`.

Done means:
- Konfigurace umí pojmenovat generované výstupy a příkaz, který je postaví (pro HAIFA `aifactory/src/aifactory/web/static/` a `just web-build`).
- Když konflikt zasáhne generovaný výstup, agent ho neřeší: po vyřešení ostatních konfliktů ho kód přestaví tím příkazem a výsledek je součástí výstupu resolve. Hlídač tyto soubory v resolve povolí jen tomuto kroku.
- Agent resolve generované soubory dál měnit nesmí.
- Test: rebase s konfliktem v bundlu a falešným build příkazem skončí přestavěným bundlem bez porušení hlídače. Konflikt jen ve zdrojích funguje jako dnes.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: přebuild generovaných výstupů v jiných workflow než resolve.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/28 · náklady $2.44
