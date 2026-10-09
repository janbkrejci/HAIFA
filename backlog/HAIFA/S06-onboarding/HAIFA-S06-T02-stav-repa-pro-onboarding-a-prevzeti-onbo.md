---
id: HAIFA-S06-T02
title: "Stav repa pro onboarding a převzetí onboardovaného repa (`factory adopt`)"
status: done
depends_on: [HAIFA-S05-T06, HAIFA-S05-T04, HAIFA-S01-T10]
---

## Zadání
Přidej funkci stavu repa pro onboarding a příkaz `factory adopt` pro stroj kolegy. Stav říká, jestli repo potřebuje instalaci, jednorázové vytěžení, nebo už je onboardované. Onboardované repo se na jiném stroji nikdy znovu nevytěží (rozhodnutí 8): adopt jen doplní místní knihovnu podle commitnuté konfigurace a do repa nic nezapíše.

Where: nový balíček `aifactory/src/aifactory/onboard/`, `aifactory/src/aifactory/config/` (`source.py`, `status.py`), manifest a stavy z L4 a knihovna z L2 a L3 v `aifactory/src/aifactory/library/`, modul kontroly z M6, `aifactory/src/aifactory/cli.py`, `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v nové složce `aifactory/tests/onboard/`.

Done means:
- Stav repa z base, vyhodnocený v tomto pořadí: `onboarded` (`.factory/manifest.yaml`), `pre_library` (`.factory/config.yaml` nebo `agents.yaml` bez manifestu), `sssf` (`adws/adw_sssf_config/*.yaml` bez `.factory/`), `working_tree` (konfigurace jen v pracovním stromu), `none`. Příznaky `sssf_leftover` (`adws/` vedle `.factory/`) a `alternate_rosters`. Stav vrací i akci (`init`, `onboard`, `adopt`, `config_commit`) a u `onboarded` blok `onboarding` z manifestu.
- Funkce jen čte: `rev-parse`, `ls-tree` a `cat-file` s `GIT_OPTIONAL_LOCKS=0`, bez fetch a bez hooků.
- `factory check` vrací tento stav místo dnešních `none`, `working_tree` a `base` a nález s akcí podle stavu.
- `factory adopt [--repo] [--dry-run] --json` přijme jen `onboarded` (jinak `not_onboarded`). Bez knihovny vrátí `library_missing` s příkazem `factory library clone <remote z manifestu>`. Knihovna s jiným `id` dá varování `library_mismatch`. Položku, kterou knihovna nemá, naimportuje z kopie v base (zápis knihovny z L3). Verzi chybějící v existující položce nechá jako `unknown` s opravou `factory config export --as`. Vrátí stavy položek a do repa nic nezapíše.
- `factory --skill` popisuje stavy a převzetí. Nové kódy jsou v `skill/codes.py`.
- Testy (pytest): každý stav a příznak (kopie `.factory/` HAIFA s `adws/`, fixtura sssf z `vendor/sssf/templates/`, konfigurace jen v pracovním stromu), stav nezmění index ani refy, adopt bez knihovny, s jinou knihovnou a s chybějící položkou (import a push do holého remote), repo po adopt bajtově stejné.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: vytěžení (O2, O4), registr a dashboard, fetch remote repa.

Pevná omezení:
- Stav ani adopt nic nezapíší do repa.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/56 · náklady $5.25
