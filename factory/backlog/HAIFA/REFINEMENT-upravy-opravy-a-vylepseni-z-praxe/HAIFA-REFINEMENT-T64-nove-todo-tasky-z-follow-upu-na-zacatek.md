---
id: HAIFA-REFINEMENT-T64
title: Nové TODO tasky z follow-upů na začátek fronty
status: done
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/run/store.py, aifactory/src/aifactory/run/task.py, aifactory/src/aifactory/run/followups.py, aifactory/tests/run/test_queue_prefs.py, aifactory/tests/run/test_followups_queue.py, aifactory/tests/run/test_followups.py, docs/decisions.md]
---

## Zadání
Nový task, který factory založí z follow-upů běhu do TODO stepu, se má automaticky zařadit na úplný začátek fronty tasků ke zpracování, tedy na začátek ruční fronty kanbanu (`task_queue`, `QueuePrefs.order`).

## Současný stav

- Funkce `followups.record` zakládá tasky a vrací `FollowUpOutcome.created` (`CreatedFollowUp.existed` říká, jestli task založil už dřívější pokus).
- `aifactory/src/aifactory/run/task.py` (`_record_follow_ups`) volá `followups.record` pod `store.serialized()` a má k dispozici `TaskRunStore`.
- `aifactory/src/aifactory/run/store.py` má `queue_prefs`, `set_queue_order`, `_prune_queue` a tabulku `task_queue (task_id, rank, excluded)`.
- Výběr (`select_next`, `select_ready`, `candidates`, `repo_candidates` v modulu fronty) bere `priority_order` (záznamy blokovaných tasků a jejich blokátorů), potom `prefer` a potom `prefs.order`.

## Co udělat

1. Do `TaskRunStore` přidat metodu (např. `queue_front(task_ids)`), která dané tasky dá na začátek ruční fronty: v zadaném pořadí před všechny tasky, které už rank mají. Ostatní tasky si ponechají vzájemné pořadí. Příznak `excluded` se nemění. Operace je atomická (jedna transakce) a je bezpečná při souběžných bězích.
2. V `_record_follow_ups` (`run/task.py`) po úspěšném `followups.record` zařadit na začátek fronty každý nově založený follow-up (`existed == False`) v pořadí, v jakém byl založen. Vynechat tasky člověka (`assignee: human`), protože žádný běh je nespustí, a tasky, které už existovaly. Platí to i pro resolve běh (`blocking=False`) a pro retry.
3. Selhání zápisu do fronty neshodí běh. Doplní jen varování k follow-upům.
4. Záznamy priority (`task_priority`, `priority_order`) zůstanou před ruční frontou: jde o blokovaný task a jeho blokátory, které jsou samy follow-upy téhož běhu. Logika výběru se jinak nemění.
5. Do `docs/decisions.md` do bodu **Follow-upy** připsat, že nový agentní follow-up jde na začátek ruční fronty.

## Mimo rozsah

- Porovnání follow-upu s backlogem (HAIFA-REFINEMENT-T65, T66).
- Změny UI kanbanu. Kanban frontu jen čte z `task_queue`.
- `.factory/`, backlog.

Hotovo znamená:
- Test ve `aifactory/tests/run/test_queue_prefs.py` ověří, že `queue_front` dá tasky na začátek v zadaném pořadí, zachová pořadí ostatních a nezmění `excluded`.
- Nový test `aifactory/tests/run/test_followups_queue.py` ověří, že po běhu se dvěma novými follow-upy jsou oba v `queue_prefs().order` na začátku v pořadí založení. Task člověka a follow-up, který už existoval, se na začátek nedostanou.
- Test ověří, že `select_ready` po takovém běhu vybere nový follow-up dřív než task, který byl předtím první ve frontě, pokud se dá spustit.
- `docs/decisions.md` popisuje nové pořadí.
- Celá dotčená testová sada je zelená.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-21 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/139 · náklady $0.00
