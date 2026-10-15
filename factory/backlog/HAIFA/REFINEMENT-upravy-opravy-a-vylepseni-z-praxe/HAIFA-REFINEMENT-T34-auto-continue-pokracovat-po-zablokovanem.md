---
id: HAIFA-REFINEMENT-T34
title: "Auto continue: pokračovat po zablokovaném tasku (přednostně blokátorem) a jen v rámci projektu"
status: todo
workflow: build-test-review
depends_on: []
related: [HAIFA-S03-T16, HAIFA-S02-T06, HAIFA-TODO-T03]
writes: [aifactory/src/aifactory/run/queue.py, aifactory/src/aifactory/run/task.py, aifactory/src/aifactory/run/followups.py, aifactory/src/aifactory/run/store.py, aifactory/src/aifactory/guide/06-behy.md, aifactory/tests/run/]
---

## Zadání
## Cíl

### 1. Pokračování po selhání kvůli blokaci
Task může selhat proto, že je blokovaný a zjistí se to až v jeho průběhu: agent během běhu nahlásí `blocked_by` nebo follow-up s `blocks_task`. Factory pak v `run/task.py` ukončí běh s důvodem `blocked: task X waits for ...`. Pokud je u takového tasku zapnuté auto continue, řetěz se dnes zastaví se `stop == "failed"`. Místo toho má factory sama spustit další task ve frontě.

- Přednost dostane blokátor (dostanou blokátory), který vznikl (které vznikly) během selhaného tasku. Je to follow-up s `blocks_task`, který factory při běhu založila (`FollowUpOutcome.created` / `blocked_by`). Spustí se, pokud je spustitelný: `todo`, má workflow, není vyloučený v kanbanu, nekoliduje ve `writes` a nemá nesplněné závislosti.
- Pokud spustit nejde, pokračuje řetěz běžným výběrem `select_next`: ruční fronta z kanbanu, pak stejný step, pak zbytek projektu. Zablokovaný task se při tom přeskočí jako `blocked`.
- Platí to pro sekvenční řetěz (`run_chain`) i pro paralelní plnění slotů (`finished()` při `max_parallel_runs` > 1).
- Jakékoli jiné selhání (chyba buildu, červené testy, zamítnuté review, chyba harnessu…) dál zastaví řetěz se `STOP_FAILED` jako dosud.
- O pokračování rozhoduje stejné pravidlo jako po úspěchu: `--auto` nebo `auto_continue: true` zděděné selhaným taskem. Blokátor ani další task se nespustí, pokud jim pravidla auto-continue start nedovolují (`require_auto_continue`, `excluded`).
- Zablokovaný task zůstane nehotový a bez PR. Auto-merge se ho netýká.

### 2. Kontrola: auto continue jen ze stejného projektu
Ověřte, že řetěz auto-continue nikdy nespustí task z jiného projektu (kořenového kontejneru backlogu), a to ani přes ruční frontu z kanbanu. `candidates()` filtruje přes `ancestors(after)[-1]`. Totéž ověřte pro nový výběr blokátoru: follow-upy se zakládají do `TODO` stepu téhož projektu. Pokud kontrola najde únik, opravte ho.

## Akceptační kritéria
- Test: task s auto continue skončí jako blokovaný a během běhu vznikl spustitelný blokátor. Řetěz pak jako další spustí právě tento blokátor a neskončí se `STOP_FAILED`.
- Test: blokovaný task bez spustitelného blokátoru. Řetěz pokračuje dalším kandidátem ze `select_next`, nebo skončí `exhausted`.
- Test: neblokační selhání dál končí `STOP_FAILED`.
- Test: blokovaný task bez auto continue (a bez `--auto`) nepokračuje.
- Test pro paralelní řetěz (`max_parallel_runs` > 1) se stejným chováním po blokaci.
- Test: kandidát z jiného projektu, i když je zařazený v ruční frontě kanbanu, se v řetězu nespustí.
- Aktualizovaný docstring `run/queue.py` a návod `guide/06-behy.md`, pokud popisují zastavení po selhání.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
