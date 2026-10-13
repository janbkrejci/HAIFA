---
id: HAIFA-S02-T05
title: Pokračování selhaného nebo zastaveného běhu s kontextem agentů
status: done
depends_on: []
---

## Zadání
Selhaný nebo ručně zastavený běh tasku jde dnes jen spustit znovu od začátku: `factory task run` založí novou větev a nový worktree a agenti začínají bez kontextu. Pokračování se teď obchází poznámkou typu „Continue the EXISTING implementation from run 7fc82951… Original plan/review are in …/context_handoff/“ (běh `d4f262d7` tasku S01-T21). Agenti pak znovu zjišťují stav, který už měli. `task resume` umí jen pozastavený běh a `task return` jen PR po review.

Zadání: pokračování selhaného nebo zastaveného běhu se zachováním kontextu a historie agentů.

1. Pokračuje se ve stejném worktree a na stejné větvi, od fáze, která selhala nebo byla zastavená (volitelně od zvolené fáze). Hotové fáze se neopakují.
2. Každý agent naváže na svou předchozí session (`claude --resume`, `codex exec resume`, u pi obdobně). Když session není k dispozici, dostane přehled z `context_handoff/` a z výstupů předchozích fází.
3. Volitelná poznámka operátora jde agentům pokračující fáze.
4. Když se base mezitím posunula:
   - nejdřív se stáhne base z remote (jako `factory config pull`). Když nejde posunout, pokračování se zastaví s jasnou chybou a nic se nezmění,
   - potom se větev běhu rebasuje na novou base (existující krok `rebase`),
   - konflikt řeší stejný postup jako `factory task resolve` (agent mění jen konfliktní soubory). Když neuspěje, větev zůstane, jak byla, a pokračování se nespustí,
   - po rebase se před review vždy znovu spustí krok `test`, i když testy dřív prošly, aby review neschvalovalo výsledky ke starému kódu.
5. Běh čte konfiguraci a backlog z aktuální base. Když selhaná fáze v novém workflow tasku není, začne se od první fáze, která v něm existuje, a vypíše se varování.
6. Nejde pokračovat v běhu, jehož task je už schválený nebo mergnutý, ani když běží jiný běh téhož tasku.
7. CLI: `factory task retry ID [--note TEXT] [--from FÁZE] [--json]`. Dashboard: tlačítko u selhaného nebo zastaveného běhu v detailu běhu i u tasku, s polem pro poznámku.
8. Trace: pokračování je navazující pokus téhož běhu (stejný `run_id` nebo jasná vazba na původní běh), náklady a tokeny se sčítají a detail běhu ukáže, kde se navázalo.

Hotovo, když:
- selhaný běh (např. neprošlé review) jde dokončit bez opakování hotových fází a agenti navážou na své sessions,
- zastavený běh jde dokončit stejně,
- posunutá base se před pokračováním dorovná a větev rebasuje, s konfliktem přes resolve a s novým testem před review,
- testy bez sítě a živých modelů (falešné harnessy) pokryjí pokračování po selhání, po zastavení, s posunutou base bez konfliktu i s ním a odmítnutí u schváleného tasku.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-13 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/24 · náklady $0.00
