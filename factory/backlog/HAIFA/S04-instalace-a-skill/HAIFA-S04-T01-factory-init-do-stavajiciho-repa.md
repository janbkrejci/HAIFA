---
id: HAIFA-S04-T01
title: "`factory init` do stávajícího repa z knihovny"
status: done
workflow: simple-sdlc
depends_on: [HAIFA-S03-T01, HAIFA-S03-T02, HAIFA-S05-T01, HAIFA-S05-T03, HAIFA-S05-T04]
---

## Zadání
Přidej příkaz `factory init`, který do repa bez factory zapíše konfiguraci s agenty a workflow z knihovny v domově (bez knihovny ze semínka v balíčku) a manifest s původem každé položky (`docs/decisions.md`: Instalace do repa, Konfigurace jako hybrid). Dnes `.factory/` nezakládá žádný příkaz.

Where: `aifactory/src/aifactory/cli.py`, `aifactory/src/aifactory/library/` (položky, semínko, knihovna a manifest z L1, L2 a L4), `aifactory/src/aifactory/config/` (`settings.py`, `loader.py`), `aifactory/src/aifactory/skill/` (`codes.py`, `skill.md`), testy v `aifactory/tests/`. Vzor: `vendor/sssf/cookbooks/install.md`.

Done means:
- `factory init [--base VĚTEV] [--provider local|github] [--agents planner,builder,reviewer,documenter] [--bind AGENT=HARNESS[:MODEL[:THINKING]]]… [--workflows simple-sdlc] [--force] --json` zapíše `.factory/config.yaml`, `.factory/agents.yaml` (slot pro každého agenta: `purpose` z položky, vazby z jejích `defaults` přepsané `--bind`, `$specs_dir/` a `$docs_dir/` nahrazené adresáři z `config.yaml`), `.factory/prompts/<agent>/{system,user}.md`, `.factory/workflows/<jméno>.yaml`, `.factory/manifest.yaml` (formát 1, `written_by`, knihovna `id`, `name` a `remote` bez přihlašovacích údajů, bez knihovny null, blok `onboarding` se `source: init`, položky s verzí), adresář backlogu a řádky do `.gitignore` (`.factory/data/`, `.factory/worktrees/`, `.factory/local.yaml`, `.factory/trace.db*`). Výchozí base je aktuální větev, provider `local`, agenti planner, builder, reviewer a documenter a workflow `simple-sdlc`.
- Workflow přidá agenty rolí svých kroků, které v `--agents` chybí (například `scout` pro workflow `scout`).
- Odmítne repo s `.factory/manifest.yaml` (`already_installed`, poradí `factory update`) a repo s `.factory/config.yaml`, `.factory/agents.yaml` nebo `adws/adw_sssf_config/` bez manifestu (`existing_config`, poradí `factory onboard`) a nic nezapíše. Ostatní existující soubory přeskočí a vypíše, `--force` je přepíše. Řádky `.gitignore` přidá jen jednou. Nic necommituje.
- Výsledek je platný: po commitu projdou `factory config show` a `factory backlog check`, `factory config items` ukáže všechny položky `synced` a běh tasku s falešným harnessem v takovém repu doběhne.
- Prompty initu nemají pravidlo validace `haifa-validate`.
- Testy (pytest) nad dočasným git repem a dočasným `HAIFA_HOME`: init ze semínka bez knihovny, init z knihovny s upraveným builderem (manifest nese jeho verzi a knihovnu), `--bind builder=codex:gpt-5.5:high`, workflow `scout` přidá agenta scout, druhé spuštění vše přeskočí, `--force` přepíše, `.gitignore` bez duplicit, odmítnutí `already_installed` a `existing_config`, běh s falešným harnessem.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: náhled a commit do base (M8), zjištění testovacího příkazu repa, Azure DevOps v `init`, instalace nástrojů (`gh`, `az`, harnessy), onboarding existující konfigurace (O2, O4), postup instalace ve skillu (HAIFA-S04-T02).

Pevná omezení:
- `init` nikdy nepřepíše soubor bez `--force` a nic necommituje ani nepushuje.
- `init` nezapisuje do knihovny ani do `$HAIFA_HOME`.
- `.factory/` repa HAIFA se nemění.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/55 · náklady $4.58
