---
id: INTENT-S02-T02
title: Agenti navazujícího tasku vidí celý původní task
status: done
depends_on: [INTENT-S02-T01]
---

## Zadání
Zadání:
1. Prompt každé fáze běhu tasku s `follows` obsahuje sekci o původním tasku: jeho celé zadání, spec a dokumentaci tasku z `docs_root` (cesty k souborům a jejich obsah do rozumného limitu), URL a merge commit jeho PR, seznam změněných souborů a shrnutí jeho běhů.
2. Když se něco nevejde do limitu, prompt uvede cestu k souboru v worktree, odkud si to agent přečte.
3. Řetěz `follows` přes více generací zahrne jen přímého předchůdce a odkazy na starší.

Hotovo znamená:
- Test sestaveného promptu navazujícího tasku (fake harness) včetně limitu a odkazů.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-17 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/93 · náklady $1.77
