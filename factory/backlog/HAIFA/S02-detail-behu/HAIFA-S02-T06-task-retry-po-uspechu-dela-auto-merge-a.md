---
id: HAIFA-S02-T06
title: task retry po úspěchu dělá auto-merge a auto-continue jako task run
status: done
archived: true
depends_on: []
related: [HAIFA-S02-T05]
---

## Zadání
Retry běhu `abab673d` (HAIFA-REFINEMENT-T14) skončil `succeeded` a otevřel PR #25, ale výsledek má `auto_merge: null` a žádný `chain`: PR zůstalo otevřené i po zelených kontrolách CI a řetěz se zastavil. `factory task run` po úspěchu PR mergne (auto_merge) a pokračuje dalším ready taskem (auto_continue).

Zadání: `factory task retry` (CLI i dashboard) se po úspěšném pokusu chová stejně jako `task run`: auto-merge podle `auto_merge` tasku a auto-continue podle `auto_continue` / `--auto`, včetně fronty kanbanu.

Hotovo znamená:
- Test: úspěšný retry tasku s `auto_merge: true` PR mergne a s `auto_continue: true` spustí další ready task.
- Bez těchto voleb se retry chová jako dnes.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-13 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/28 · náklady $2.12
