# Interpret YAML workflow v `aifactory` + nová sémantika `until`

## Co se změnilo

Interpret YAML workflow z prototypu je nově v balíčku `aifactory.workflow`. Workflow je *data*: seznam kroků, kde krok je role z registru rolí (`.factory/roles.yaml`, jinak balený default), nebo deterministický kódový krok (`test`, `quality`, `commit`, `changes`, `command`). K tomu patří smyčky `repeat` s `max`/`until`, podmínky `when` na krocích a kritérium `accept` na úrovni workflow.

Přibyly tři věci, na kterých záleží nejvíc:

1. **Nová sémantika `until`.** Podmínka se vyhodnocuje po každém kroku těla, který opravdu proběhl, a smyčka končí hned, jak platí. V posledním kole (`i == max`) smyčka navíc skončí hned za tím prvkem těla, jehož výsledek `until` čte (`Repeat.until_tail`, počítá se při parsování). Kroky za ním by totiž opravovaly práci, kterou už nic neověří.
   - `repeat: {max: 3, until: test.passed}` s tělem `[test, fix]`, testy F,F,F → `test_1, fix_1, test_2, fix_2, test_3`. **Žádný `fix_3`.**
   - `repeat: {max: 2, until: review.approved}` s tělem `[review, revise]`, dvakrát zamítnuto → `review_1, revise_1, review_2`. **Žádný `revise_2`.**
   - Když test projde hned napoprvé, `fix` se nespustí.
   - Když `until` neodkazuje na žádný krok v těle nebo chybí, poslední kolo proběhne celé.
   - Jde o vědomou odchylku od `adw_simple_sdlc.py`, který po posledním neúspěšném testu ještě spustí fix. Je to zapsané v docstringu `interpreter.py`.
2. **Kódový krok `command`.** Spustí `argv` z workflow. Výsledek je `passed` podle exit kódu: 0 znamená úspěch, timeout vrací 124, chybějící binárka 127. Výchozí `timeout` je 600 s. Krok povinně potřebuje `id` a podmínky čtou jeho výsledek pod tímto `id` (např. `dotnet_test.passed`).
3. **CLI `factory workflow check <FILE> [--json] [--roles PATH] [--agents PATH]`.** Ověří workflow proti registru rolí a proti rosteru agentů. Nic se nespouští.

Podmínky parsuje malý rekurzivní parser (`and`/`or`/`not`, závorky, `== != < <= > >=`, literály `true/false/null`, čísla a řetězce, odkazy `<step>.<field>`). Vyhodnocují se procházením stromu, nikdy ne jako Python. Krok, který neproběhl, čte `None` (`<step>.ran` → `False`).

## Soubory

| Soubor | Obsah |
|---|---|
| `aifactory/src/aifactory/workflow/model.py` | `RoleStep`, `CodeStep`, `Repeat` (vč. `until_tail`), `Workflow`, `WorkflowError`, `walk` |
| `aifactory/src/aifactory/workflow/conditions.py` | parser a vyhodnocení podmínek (`parse_condition`, `evaluate`, `truthy`, `refs`) |
| `aifactory/src/aifactory/workflow/parse.py` | `load_workflow` / `parse_workflow`: validace proti `RoleRegistry`, všechny chyby najednou; `outline` |
| `aifactory/src/aifactory/workflow/check.py` | `check_workflow`, `check_agents`, `CheckResult.to_json()` |
| `aifactory/src/aifactory/workflow/interpreter.py` | `run_workflow`, `preflight`, `CodeRunner` (protokol), `EngineCodeRunner`, smyčka `_Interpreter.loop` |
| `aifactory/src/aifactory/workflow/__init__.py` | re-export veřejného API |
| `aifactory/src/aifactory/cli.py` | podpříkaz `workflow check` |
| `aifactory/tests/workflow/*.py`, `aifactory/tests/test_smoke.py` | testy s falešnými harnessy a `FakeCodeRunner` (`workflow_fakes.py`) |
| `specs/6c1e6fb5_workflow-interpreter-until.md` | plán a rozhodnutí o `until` |

Validace v `parse.py` hlásí mimo jiné tyto chyby: neznámý krok, klíč, harness nebo `thinking`, špatnou podmínku, odkaz na neexistující krok nebo pole (`unknown_ref`/`unknown_field`), `repeat` bez `max` (`missing_max`), `command` bez `id`/`argv` a override (`harness`/`model`/`thinking`) na kódovém kroku.

Role kroky běží přes `run.phase`/`ph.call`. Override harness/model/thinking se uplatní jen pro danou fázi (`step_override`). `preflight` před během ověří každou kombinaci (agent, harness, model, thinking).

## Použití

```yaml
name: demo
description: Build, then repair the suite until it is green
steps:
  - build
  - repeat: {max: 2, until: suite.passed}
    steps:
      - command: {id: suite, argv: [dotnet, test]}
      - fix
  - commit: {when: suite.passed}
accept: suite.passed
```

```sh
factory workflow check wf.yaml          # "OK: demo (N steps)" nebo seznam chyb "<file>:<path>: <code>: <msg>"
factory workflow check wf.yaml --json   # {ok, path, workflow, errors, steps, roles, agents, warnings}
```

- Exit kódy: `0` znamená OK, `1` znamená, že workflow má chyby, `2` znamená, že nejde načíst registr rolí nebo roster.
- Uvnitř factory repa (existuje `.factory/config.yaml`) a bez flagů se berou `.factory/roles.yaml` (jinak balené defaulty) a `.factory/agents.yaml`.
- Mimo factory repo se agenti nekontrolují. Na stderr se objeví `warning: agents not checked: no .factory/agents.yaml`.
- `factory workflow` bez podpříkazu vypíše nápovědu a skončí kódem 0.

Z Pythonu: `run_workflow(load_workflow(path, roles), prompt, cfg, code=...)` vrací `WorkflowRun` s poli `exit_code`, `accepted`, `phases`, `results`, `envelopes` a `records`.

## Ověření

```sh
just test && just typecheck && just lint
```

Hlavní testy:
- `tests/workflow/test_workflow_loops.py`: obě smyčky, vyčerpání `max` bez `fix_3`/`revise_2`, `when` na kroku i na celém `repeat`, `until` bez odkazu do těla, smyčka bez `until`.
- `test_workflow_command.py`: exit kódy 0/3/127 a opravná smyčka se skutečným příkazem.
- `test_workflow_cli.py`, `test_workflow_parse.py`, `test_workflow_conditions.py`, `test_workflow_harness_mix.py`.

## Poznámky

- `EngineCodeRunner.command` volá privátní `engine_quality._run`.
- CLI zatím umí jen `check`. Spouštění workflow z CLI tahle změna nepřidává.
