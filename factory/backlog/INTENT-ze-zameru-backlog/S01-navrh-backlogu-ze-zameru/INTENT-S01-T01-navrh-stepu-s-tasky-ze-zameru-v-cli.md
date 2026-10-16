---
id: INTENT-S01-T01
title: Návrh stepu s tasky ze záměru v CLI
status: todo
depends_on: []
related: [INTENT-S01-T02, INTENT-S01-T03, HAIFA-REFINEMENT-T29, HAIFA-REFINEMENT-T18]
writes: [aifactory/src/aifactory/cli.py, aifactory/src/aifactory/backlog/, aifactory/src/aifactory/workflow/, aifactory/src/aifactory/seed/, aifactory/src/aifactory/library/, aifactory/src/aifactory/skill/, aifactory/tests/]
---

## Zadání
1. `factory backlog propose "<záměr>" [--project ID] [--step ID]` spustí read-only agenta. Izolace je stejná jako u návrhu workflow v `aifactory/src/aifactory/workflow/adaptive.py`: izolovaný checkout na commitu, agent bez writes. Agent prozkoumá repo a backlog a vrátí typovaný návrh (pydantic model, jeho JSON schéma dostane agent v promptu). Návrh je buď nový step (v projektu z `--project`), nebo tasky do existujícího stepu (`--step`). U každého tasku obsahuje:
   - `title`,
   - zadání s částí „Hotovo znamená“,
   - `depends_on`, a to i na existující tasky v backlogu,
   - `writes`,
   - `workflow` z katalogu.
2. Návrh se validuje proti backlogu stejně jako `factory task add`: platná ID a závislosti, žádné cykly ani odkazy na sebe sama, existující workflow. Neplatný návrh dostane agent zpět s chybami k opravě nejvýš jednou. Pokud neprojde ani podruhé, příkaz skončí chybou a nic nezapíše.
3. Bez `--apply` příkaz jen ukáže náhled: strom step → tasky a jejich texty. S `--json` vrátí strojový výstup. `--apply` zapíše návrh přes `backlog/edit` a nic necommitne.
4. Prompt agenta je v semínku knihovny (`aifactory/src/aifactory/seed/`), aby šel přepsat v `.factory/`.
5. Nový příkaz se doplní do popisu CLI (`skill/commands.py`, `skill.md`), aby ho znal `factory --skill`.

Hotovo znamená:
- Je test s fake harnessem, který ověří tři věci: platný návrh se zobrazí v náhledu i v `--json`; neplatný návrh se jednou vrátí agentovi a opravený projde, a když neprojde ani oprava, příkaz skončí chybou bez zápisu; `--apply` zapíše soubory stepu a tasků a nevznikne commit.
- Prompt agenta jde přepsat v `.factory/` a přepis se použije.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
