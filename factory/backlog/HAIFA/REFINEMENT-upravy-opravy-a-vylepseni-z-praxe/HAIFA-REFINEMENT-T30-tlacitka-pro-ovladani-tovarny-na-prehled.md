---
id: HAIFA-REFINEMENT-T30
title: Tlačítka pro ovládání továrny na Přehledu
status: todo
workflow: simple-sdlc
depends_on: []
related: [HAIFA-S01-T19, HAIFA-S03-T16, HAIFA-S03-T19, HAIFA-REFINEMENT-T20, HAIFA-S10-T02]
writes: [aifactory/src/aifactory/web/, aifactory/src/aifactory/run/, aifactory/web/src/, aifactory/tests/]
---

## Zadání
Na Přehledu repozitářů (`OverviewView.vue` / `RepoCard.vue`, API `GET /api/overview`) přidat u každého repozitáře ovládání továrny a souhrn stavů tasků.

## Spustit továrnu
- Zelené tlačítko **Spustit továrnu** (ikona Play) se zobrazí jen tehdy, když zároveň:
  - v repu existují připravené tasky (stav `ready`, tj. s efektivním workflow, které by výběr auto-continue mohl spustit),
  - není překročen limit paralelních běhů (`max_parallel_runs` z `.factory/config.yaml`), tj. je aspoň jeden volný slot.
- Po kliknutí se spustí tolik paralelních běhů, kolik je možné: nejvýš počet volných slotů (`max_parallel_runs` minus běžící) a nejvýš počet připravených tasků. Použít stávající mechanismus auto-continue / řetězu (`run/queue.py`, `web/chains.py`, `web/launcher.py`), stejné pořadí výběru (ruční fronta kanbanu, vyloučené tasky se nespouští, kolize zápisových cest a závislosti se respektují). Nevymýšlet paralelní mechanismus vedle stávajícího.
- Na akci se zobrazí spinner (jako u ostatních spouštěcích akcí).

## Souhrn stavů tasků
- Na Přehledu u každého repa zobrazit souhrn, kolik tasků je v kterém stavu (stavy podle backlogu, např. todo / ready / běží / review / done …, tak, jak je backlog API už rozlišuje).

## Pauza a Stop
- Přidat tlačítka **Pauza** a **Stop** (ikony jako na přehrávači), která provedou pauzu, resp. stop pro všechny běžící tasky daného repa (stávající `pause_run` / `stop_run` pro každý běžící běh, ať se nové běhy z řetězu už nespouští).
- Po stisku zobrazovat, jestli je už opravdu zastaveno/pozastaveno, nebo ještě něco dobíhá (např. „Zastavuje se – dobíhají 2 běhy“ → „Zastaveno“), dokud nedoběhnou všechny dotčené běhy.
- Tlačítka zobrazovat jen tehdy, když něco běží (resp. je co pozastavit nebo zastavit).

## Akceptační kritéria
- Spustit továrnu je vidět právě tehdy, když existuje připravený task a volný slot; po kliknutí běží min(volné sloty, připravené tasky) nových běhů.
- Souhrn stavů tasků odpovídá backlogu repa.
- Pauza i Stop zasáhnou všechny běžící běhy repa a UI ukazuje přechod „dobíhá“ → „zastaveno/pozastaveno“.
- Backend endpointy i frontendové komponenty mají testy (pytest, vitest); stávající testy Přehledu zůstanou zelené.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
