---
id: HAIFA-REFINEMENT-T39
title: Task čekající na review neuvolňuje slot pro paralelní běhy
status: done
archived: true
workflow: build-test-review
depends_on: []
related: [HAIFA-S03-T16, HAIFA-REFINEMENT-T34, HAIFA-REFINEMENT-T30, HAIFA-S03-T14]
writes: [aifactory/src/aifactory/run/, aifactory/src/aifactory/web/chains.py, aifactory/src/aifactory/web/overview.py, aifactory/src/aifactory/web/control.py, aifactory/src/aifactory/guide/, aifactory/src/aifactory/skill/, aifactory/tests/]
---

## Zadání
## Problém

Počet volných slotů pro paralelní běhy (`max_parallel_runs` v `.factory/config.yaml`) dnes počítá jen živé běhy (`TaskRunStore.live_runs()`). Jakmile běh skončí a jeho PR čeká na review/merge, slot se považuje za volný a továrna nebo řetěz hned spustí další task. Stav „čeká na review“ ale nemá znamenat uvolněný slot.

Dotčená místa (současný stav):
- `run/queue.py`, `start_factory`: `free_slots = max(0, limit - len(live_runs()))`.
- `run/queue.py`, plnění slotů paralelního řetězu ("refills a slot whenever a run ends").
- `web/chains.py`: `free_slots = max_parallel - running`, kde `running` jsou jen běhy ve stavu RUNNING.
- `web/overview.py`, `web/control.py`: zobrazení obsazenosti a volných slotů, pokud se v nich počítají.

## Požadované chování

- Do obsazených slotů se počítají živé běhy a také tasky, jejichž PR je otevřený a nesloučený (`store.open_prs()`, stav `in_review`). Každý task se počítá jen jednou, i když má zároveň živý běh (např. resolve nebo retry) a otevřený PR.
- Slot se uvolní, až když se PR sloučí nebo zavře, nebo když task skončí bez PR (selhal, je zablokovaný nebo zrušený).
- Platí to pro „Spustit továrnu“ (`start_factory`), pro plnění slotů paralelního řetězu i pro hodnoty `running`/`free_slots`, které vrací API (`/api/chains`, přehled).
- Stávající pravidla pro kolize `writes` s otevřenými PR (`Occupancy`, `writes_overlap`) a pro `exclusive` zůstávají beze změny.
- Když nejsou volné sloty, protože tasky čekají na review, má být z výsledku nebo skipu poznat, že důvodem jsou PR čekající na review (ne jen živé běhy).

## Akceptační kritéria

- Test: s `max_parallel_runs: 2`, jedním živým během a jedním otevřeným PR jiného tasku spustí `start_factory` 0 tasků a `free_slots == 0`.
- Test: po sloučení nebo zavření PR se slot uvolní a další ready task se spustí.
- Test: task se živým během i otevřeným PR obsadí jen jeden slot.
- Test: paralelní řetěz neplní slot tasku, jehož PR čeká na review.
- API `/api/chains` a přehled vracejí `free_slots` po započtení PR čekajících na review. Existující testy v `tests/run/test_factory_start.py`, `tests/run/test_parallel_chain.py`, `tests/web/test_web_chains.py` a `tests/web/test_web_overview.py` jsou upravené nebo rozšířené.
- Docstring modulu `run/queue.py` a příslušné pasáže v `guide/06-behy.md` a `skill/skill.md` popisují nové počítání slotů.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-15 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/52 · náklady $2.91
