---
id: HAIFA-REFINEMENT-T56
title: "Auto continue: po dokončení blokátoru pokračovat odblokovaným taskem z jiného projektu"
status: done
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/run/queue.py, aifactory/tests/run/test_auto_continue.py, docs/decisions.md]
---

## Zadání
Řetěz auto-continue (`select_next` → `candidates` v `aifactory/src/aifactory/run/queue.py`) bere další task jen z projektu právě dokončeného tasku (rozhodnutí HAIFA-REFINEMENT-T34). Když task v projektu B závisí na tasku v projektu A, po dokončení blokátoru v A řetěz task v B nikdy nespustí. Člověk ho pak musí pustit ručně.

Co udělat:
- V `candidates` (případně v `select_next`) přidat do kandidátů i `todo` tasky jiných projektů, které přímo závisí (`depends_on`) na právě dokončeném tasku `after`. Pořadí: až za tasky vlastního projektu z ručního pořadí (kanban queue) a ze stejného stepu, ale před zbytkem vlastního projektu, aby odblokovaný task přišel na řadu brzy. Kandidát pak projde stejnými kontrolami jako ostatní (`_select`): nesplněné závislosti, `waits_on_pr`, `excluded`, `no_workflow`, `human_task`, kolize writes, `require_auto_continue`.
- Ostatní tasky cizích projektů (ty, které na `after` nezávisí) dál zůstávají mimo řetěz. Stávající test `test_chain_never_starts_a_queued_task_of_another_project` musí dál platit.
- Aktualizovat docstring modulu a funkcí v `queue.py` (odstavec „The next task is always one of the same project…“).
- Do `docs/decisions.md` doplnit krátké rozhodnutí: řetěz zůstává v projektu, výjimkou jsou tasky jiného projektu, které přímo závisejí na právě dokončeném tasku.
- Testy v `aifactory/tests/run/test_auto_continue.py`:
  - dokončení A-T01 spustí odblokovaný B-T01 (s `auto_continue`),
  - B-T01 s další nesplněnou závislostí se nespustí,
  - B-T01 bez `auto_continue` se při řetězu bez `--auto` nespustí,
  - nezávislý queued task projektu B se dál nespustí.

Mimo rozsah: tranzitivní závislosti (jen přímí závislí na `after`), změny UI.

Hotovo znamená:
- Nové testy v `aifactory/tests/run/test_auto_continue.py` procházejí, stávající testy auto-continue zůstávají zelené.
- Docstringy `queue.py` a `docs/decisions.md` popisují novou výjimku.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-20 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/123 · náklady $0.00
