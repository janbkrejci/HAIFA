---
id: HAIFA-REFINEMENT-T103
title: Závažnost follow-upu a workflow podle závažnosti
status: todo
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T101, HAIFA-REFINEMENT-T102]
writes: [aifactory/src/aifactory/seed/agents/builder/system.md, aifactory/src/aifactory/seed/agents/planner/system.md, aifactory/src/aifactory/seed/agents/tester/system.md, aifactory/src/aifactory/seed/agents/reviewer/system.md, aifactory/src/aifactory/seed/agents/documenter/system.md, aifactory/src/aifactory/engine/data_types.py, aifactory/src/aifactory/config/settings.py, aifactory/src/aifactory/run/followups.py, aifactory/src/aifactory/run/triage.py, aifactory/tests/run/test_followups.py, aifactory/tests/run/test_followups_triage.py, aifactory/tests/config/, aifactory/src/aifactory/config/loader.py]
---

## Zadání
Follow-up dnes nemá závažnost. Kosmetický rozdíl (jedna zastávka Tabu) i vada, která blokuje uživatele, se zakládají stejně a dostanou workflow projektu. Agent nastaví `workflow: "build-review"` jen u follow-upu, který mění pouze dokumentaci. V NEO_HEF stojí běh přes build-review přibližně $1,4, plný haifa-implement-task přibližně $9,3.

Co udělat:
- `FollowUp` (aifactory/src/aifactory/engine/data_types.py) dostane volitelné pole `severity`: `blocker | defect | minor | cosmetic`. Krátké definice patří do sekce „Unfinished work“ promptů `builder`, `planner`, `tester`, `reviewer` a `documenter` (seed/agents/<agent>/system.md).
- Nastavení projektu (`ProjectSettings`, aifactory/src/aifactory/config/settings.py) `follow_up_workflows`: mapa závažnost → workflow, například `{minor: build-review, cosmetic: build-review}`. Výchozí hodnota je prázdná a chování se nemění. Pořadí: `workflow`, které výslovně uvedl agent, pak mapa podle závažnosti, pak zděděné workflow.
- Závažnost se zapíše do těla založeného tasku (oddíl „Původ“ v run/followups.py) a triáž ji dostane v kontextu (run/triage.py).
- Při sloučení follow-upů (shoda titulku, nebo pokrytí z HAIFA-REFINEMENT-T102) platí nejvyšší závažnost.

Mimo rozsah: práh, pod kterým se follow-up nezaloží, a jakákoli změna auto-continue nebo fronty.

Hotovo znamená:
- Test v aifactory/tests/run/test_followups.py: follow-up `minor` bez `workflow` v projektu s mapou dostane `build-review`. Follow-up `minor` s výslovným `workflow` si ho ponechá. Projekt bez mapy dědí jako dnes.
- Test načtení nastavení `follow_up_workflows` včetně odmítnutí neznámé závažnosti a neexistujícího workflow.
- Stávající testy follow-upů, triáže a konfigurace procházejí.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
