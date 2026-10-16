---
id: HEAL-S02-T03
title: "Vyčerpaná kvóta: pokračovat na záložním harnessu"
status: todo
depends_on: [HEAL-S01-T01]
---

## Zadání
Čtyři běhy HAIFA skončily na vyčerpaných kreditech Codexu, i když byl Claude Code k dispozici.

Zadání:
1. Agent může mít v konfiguraci záložního agenta nebo harness s modelem (návrh klíče a umístění: `agents.yaml` sdíleně, `local.yaml` lokálně, zapsat do `docs/decisions.md`).
2. Při selhání `quota` factory jednou automaticky pokračuje přes retry se záložním harnessem. Agent bez původní session dostane `## Continuation` jako dnes.
3. Bez zálohy dashboard nabídne „Pokračovat s jiným harnessem“ s výběrem z povolených a otestovaných harnessů.
4. Přepnutí je vidět v událostech běhu a v PR.

Hotovo znamená:
- Test s fake harnessem, který vrátí kvótu, a záložním, který doběhne.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
