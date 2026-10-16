---
id: HAIFA-TODO-T13
title: Zapsat obnovu knihovny při instalaci do docs/decisions.md
status: done
workflow: build-review
depends_on: []
related: [HAIFA-TODO-T08]
writes: [docs/decisions.md]
---

## Zadání
Do docs/decisions.md v sekci 'Konfigurace a knihovna' přidat hned za bod 'Dědičnost z knihovny' nový bod, například: '- **Obnova knihovny při instalaci:** instalace a upgrade HAIFA spustí `factory library seed --all`, který nahradí všechny položky semínka v knihovně verzí z nainstalovaného balíčku, i ty, které tým upravil. Položky mimo semínko zůstanou a kopie v `.factory/` rep se nikdy nemění. Knihovna obsahuje i skill `factory` vygenerovaný z `factory --skill`. Ruční `factory library seed` bez `--all` dál ponechá položky změněné týmem.' Task musí mít docs/decisions.md v povolených cestách.

### Původ

Vznikl při běhu `37daf127` tasku `HAIFA-TODO-T08` (Zapsat obnovu knihovny při instalaci do docs/decisions.md), v kroku `build` (agent builder).
Důvod: HAIFA-TODO-T08 má jen upravit docs/decisions.md, ale ten soubor leží v kořeni repa mimo povolené cesty tasku (aifactory/, justfile, spec a doc tasku). Úprava by se vrátila a fáze by selhala. Chování je v kódu: aifactory/src/aifactory/library/reseed.py, cli.py (`library seed --all`, instalace a upgrade hlásí library_refreshed).
Task `HAIFA-TODO-T08` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-TODO-T08 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-16 · workflow build-review · PR https://github.com/janbkrejci/HAIFA/pull/56 · náklady $0.32
