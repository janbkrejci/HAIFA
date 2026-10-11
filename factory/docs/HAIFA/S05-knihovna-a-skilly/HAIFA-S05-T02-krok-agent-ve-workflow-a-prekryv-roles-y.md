# HAIFA-S05-T02: Krok `agent:` ve workflow a překryv `roles.yaml`

## Co se změnilo a proč

Když repo mělo vlastní roster (D24) a chtělo pustit krok na jiném agentovi, muselo dřív zkopírovat celý `roles.yaml` včetně všech kódových kroků. Teď na to stačí dvě lehčí cesty:

1. **`agent:` na kroku role ve workflow.** Platí jen pro ten jeden krok:
   ```yaml
   steps:
     - plan
     - build: {agent: scout, harness: codex, model: gpt-5.5}
   ```
   Krok dostane kopii role s jiným agentem (`dataclasses.replace`). Typ výstupu i gates zůstávají z role a samotný registr se nemění. Agent se dá kombinovat s `harness`, `model` a `thinking`.
2. **Překryv `.factory/roles.yaml`.** Soubor **bez** klíče `code_steps` se před validací sloučí s balíčkovým registrem:
   ```yaml
   roles:
     review: {agent: critic}          # existující role: přepíšou se jen uvedená pole
     audit:                           # nová role: povinné agent, output_type, gates, description
       agent: auditor
       output_type: ReviewOutput
       gates: [artifacts_exist]
       description: Audit the change against the security checklist
   ```
   Soubor **s** `code_steps` nahradí registr celý, stejně jako dřív.

## Kde to je

- `aifactory/src/aifactory/workflow/parse.py`: `agent` přibyl do `_ROLE_OPTS`. Metoda `_Parser.agent()` hlásí prázdnou hodnotu nebo hodnotu, která není řetězec, jako `invalid_agent`. `role_step` nahradí `role.agent`. Na kódovém kroku vrací `agent:` chybu `override_on_code_step`.
- `aifactory/src/aifactory/workflow/model.py`: `RoleStep.agent` drží jen explicitní hodnotu z kroku. Efektivního agenta už obsahuje `role.agent`, takže ho osnova (`data.steps[].agent`) ukazuje.
- `aifactory/src/aifactory/workflow/check.py`: když `check_agents` nenajde v rosteru agenta zadaného přes `agent:`, hlásí `unknown_agent` na cestě `steps[N].<step>.agent`. Ostatní kontroly, včetně kontroly přepsání kroku, zůstaly jako dřív. Stejnou kontrolu dělá `factory workflow check` i preflight běhu.
- `aifactory/src/aifactory/engine/role_registry.py` (změny mají značku `# aifactory`):
  - `is_overlay(data)` vrací True, když jde o mapping bez `code_steps`.
  - `merge_overlay(data, base)` slučuje překryv se surovým YAML. Existující role sloučí mělce po polích, nové roli zkontroluje `OVERLAY_REQUIRED` (`missing_key` na `roles.<jméno>.<klíč>`). Přepsání aliasu (např. `planner`) hlásí jako `alias_conflict` na `roles.<alias>` a hláška radí přepsat kanonické jméno. Dál hlásí `missing_roles` a `invalid_role`. `code_steps` převezme z balíčku.
  - `parse_roles(data, base=None)` zavolá na překryv sloučení a výsledek pak projde běžnou validací `_Loader`. Proto mají chyby jako `unknown_key`, `unknown_output_type` nebo konflikt aliasů stejné kódy a cesty jako u plného souboru.
- `aifactory/src/aifactory/engine/defaults/roles.yaml`: přibyl jen komentář, který popisuje překryv.
- `aifactory/src/aifactory/config/loader.py`: `_load_roles` dostal jen docstring. Překryv funguje, protože loader dál používá registr přes `role_registry`.
- `aifactory/src/aifactory/skill/codes.py`: nový kód `missing_key` v seznamu kódů pro roles.
- `aifactory/src/aifactory/skill/skill.md`: `factory --skill` popisuje `agent:` u kroku, jeho kontrolu a překryv i s příkladem.

## Jak to ověřit

```sh
just test && just typecheck && just lint
```

Testy (bez modelu a bez sítě):

- `aifactory/tests/workflow/test_workflow_step_agent.py` (nový):
  - krok `build: {agent: scout}` běží s falešným harnessem na `scout` a vrátí `BuildOutput`;
  - kombinace agenta s přepsáním `harness` a `model`;
  - neznámý agent spadne v preflightu dřív, než proběhne jakékoli volání.
- `aifactory/tests/workflow/test_workflow_parse.py`: `agent:` nahradí agenta role a registr zůstane nedotčený. Pokrývá i `invalid_agent` a `override_on_code_step`.
- `aifactory/tests/workflow/test_workflow_cli.py`: `factory workflow check --json` u neznámého agenta kroku a s překryvem, který přidává roli `audit`.
- `aifactory/tests/engine/test_role_registry.py`:
  - překryv s jednou změněnou a jednou novou rolí;
  - načtení překryvu ze souboru;
  - prázdný překryv dá balíčkový registr;
  - plný soubor nahrazuje registr jako dřív;
  - parametrizované neplatné překryvy (`missing_key`, `unknown_key`, `alias_conflict`, `unknown_output_type`, `missing_roles`, `invalid_role`).
- `aifactory/tests/config/test_config_loader.py`: překryv v `.factory/roles.yaml` se sloučí při načtení konfigurace worktree.

Ruční kontrola: dejte do repa `.factory/roles.yaml` jen s `roles:` a spusťte `factory workflow check FILE --json`. Výstup ukáže `data.roles == ".factory/roles.yaml"` a u každého kroku jeho agenta.
