---
id: HEAL-S01-T02
title: "Accept not met vysvětlí, co neprošlo"
status: done
depends_on: [HEAL-S01-T01]
---

## Zadání
`accept not met` je nejčastější chyba (10 z 33 selhání v HAIFA) a nic neříká.

Zadání:
1. Detail selhání `accept_not_met` obsahuje vyhodnocený výraz `accept`, hodnotu každého pole, které v něm je (např. `test.passed=false`, `review.approved=false`), a počet kol smyček `repeat`, které proběhly.
2. Přiloží poslední výtky review a poslední neprošlé kontroly testu (z envelope), zkrácené na rozumnou délku.
3. Text chyby v `task_runs.error` je jedna věta, např. „Review neschválilo ani po 2 kolech: <první výtka>“.

Hotovo znamená:
- Test workflow, které skončí na accept, ověří detail i text chyby.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-16 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/68 · náklady $2.22
