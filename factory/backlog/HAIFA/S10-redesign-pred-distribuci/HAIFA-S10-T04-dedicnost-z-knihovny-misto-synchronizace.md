---
id: HAIFA-S10-T04
title: Dědičnost z knihovny místo synchronizace
status: todo
depends_on: []
---

## Zadání
Agenti, workflow, skilly a rozšíření se hledají nejdřív v `.factory/` repa a když tam nejsou, v systémové knihovně (`$HAIFA_HOME/library`, bez knihovny seed). Kopie v repu má přednost a přepisuje knihovní. Synchronizace mezi knihovnou a repem zmizí.

Kde: `aifactory/src/aifactory/config/loader.py` (sestavení rosteru, promptů a workflow s dědičností), `library/` (manifest, update, config_edit add/export, config_transfer, state, multi_repo, migrations), `onboard/` (celé: sssf i pre_library onboarding a adopt se ruší), `check/` pravidla item_*, CLI (`factory update`, `factory config add|export|revert|items`, `factory onboard|adopt`), web (`/factory/plan|apply` akce update/add/export/onboard/adopt, FactoryItems, OnboardingPanel), skill.md. Přidání repa (`web/repos.py add_repo`) pak zapisuje jen `.factory/config.yaml` a `.gitignore`.

Hotovo znamená:
- Repo bez agentů a workflow v `.factory/` běží s knihovními; vlastní kopie v repu má přednost (test na obojí).
- Do trace běhu se zapíše commit knihovny, ze kterého běh četl.
- Skilly z knihovny se při startu běhu nakopírují do worktree (necommitují se); lokální skilly repa fungují jako dnes pro claude i codex.
- Akce „Přesunout do knihovny“ zapíše kopii z repa do knihovny, z repa ji smaže a commitne.
- Manifest, `factory update`, export/add/revert, onboarding a adopt jsou pryč i s testy; kód je viditelně štíhlejší.
- `just check` a `just e2e` projdou.

Pevná omezení: `vendor/` a `prototype/` se nemění.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
