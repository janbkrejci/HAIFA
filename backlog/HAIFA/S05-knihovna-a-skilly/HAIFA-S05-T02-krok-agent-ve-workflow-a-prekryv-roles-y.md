---
id: HAIFA-S05-T02
title: "Krok `agent:` ve workflow a překryv `roles.yaml`"
status: done
depends_on: []
---

## Zadání
Umožni repu s vlastním rosterem (D24) použít jiného agenta bez kompletního `roles.yaml`. Krok role ve workflow přijme `agent:` a `.factory/roles.yaml` bez `code_steps` se sloučí přes balíčkový registr. Dnes repo s novým jménem agenta musí zkopírovat celý registr včetně všech kódových kroků.

Where: `aifactory/src/aifactory/workflow/` (`parse.py`, `check.py`, `model.py`), `aifactory/src/aifactory/engine/role_registry.py`, `aifactory/src/aifactory/engine/defaults/roles.yaml`, `aifactory/src/aifactory/config/loader.py` (`_load_roles`), `aifactory/src/aifactory/skill/skill.md`, testy v `aifactory/tests/workflow/` a `aifactory/tests/engine/test_role_registry.py`.

Done means:
- Krok role přijme `agent: JMÉNO` vedle `harness`, `model` a `thinking`. Krok dostane kopii role s tímto agentem (typ výstupu a gates zůstanou). `factory workflow check` a preflight ověří, že agent je v rosteru a přijme přepsání kroku. Osnova workflow ukáže agenta kroku.
- `.factory/roles.yaml` bez klíče `code_steps` je překryv: existující krok přepíše uvedená pole, nový krok potřebuje `agent`, `output_type`, `gates` a `description` a výsledek projde `parse_roles`. Soubor s `code_steps` nahradí registr jako dnes.
- Chyby překryvu mají cestu a kód jako dnes (`unknown_key`, `alias_conflict`, ...).
- `factory --skill` popisuje `agent:` u kroku a překryv.
- Testy (pytest): krok s `agent:` běží s falešným harnessem na zvoleném agentovi, neznámý agent v kroku, překryv s jedním změněným a jedním novým krokem, plný soubor beze změny chování, neplatný překryv.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: role jako položky knihovny, editor rolí, nové typy výstupů a gates.

Pevná omezení:
- Každá změna logiky v `aifactory/src/aifactory/engine/` má značku `# aifactory`.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/14 · náklady $2.33
