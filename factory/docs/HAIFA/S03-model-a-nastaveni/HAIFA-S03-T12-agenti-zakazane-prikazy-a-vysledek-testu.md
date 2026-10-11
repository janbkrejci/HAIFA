# HAIFA-S03-T12: Agenti: zakázané příkazy a výsledek testu pro review

## Co se změnilo a proč
Builder a reviewer spouštěli celou testovací sadu, i když jim to prompt zakazoval. Fáze test ji pak pustila znovu. Reviewer navíc výsledek fáze test nedostal, protože `previous_envelope` je jen jedna obálka. Proto si testy pouštěl sám.

Nově platí:
- Agent může mít v `.factory/agents.yaml` seznam `disallowed_commands`. Harness claude ho vynutí přes `--disallowedTools`. Harness, který zákaz neumí (codex, pi), se nahlásí při `factory check` i na začátku běhu.
- Role krok workflow může dostat víc vstupů. Každá role dostane proměnnou šablony `{{test_result}}` s výsledkem posledního kroku `test`.
- Výchozí prompt revieweru říká, že fáze test už sadu na stejném kódu pustila, a výsledek mu ukazuje.

## Konfigurace
```yaml
# .factory/agents.yaml
defaults:
  harness: claude
agents:
  - name: builder
    disallowed_commands: [just check, "just check *", just test, "just test *", just e2e, just web-test, pytest]
  - name: reviewer
    writes: []
    disallowed_commands: [just check, just check-scoped, just test, just e2e, just web-test, pytest]
```
Každá položka je vzor Bash příkazu ve tvaru, jakému rozumí claude. `pytest` zakáže jen holé `pytest`, tedy běh bez cesty. `pytest tests/x.py` projde. `just test *` zakáže `just test` s libovolnými argumenty. Položka, která už jmenuje nástroj (`Bash(...)`), projde beze změny. Klíč se dědí z `defaults` stejně jako `tools` a `writes`.

Workflow může vstupy pojmenovat i explicitně. `input:` jako seznam funguje beze změny (`previous_envelope`). Nově může mít `input:` i podobu mapy:
```yaml
- review:
    input:
      previous_envelope: [build, fix, revise]
      test_result: test        # přepíše výchozí test_result
      suite: [test]            # vlastní proměnná {{suite}}
```
Názvy `prompt` a `context_handoff_dir` jsou rezervované.

`{{test_result}}` (i proměnná z mapy, která ukazuje na krok test, quality nebo command) je JSON:
```json
{"step": "test", "phase": "test_2", "passed": true, "command": "just check-scoped",
 "log": "/…/test.log", "failures": 0, "code_changed_since": false}
```
`code_changed_since` je true, když po testu běžel agent, který mění kód (build, fix nebo revise). Před prvním testem má proměnná hodnotu `(none)`.

## Kde to je
- `aifactory/src/aifactory/engine/data_types.py`: přibylo `AgentConfig.disallowed_commands`, `ConfigDefaults.disallowed_commands`, `PiRequest.disallowed_commands` a `AgentCall.variables` (další proměnné šablony jednoho volání).
- `aifactory/src/aifactory/engine/agents.py`: předá `disallowed_commands` do requestu a do trace (`agent_start`). Do šablon vloží `call.variables`, vlastní proměnné enginu mají přednost.
- `aifactory/src/aifactory/engine/agent_cc.py`: obsahuje `SUPPORTS_DISALLOWED_COMMANDS = True` a funkci `disallowed_tools()`. Příkaz dostane `--disallowedTools "Bash(…)" …` a hned za ním následuje volba (`--strict-mcp-config` nebo `--mcp-config`), protože flag je variadický a jinak by spolkl prompt.
- `aifactory/src/aifactory/engine/agent_pi.py` a `aifactory/src/aifactory/harness/codex.py` mají `SUPPORTS_DISALLOWED_COMMANDS = False`.
- `aifactory/src/aifactory/harness/__init__.py`: funkce `supports_disallowed_commands(name)` a `unenforced_disallowed(agent)`.
- `aifactory/src/aifactory/harness/config.py`: `disallowed_commands` je v `INHERITED`.
- `aifactory/src/aifactory/check/repo_rules.py`: pravidlo `disallowed commands` vydá varování `disallowed_commands_unenforced`. Kód je doplněný v `skill/codes.py`.
- `aifactory/src/aifactory/workflow/parse.py` a `model.py`: `input:` jako mapa a `RoleStep.variables`.
- `aifactory/src/aifactory/workflow/interpreter.py`: `test_result` a proměnné vstupů. `unenforced_restrictions()` respektuje i override harnessu v kroku. Varování se zapíšou do fáze `request` (konzole a trace) a do `WorkflowRun.warnings`.
- `aifactory/src/aifactory/seed/agents/reviewer/user.md`: nová sekce `test_result`. Říká, že fáze test už sadu na stejném kódu pustila, a ukazuje výsledek. Systémové prompty builderu a revieweru v seedu jsou teď shodné s `.factory/prompts` (zakázané příkazy, žádné testy v revieweru).
- `aifactory/tests/library/test_library_seed.py`: `PENDING_SEED_BLOCKS` povolí sekci `test_result`, dokud ji operátor nepřenese do `.factory/prompts/reviewer/user.md`. Ostatní text se musí shodovat. Kontrola verze revieweru se do té doby přeskočí.

## Pro operátora
`.factory/` je chráněný, a proto se v tomto tasku nemění. Aby to HAIFA používala na sobě, je potřeba:
1. doplnit `disallowed_commands` builderu a revieweru v `.factory/agents.yaml`,
2. přidat do `.factory/prompts/reviewer/user.md` sekci `{{test_result}}` (podle seedu).

Workflow `build-test-review` měnit nemusíte, protože `test_result` dostane review automaticky.

## Jak ověřit
`just test`, `just typecheck`, `just lint`. Relevantní testy:
- `aifactory/tests/harness/test_harness_disallowed.py`: zákaz se dostane do příkazu claude, codex a pi se nahlásí, dědění z `defaults` a pravidlo `factory check`.
- `aifactory/tests/workflow/test_workflow_inputs.py`: review dostane obálku fixu i výsledek posledního testu (příkaz a log), testuje se `code_changed_since`, `(none)`, mapa `input:` včetně chyb parsování a varování na začátku běhu při `harness: codex` v kroku.
