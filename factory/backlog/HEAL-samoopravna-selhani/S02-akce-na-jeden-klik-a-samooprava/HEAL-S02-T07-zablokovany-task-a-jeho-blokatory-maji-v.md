---
id: HEAL-S02-T07
title: Zablokovaný task a jeho blokátory mají ve frontě přednost
status: done
depends_on: [HEAL-S02-T06]
writes: [aifactory/, docs/decisions.md]
---

## Zadání
Task zablokovaný během běhu čeká na odblokování příliš dlouho. Příklad z HAIFA: REFINEMENT-T36 se 15. 10. v 15:42 zablokoval na TODO-T09, řetěz pak jel REFINEMENT-T37 až T41 a TODO-T06, T09 běžel až další den ve 13:13 a T36 doběhl až po ručním spuštění.

Dnes (`run/queue.py`): přednost dostanou jen blokátory nově založené jako follow-up (`blockers_of`, ne existující tasky z `blocked_by`), jen pro jeden další výběr a jen v běžícím řetězu. Po dokončení blokátorů blokovaný task přednost nemá.

Zadání:
1. Při zablokování běhu (druh `blocked` z HEAL-S02-T06) se v trace DB uloží přednostní záznam: task a jeho blokátory, včetně existujících tasků z `blocked_by`.
2. Výběr dalšího tasku (`select_next`, `repo_candidates` a souběžné řetězy) bere v tomto pořadí: blokovaný task s přednostním záznamem, jehož blokátory jsou hotové; jeho nehotové blokátory (i blokátory blokátorů); fronta kanbanu a běžné pořadí. Kontroly kandidáta (sloty, kolize writes, auto_continue, excluded) platí beze změny.
3. Záznam platí i po skončení řetězu a při ručním spuštění řetězu. Zmizí, když task doběhne úspěšně, je zrušen, nebo když člověk přednost zruší.
4. Kanban ukáže tasky s předností nahoře fronty se štítkem „přednostně“ a tlačítkem pro zrušení přednosti. API a `factory task list` přednost vypíšou.
5. Zapsat do `docs/decisions.md` (Běh tasku): zablokovaný task a jeho blokátory mají přednost před frontou kanbanu.

Hotovo znamená:
- Testy výběru: blokátory před frontou kanbanu (i existující z `blocked_by`), blokovaný task hned po posledním blokátoru, přednost přežije konec řetězu, zrušení přednosti vrátí běžné pořadí.
- Vitest kanbanu se štítkem a zrušením přednosti.
- Dotčené testy projdou podle AGENTS.md, `just web-test`, `just web-build`, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-18 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/108 · náklady $6.37
