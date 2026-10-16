---
id: HEAL-S02-T03
title: "Vyčerpaná kvóta: pokračovat na záložním harnessu"
status: done
depends_on: [HEAL-S01-T01]
related: [HEAL-S02-T04, HAIFA-S02-T05]
writes: [aifactory/, docs/decisions.md]
---

## Zadání
Čtyři běhy HAIFA skončily na vyčerpaných kreditech Codexu, i když byl Claude Code k dispozici.

Zadání:
1. Agent může mít v konfiguraci záložního agenta nebo harness s modelem. Návrh klíče a umístění: `agents.yaml` sdíleně, `local.yaml` lokálně. Zvolený klíč, umístění a pořadí přednosti (local před sdíleným) zapsat do `docs/decisions.md`.
2. Při selhání s druhem `quota` (rozpoznává adaptér harnessu podle HEAL-S01-T01) factory jednou automaticky pokračuje přes retry se záložním harnessem. Agent bez původní session (jiný harness) dostane `## Continuation` jako dnes. Záloha se zkouší nejvýš jednou: když selže i ona, běh skončí selháním s druhem `quota` a nezacyklí se.
3. Bez zálohy dashboard u běhu selhaného na kvótě nabídne „Pokračovat s jiným harnessem“. Výběr je jen z povolených a otestovaných harnessů a pokračování proběhne jako retry s vybraným harnessem.
4. Přepnutí je vidět v událostech běhu (z jakého harnessu nebo modelu na jaký a proč) a v popisu PR.

Hotovo znamená:
- Test s fake harnessem, který vrátí kvótu, a záložním, který doběhne: běh skončí úspěšně, v událostech je přepnutí a záložní agent dostal `## Continuation`.
- Test, že bez nakonfigurované zálohy se automaticky nepřepíná a běh zůstane selhaný s druhem `quota`.
- Rozhodnutí o klíči a umístění je zapsané v `docs/decisions.md`.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-16 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/74 · náklady $8.33
