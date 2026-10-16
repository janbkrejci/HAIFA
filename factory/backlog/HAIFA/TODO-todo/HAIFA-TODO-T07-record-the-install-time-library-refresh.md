---
id: HAIFA-TODO-T07
title: Record the install-time library refresh in docs/decisions.md
status: todo
depends_on: [HAIFA-TODO-T12]
related: [HAIFA-REFINEMENT-T35]
writes: [docs/decisions.md]
---

## Zadání
Add or adjust the decision in docs/decisions.md, next to the 'Dědičnost z knihovny' bullet. Install and upgrade refresh every seed item in the library to the installed version (`factory library seed --all`). Items outside the seed stay. Repo copies in .factory/ are never touched. The library contains the `factory` skill generated from `factory --skill`. Manual `factory library seed` without `--all` still keeps team-changed items.

### Původ

Vznikl při běhu `794b94cb` tasku `HAIFA-REFINEMENT-T35` (Knihovna místo „Tento počítač“, tabbar bez scrollbaru, dialogy knihovny a obnova knihovny při instalaci nové verze), v kroku `plan` (agent planner).
Důvod: HAIFA-REFINEMENT-T35 changes the seed semantics. Install and upgrade now run `factory library seed --all`, which replaces team edits of seed items in the library; customizations belong in the repos' .factory/. The library also gains a generated `skill/factory` seed item. docs/decisions.md is outside the task's allowed paths, so the decision could not be recorded there.

<!-- factory: follow-up-of=HAIFA-REFINEMENT-T35 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
