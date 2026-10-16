---
id: INTENT-S01-T01
title: Návrh stepu s tasky ze záměru v CLI
status: todo
depends_on: []
---

## Zadání
Zadání:
1. `factory backlog propose "<záměr>" [--project ID] [--step ID]` spustí read-only agenta (stejná izolace jako návrh workflow v `workflow/adaptive.py`), který prozkoumá repo a backlog a vrátí typovaný návrh: nový step nebo tasky do existujícího, u každého tasku title, zadání s částí „Hotovo znamená“, `depends_on` (i na existující tasky), `writes` a `workflow`.
2. Návrh se validuje proti backlogu stejně jako `factory task add`. Neplatný návrh se vrátí agentovi k opravě nejvýš jednou.
3. Výstup je náhled (strom a texty) a `--json`. `--apply` návrh zapíše přes `backlog/edit` a nic necommitne.
4. Prompt agenta je v semínku knihovny, aby šel přepsat v `.factory/`.

Hotovo znamená:
- Test s fake harnessem: návrh se validuje, neplatný se opraví, `--apply` zapíše soubory.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
