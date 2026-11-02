---
id: HAIFA-REFINEMENT-T101
title: "Agenti dokončí objevenou práci na místě, follow-up jen jako poslední možnost"
status: done
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/seed/agents/builder/system.md, aifactory/src/aifactory/seed/agents/planner/system.md, aifactory/src/aifactory/seed/agents/tester/system.md, aifactory/src/aifactory/seed/agents/reviewer/system.md, aifactory/src/aifactory/seed/agents/documenter/system.md, aifactory/tests/run/test_follows_prompt.py]
---

## Zadání
Pravidlo týmu: práci, o které nikdo nevěděl a kterou agent objeví během tasku, má udělat hned v tomto tasku. Nový task smí založit jen tehdy, když to opravdu jinak nejde. Dnešní sekce „Unfinished work“ v promptech agentů posílá do `follow_ups` všechno, co je „out of scope, extra, or a changed intent“. V praxi (NEO_HEF, projekt UIRTODO, factory 0.1.545 až 0.1.563) tak z jednoho běhu vznikají drobné a duplicitní tasky a každý pak stojí celý běh workflow (u haifa-implement-task přibližně $9,3). Za tři dny vzniklo 40 tasků z follow-upů a 7 z nich se rušilo ručně jako duplicity.

Co udělat:
- V sekci „Unfinished work“ seed promptů `builder`, `planner`, `tester`, `reviewer` a `documenter` (aifactory/src/aifactory/seed/agents/<agent>/system.md) změnit pravidlo pro follow-upy takto: objevenou práci, kterou agent zvládne, dokončí v tomto tasku. Když by ho stála hodně kontextu, deleguje ji na subagenta. Cestu mimo `writes` hlásí přes `needs_writes`, ne jako follow-up (to už prompty říkají, zachovat). Follow-up je poslední možnost, jen když práci v tomto běhu opravdu udělat nejde: patří existujícímu tasku backlogu (agent ho jmenuje), nebo by změnila cíl tasku.
- Zúžit `for_human` na přístupy a credentials, akci v systému mimo repo a rozhodnutí, které agent sám udělat nesmí. Všechna rozhodnutí z jednoho běhu patří do jednoho follow-upu `for_human`, ne do jednoho za každého agenta.
- Documenter nemá z poznámky builderu „mimo úlohu“ dělat nový follow-up, když stejnou práci už v běhu ohlásil jiný agent. Má ji nechat jen jako zjištění v dokumentu tasku, ne jako otevřenou práci.
- „Never leave open work in the repository“ zůstává beze změny.

Mimo rozsah: kód factory (triáž, fronta, follow-upy), prompty ostatních agentů.

Hotovo znamená:
- Všech pět promptů má stejné nové znění sekce a test v aifactory/tests/run/test_follows_prompt.py hlídá klíčové věty (dokonči na místě, subagent, follow-up jen jako poslední možnost, zúžený `for_human`).
- Stávající testy seed promptů procházejí.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-02 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/196 · náklady $0.00
