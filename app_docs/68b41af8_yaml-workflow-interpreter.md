# Interpret YAML workflow a registr rolí

## Co se změnilo a proč

Workflow už nemusí být Python skript. Popisuje se jako data v YAML a prototyp ho načte, zvaliduje a spustí nad vendorovaným enginem (`adw_modules`). `vendor/` zůstal beze změny: engine se jen importuje přes `haifa_proto.engine`.

- **Registr rolí jako data.** `prototype/src/haifa_proto/defaults/roles.yaml` a `prototype/src/haifa_proto/roles.py` mapují jméno kroku na agenta, typ výstupu, gates a popis fáze. `output_type` se hledá podle jména v `adw_modules.data_types` (musí dědit z `EnvelopeBase`) a gates v `adw_modules.gates`. Obsah odpovídá vendorovanému `adw_modules/roles.py`, včetně aliasů (`planner` = `plan` atd.). Navíc je tu role `revise`, kterou `adw_simple_sdlc.py` zapisuje přímo v kódu. Sekce `code_steps` definuje deterministické kroky `test`, `quality`, `commit`, `changes` a `command`. Registr kontroluje popisy fází podle pravidla 7: používá k tomu enginový validátor `PhaseParams`, takže kontrola při načtení a za běhu se nemůže rozejít.
- **Model workflow** (`prototype/src/haifa_proto/workflow.py`). Obsahuje `name`, `description`, `steps` a `accept`. Krok je buď role, nebo kódový krok, zapsaný jako holé jméno nebo jako `{jméno: {volby}}`:
  - role mají volby `harness` (`claude`/`codex`/`pi`), `model`, `thinking` (`off`…`max`), `when`, `id`, `description` a `input` (ze kterých kroků se bere předchozí envelope),
  - kódové kroky mají volby `when`, `id` a `description`. `command` navíc vyžaduje `id` a `argv` a volitelně bere `timeout`. Přepis harness/model/thinking u kódového kroku je chyba,
  - `repeat: {max, until, when}` se `steps`. `until` se vyhodnotí po každém kroku těla, takže smyčka `test_1 → fix_1 → test_2` skončí hned, jakmile `test_2` projde.
- **Podmínky** mají vlastní tokenizér a rekurzivní parser. Podporují `and`/`or`/`not`, závorky, `== != < <= > >=` a literály (čísla, řetězce, `true`/`false`/`null`). Reference má vždy tvar `<krok>.<pole>`. Krok, který neběžel, vrací `None`, jeho `ran` vrací `False`. Nikde se nepoužívá `eval`, což hlídá i test.
- **Validace při načtení.** Všechny chyby se nahlásí najednou jako `WorkflowError.issues` s kódem a cestou (např. `steps[0].plan.harness`). Hlídají se: neznámý krok/harness/thinking, `repeat` bez `max` nebo s `max < 1`, syntaxe podmínek, reference na neexistující krok nebo pole (`unknown_ref`, `unknown_field`), neznámé klíče, kolize `id` a popisy, které jen opakují jméno. Pole, která smí podmínka číst, odvozuje `RoleRegistry.result_fields` z typu výstupu (`VerifyOutput`, `ChangesOutput`, pro `commit` `sha/committed/message`) plus `ran`.
- **Běh** (`run_workflow`). Nejprve `preflight` zkontroluje každou kombinaci agent × harness × model × thinking přes `agents.validate`, takže špatný model spadne dřív, než cokoli poběží. Pak se zapíše fáze `request` a kroky jdou přes enginové `run.phase` / `ph.call`. `apply_override` dočasně přepíše `coding_agent`/`model`/`thinking` agenta (u jiného harnessu než `pi` vymaže `harness_engineering`) a po kroku vše vrátí zpět. Fáze v opakování dostávají přípony `_1`, `_2`. `commit` bere `commit_message` posledního envelope, který ho má. Kódové kroky běží přes `EngineCodeRunner` (`quality`, `git_helper`, `changes`), testy ho nahrazují falešným. Výsledek `accept` určí `accepted` a exit kód.
- **CLI:** `haifa-proto workflow check <soubor> [--roles <roles.yaml>] [--json]` (`prototype/src/haifa_proto/cli.py`). Pokud je workflow v pořádku, vypíše `OK: <name> (N steps)`, jinak `soubor:cesta: kód: zpráva` pro každou chybu. S `--json` vrací `{ok, path, workflow, errors, steps}`, kde `steps` je plochý přehled kroků včetně agenta a přepisů. Při chybě je exit kód 1.

