---
id: HAIFA-REFINEMENT-T46
title: "Follow-upy z běhu: sloučit duplicitní a nehlásit, co už backlog kryje"
status: todo
depends_on: []
---

## Zadání
V NEO_HEF založil běh `b4239924` (ROB-S21-T005, 2026-10-19) dvě lidské úlohy se stejným obsahem: `ROB-TODO-T01` nahlásil builder, `ROB-TODO-T02` documenter. Obě žádají upřesnit u vlastníka legacy význam „aktivní seznam“ v opravě D173 (G47). Factory follow-upy z různých fází běhu neslučuje, takže člověk dostane stejný úkol dvakrát. Navíc nezkontroluje, jestli backlog už stejnou věc nekryje: dotčená úloha `ROB-S21-T004` už měla `depends_on` na lidskou úlohu `ROB-S31-H01` se stejným dotazem.

Zadání:
1. Follow-upy jednoho běhu se před zápisem do backlogu sloučí: stejný cíl (titul, dotčené úlohy, assignee) = jedna úloha, v `### Původ` všechny fáze, které ji nahlásily.
2. Agent, který follow-up hlásí, dostane v promptu seznam otevřených úloh, na kterých dotčené úlohy závisí (`depends_on`), a nehlásí, co už kryjí.

Hotovo znamená:
- Test: běh, ve kterém dvě fáze nahlásí stejný follow-up, založí jednu úlohu.
- Test: follow-up, který kryje existující závislost dotčené úlohy, se nezaloží (nebo se jen připojí jako related).
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
