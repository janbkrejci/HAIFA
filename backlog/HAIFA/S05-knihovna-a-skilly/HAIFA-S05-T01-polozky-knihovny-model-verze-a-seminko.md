---
id: HAIFA-S05-T01
title: "Položky knihovny: model, verze a semínko"
status: done
depends_on: []
---

## Zadání
Přidej model položek knihovny HAIFA (agent, workflow, skill, rozšíření pi), jejich verzi jako sha256 obsahu a semínko knihovny v balíčku. Je to základ hybridní konfigurace (`docs/decisions.md`, Konfigurace jako hybrid): stejný obsah musí dát stejnou verzi v knihovně i v kopii `.factory/` repa. Dnes balíček nemá agenty ani prompty a balíčkové workflow `scout` nemá agenta.

Where: nový balíček `aifactory/src/aifactory/library/`, nová data `aifactory/src/aifactory/seed/`, `aifactory/src/aifactory/defaults/workflows/`, `aifactory/src/aifactory/config/loader.py`, `aifactory/src/aifactory/workflow/` (`parse.py`, `check.py`), `aifactory/src/aifactory/engine/role_registry.py`, zdroje semínka `.factory/agents.yaml` a `.factory/prompts/` repa HAIFA a `vendor/sssf/templates/prompt_engineering/scout/`, testy v nové složce `aifactory/tests/library/`.

Done means:
- Typy `agent`, `workflow`, `skill` a `extension`. Jméno odpovídá `[a-z0-9][a-z0-9-]{0,47}`. Položka se načte z rozložení knihovny (`agents/<jméno>/{agent.yaml,system.md,user.md}`, `workflows/<jméno>.yaml`, `skills/<jméno>/`, `extensions/<jméno>/`) i z kopie v repu (purpose z `.factory/agents.yaml`, prompty z `.factory/prompts/<slot>/`, `.factory/workflows/<jméno>.yaml`, `.factory/skills/<jméno>/`, `.factory/extensions/<jméno>/`).
- Verze je `sha256:<hex>` kanonického obsahu: agent = purpose, `system.md` a `user.md` (každá část s délkou), workflow = bajty souboru, skill a rozšíření = seřazený seznam (relativní cesta, spustitelnost, bajty). `defaults` agenta do verze nepatří. Stejný obsah dá stejnou verzi v obou rozloženích a pod jakýmkoli jménem.
- `agent.yaml` má `purpose` a `defaults` (`harness`, `model`, `thinking`, `tools`, `writes`, `color`, `skills`, `extensions`). `writes` smí obsahovat `$specs_dir/` a `$docs_dir/` a pomocná funkce je nahradí hodnotami z `ProjectSettings`.
- Validace vrátí všechny problémy najednou: `SKILL.md` s YAML front matter, `name` rovné složce a neprázdné `description`, rozšíření se vstupním souborem `<jméno>.ts`, workflow jako mapování, které projde `parse_workflow` proti balíčkovému registru rolí, symlink odmítnut, nejvýš 2 MB a 200 souborů na položku.
- Semínko `aifactory/src/aifactory/seed/agents/` má planner, builder, reviewer a documenter: prompty bajtově stejné jako `.factory/prompts/` repa HAIFA, purpose a výchozí vazby jako `.factory/agents.yaml` (claude, `claude-opus-5-5`, medium), `writes` planneru `$specs_dir/`, documenteru `$docs_dir/`, revieweru `[]`. Scout má prompty ze `vendor/sssf/templates/prompt_engineering/scout/` upravené jako planner HAIFA: `<context_handoff_dir>` je mimo repo, žádný git, žádná jména podle `adw_id`, `writes: []`. Workflow semínka jsou `aifactory/src/aifactory/defaults/workflows/*.yaml` a nekopírují se.
- Testy (pytest): zlaté verze pro každý typ, stejná verze z knihovny i z kopie v repu, změna jednoho bajtu nebo spustitelnosti změní verzi, `defaults` verzi nemění, každá chyba validace, prompty semínka se rovnají `.factory/prompts/` HAIFA, dočasné repo s rosterem ze semínka (všech 5 agentů) projde `load_config` a preflight každého balíčkového workflow včetně `scout`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: knihovna v domově a git, CLI, manifest repa, skilly v bězích, změna `.factory/` HAIFA.

Pevná omezení:
- `.factory/` repa HAIFA se nemění.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/8 · náklady $3.97
