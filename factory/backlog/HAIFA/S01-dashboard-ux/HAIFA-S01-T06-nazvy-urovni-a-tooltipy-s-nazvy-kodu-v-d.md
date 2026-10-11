---
id: HAIFA-S01-T06
title: Názvy úrovní a tooltipy s názvy kódů v dashboardu
status: done
depends_on: [HAIFA-S03-T02, HAIFA-S02-T03]
---

## Zadání
Ukaž v dashboardu úrovně backlogu česky podle `levels` a všude, kde se ukazuje kód projektu, stepu nebo tasku, ukaž jeho název tooltipem (rozhodnutí v `docs/decisions.md`: project → step → task).

Where: `aifactory/src/aifactory/web/` (`app.py`, `backlog.py`, `review.py`, `runs.py`), `aifactory/web/src/` (`lib/backlog.ts`, `lib/review.ts`, `lib/runs.ts`, `components/backlog/`, `components/review/`, `components/runs/`, `views/` a testy), `aifactory/tests/web/`, build v `aifactory/src/aifactory/web/static/`.

Done means:
- UI pojmenuje úrovně podle `levels`: project jako Projekt, module jako Modul, step jako Step, task jako Task a jiné jméno beze změny. Platí pro strom, hlavičku grafu, formulář tasku, legendu grafu, popisky polí, placeholdery a hlášky. Sloupec Modul na obrazovce Review se jmenuje podle úrovně.
- API dashboardu vrací `project_id` místo `module_id` (Review) a `project` místo `module` u stepů. `GET /api/backlog/names` vrací pro každý kód projektu, stepu a tasku jeho název a úroveň.
- Každý kód projektu, stepu nebo tasku v UI má tooltip s názvem a úrovní, včetně tooltipu Blokováno, vazeb, nesplněných závislostí před spuštěním, uzlů grafu, seznamu PR a hlavičky běhu. Filtr tasku v Bězích ukazuje `kód: název`.
- Změna názvu v backlogu se v tooltipech projeví bez obnovení stránky.
- Testy API (pytest) pro endpoint názvů a přejmenované klíče. Unit testy (vitest) mapy úrovní a tooltipu s názvem. Atributy `data-test` zůstávají.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: zakládání a přejmenování projektů a stepů, drobečková navigace, skládání stromu.

Pevná omezení:
- API běhů (`phases`, `phase_id`) a slovo Fáze pro fáze běhu se nemění.
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/32 · náklady $4.68