## Výchozí workflow

Soubory jsou v `prototype/src/haifa_proto/defaults/workflows/`. Každý je YAML podobou jednoho vendorovaného ADW: `plan.yaml`, `scout.yaml`, `plan-build.yaml`, `plan-build-test.yaml` (oprava až 3×, `commit` jen při zelených testech), `document.yaml` a `simple-sdlc.yaml`.

`simple-sdlc.yaml` vyjadřuje `adw_simple_sdlc.py`: plan → commit_plan → build → smyčka test/fix (max 3) → smyčka review/revise (max 2, review čte `input: [build, fix, revise]`) → `retest` (když `revise.ran and review.approved`) → commit_build → changes → document → commit_docs. Všechny kroky za smyčkami mají podmínku `test.passed and review.approved`. **Známý rozdíl** je popsaný v komentáři souboru: když reviewer zamítne i v poslední iteraci, YAML ještě spustí `revise_2`, kdežto Python verze skončí dřív. Na výsledku to nic nemění.

## Ověření

```bash
cd prototype
uv run pytest tests/test_roles.py tests/test_conditions.py tests/test_workflow_load.py \
  tests/test_workflow_simple_sdlc.py tests/test_workflow_harness_mix.py tests/test_cli_workflow.py tests/test_cli.py
uv run haifa-proto workflow check src/haifa_proto/defaults/workflows/simple-sdlc.yaml
uv run haifa-proto workflow check tests/fixtures/workflows/broken.yaml --json   # exit 1, čtyři druhy chyb
```

Testy nevolají model. `tests/workflow_fakes.py` nahradí harnessy v `agents.INTERFACES` objektem `FakeHarness`, který vrací naskriptované envelopes a zaznamenává harness, model, thinking a prompt. `FakeCodeRunner` simuluje výsledky testů a commity. Skutečný harness v testu vyhodí výjimku. Fixture `engine_env` v `tests/conftest.py` připraví dočasný git repozitář a roster falešných agentů.

- `test_workflow_simple_sdlc.py` pokrývá tři scénáře ze zadání (vše projde; testy selžou jednou a `fix_1` je spraví; review jednou zamítne a `revise_1` → `review_2` → `retest` projde) a navíc scénář, kdy testy nikdy neprojdou (exit 1, zůstane jen commit plánu). Kontroluje přesné pořadí fází `(name, kind, owner)` a zprávy commitů.
- `test_workflow_harness_mix.py` s fixture `mixed-harness.yaml` (plan na `claude`, build na `codex`, review na `pi`) ověřuje, že každý krok dostal svůj harness a model a že build bez přepisu `thinking` zdědil výchozí hodnotu agenta. Dál ověřuje, že `previous` předaný dalšímu harnessu je přesně JSON předchozího envelope, že se agenti po běhu vrátí do původního stavu a že preflight odmítne neplatný model dřív, než proběhne jakékoli volání.
- `test_workflow_load.py` načte všechny výchozí workflow a projde katalog neplatných vstupů. `test_roles.py` porovná YAML registr s vendorovým `ROLES` (stejný agent, identické třídy a gate funkce, popisy i retries).

Návrh k implementaci je v `specs/68b41af8_yaml-workflow-interpreter.md`.
