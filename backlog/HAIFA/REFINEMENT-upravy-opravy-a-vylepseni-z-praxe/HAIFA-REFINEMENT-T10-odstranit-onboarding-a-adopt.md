---
id: HAIFA-REFINEMENT-T10
title: "Odstranit onboarding (sssf, pre_library) a factory adopt"
status: todo
workflow: simple-sdlc
depends_on: []
writes: [aifactory/, docs/sssf/]
---

## Zadání
HAIFA už nebude převádět existující factory do svého formátu. Odstraň celý onboarding: `factory onboard` ze sssf (O1), `factory onboard` z `pre_library` (O2) a `factory adopt` (O3). Repo se do HAIFA dostane jen přes `factory init`. Testy onboardingu teď na `main` padají (kopírují `.factory/` repa HAIFA ze staré historie a golden výstupy sssf), takže blokují ostatní tasky.

Where: `aifactory/src/aifactory/onboard/` (celý balíček včetně `sssf_stock/`), `aifactory/src/aifactory/cli.py` (`onboard`, `adopt`), `aifactory/src/aifactory/web/` (`factory.py`, `overview.py`, `repos.py`, `sssf_cleanup.py`), frontend `aifactory/web/src/` (`components/factory/OnboardingPanel.vue` a jeho použití, akce onboardingu v přehledu rep), `aifactory/src/aifactory/check/` (`model.py`, `context.py`, `repo_rules.py`), `aifactory/src/aifactory/config/manifest.py`, `aifactory/src/aifactory/library/` (`install.py`, `install_commit.py`), `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), `aifactory/tests/onboard/` a další testy, které onboarding nebo `vendor/sssf` používají, `docs/sssf/`.

Done means:
- Příkazy `factory onboard` a `factory adopt` ani jejich API a obrazovky v dashboardu neexistují. Balíček `aifactory.onboard` a `sssf_stock` jsou smazané.
- Stav repa (dnes `aifactory.onboard.state.repo_state`) přežije v jednodušší podobě mimo smazaný balíček: repo s manifestem v base je nainstalované, konfigurace jen v pracovním stromu je necommitnutá, repo bez `.factory/` potřebuje `factory init`. Repo s `.factory/` bez manifestu nebo se sssf (`adws/`) se hlásí jako nepodporované s radou, že HAIFA ho nepřevezme. Stavy `sssf` a `pre_library` a příznaky `sssf_leftover` a `alternate_rosters` zmizí. `factory check`, přehled rep a dashboard používají nový stav.
- Manifest nemá `onboarding.source` `sssf` ani `pre_library`. Starší manifest s těmito hodnotami se dál načte.
- `factory init` odmítá existující konfiguraci jako dnes, bez rady na `factory onboard`.
- Kód ani testy v `aifactory/` se neodkazují na `vendor/sssf/`, aby šel adresář po merge smazat. Odkazy v komentářích `engine/`, které jen popisují původ portu, mohou zůstat.
- `docs/sssf/` je smazaný.
- `factory --skill` onboarding ani adopt nepopisuje. Nepoužité kódy chyb jsou pryč ze `skill/codes.py`.
- Testy (pytest a vitest): stav repa pro nainstalované, necommitnuté, prázdné a nepodporované repo, `factory check` nad každým z nich, dashboard bez onboardingu. Testy onboardingu jsou smazané.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: smazání `vendor/sssf/` a úpravy `.factory/`, `CLAUDE.md`, `AGENTS.md` (chráněné, udělá operátor po merge), změny `factory init` mimo radu na onboard, `prototype/`.

Pevná omezení:
- `.factory/`, `vendor/`, `prototype/`, `CLAUDE.md` a `AGENTS.md` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
