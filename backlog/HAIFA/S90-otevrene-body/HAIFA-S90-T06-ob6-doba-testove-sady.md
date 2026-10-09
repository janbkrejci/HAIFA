---
id: HAIFA-S90-T06
title: OB6 Doba testové sady
status: cancelled
workflow: manual-test-duration
depends_on: []
writes: [docs/decisions.md, "backlog/HAIFA/REFINEMENT-upravy-opravy-a-vylepseni-z-praxe/HAIFA-REFINEMENT-T*-zrychlit-testovou-sadu.md"]
---

## Zadání
Změř dobu `just test` na klidném stroji. Úkol 2.20 časové cíle neověřil, protože stroj byl přetížený.

Podmínka: spustit na stroji bez souběžných běhů.

Done means:
- Změřená doba a nejpomalejší testy (`pytest --durations=15`) jsou zapsané v `docs/decisions.md`.
- Pokud sada běží déle než 3 minuty, vznikne task na zrychlení.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
