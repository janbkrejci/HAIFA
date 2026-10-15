---
id: HAIFA-REFINEMENT-T28
title: Automerge se musí postarat i o zelenou CI pipeline
status: done
workflow: simple-sdlc
depends_on: []
related: [HAIFA-S03-T11, HAIFA-S02-T04, HAIFA-S03-T17, HAIFA-S03-T15, HAIFA-S02-T06, HAIFA-S09-T01]
writes: [aifactory/src/, aifactory/tests/, aifactory/web/]
---

## Zadání
Schválím-li PR a dám ho mergnout, nebo když ho jde mergnout automerge, tak se proces musí postarat o zelenou CI pipeline, pokud je v remote pipeline nastavená. Když neprojde zeleně, musí do téhož PR udělat opravy a úpravy, které jsou potřeba.

## Současný stav (kontext z repa)
- `aifactory/src/aifactory/review/automerge.py`: `settled_checks` počká, až checky doběhnou (`AUTO_MERGE_CHECKS_TIMEOUT`), a `hosting_blocker` při červených checkách jen vrátí `checks_failing` a merge skončí. Nic se neopravuje.
- Ruční schválení (`approve_task` → `_approve` v `review/flow.py`) checky vůbec nečte. Před merge pushne commit `status: done`, takže se CI spustí znovu na novém headu.
- `GitHubProvider.checks` čte `gh pr checks`. `AzureProvider` checky nečte, takže vrací `none`.
- Vzor pro opravný běh do téhož PR existuje: auto-resolve konfliktu (`resolve_and_merge` s workflow `resolve-reviewed`).

## Požadované chování
1. Ruční schválení (CLI `factory task approve` i dashboard) i auto-merge před merge počkají na výsledek CI checků PR. Čeká se na checky headu, který se bude mergovat, tedy i po pushi commitu `status: done`.
2. Když remote žádné checky nemá (`none`, ani po čekání na jejich objevení), merge proběhne jako dnes.
3. Když checky skončí zeleně, proběhne merge.
4. Když některý check skončí červeně, spustí se opravný běh na větvi téhož PR, ne v novém PR. Agent dostane názvy selhaných checků a podle možností i jejich výstup nebo log. Opraví, co je potřeba, změny pushne do téhož PR a znovu se čeká na CI.
5. Počet kol opravy je omezený. Když se CI ani tak nezazelená (nebo checky nedoběhnou včas), merge neproběhne. PR zůstane otevřený a důvod se zaznamená stejně jako dnešní chyby auto-merge (`auto_merge_error`, viditelné v dashboardu a CLI).
6. Opravný běh je vidět jako běh tasku, podobně jako dnešní auto-resolve.

## Akceptační kritéria
- Testy s falešným providerem pokryjí tyto scénáře: bez checků → merge; zelené → merge; červené → opravný běh do téže větve, pak zelené → merge; červené i po vyčerpání pokusů → bez merge a se zaznamenaným důvodem. Pokryjí auto-merge i ruční approve.
- Stávající testy auto-merge a approve (`tests/run/test_auto_merge.py`, `tests/review/`) projdou.
- Dokumentace chování v průvodci (`guide/07-review.md`) odpovídá novému chování.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-15 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/40 · náklady $7.87
