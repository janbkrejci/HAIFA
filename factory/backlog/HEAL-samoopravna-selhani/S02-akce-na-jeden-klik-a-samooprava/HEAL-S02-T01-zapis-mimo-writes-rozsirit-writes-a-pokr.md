---
id: HEAL-S02-T01
title: "Zápis mimo writes: rozšířit writes a pokračovat"
status: done
archived: true
depends_on: [HEAL-S01-T03]
---

## Zadání
Zadání:
1. U selhání `writes_violation` nabídne dashboard i CLI akci „Povolit tyto cesty a pokračovat“: přidá porušené cesty do `writes` tasku (přes `backlog/edit`, commit do base podle `base_changes`) a spustí `factory task retry`.
2. Cestu do `protected_files` nebo do backlogu akce nenabídne a vysvětlí proč.
3. CLI: `factory task retry ID --allow-writes` udělá totéž.

Hotovo znamená:
- Test: běh selže na zápisu mimo writes, akce rozšíří writes, retry doběhne.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-16 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/72 · náklady $4.81
