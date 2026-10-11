# Cesty výstupů tasku v promptech agentů (`{{spec_path}}`, `{{doc_path}}`)

## Proč

Prompty planneru a documenteru v šabloně sandboxu kázaly agentovi pojmenovat výstup `specs/<adw_id>_<slug>.md` resp. `app_docs/<adw_id>_<slug>.md`. Hlídač zápisů tasku ale povoluje jen `specs/<task-id>-<slug>.md` a `app_docs/<task-id>-<slug>.md`, takže každý agentní scénář validace proti GitHubu skončil `run_failed: planner changed paths outside its task run`. Lokální validace to neodhalila, protože falešný harness psal na cestu podle vlastního pravidla (`TASK_STEMS`) a prompt nečetl.

Hlídač zápisů ani pojmenování z úkolu 2.9 se nemění. Proměnné `spec_path` a `doc_path` běh už předával (`aifactory/src/aifactory/run/task.py`, beze změny). Tato změna je jen začala v promptech používat.

## Co se změnilo

**Prompty šablony** (`aifactory/validation/template/.factory/prompts/`)
- `planner/user.md`, `planner/system.md`: kopie plánu jde přesně do `{{spec_path}}`. Odstraněno vybírání názvu podle `<adw_id>`, výpis `specs/` i přípony `_v2`/`_v3`. Pokud soubor existuje, přepíše se. `artifacts` v reportu obsahuje `{{spec_path}}`.
- `documenter/user.md`, `documenter/system.md`: totéž pro write-up a `{{doc_path}}`, včetně `document_path` v reportu.

**Falešný harness** (`aifactory/validation/fake.py`, `fake_scripts.py`)
- Nový zástupný token `OUTPUT = "@output"`. Pokud se objeví v cestě editu nebo kdekoli v obálce, `FakeHarness.run` ho nahradí cestou z vykresleného promptu.
- `output_path(prompt, adw_id)` vrací první relativní `.md` cestu v backticku ze sekce `## Task`. Přeskakuje cesty pod `<context_handoff_dir>`, absolutní cesty a cesty s mezerou nebo uvozovkou. Placeholder `<adw_id>` doplní id session (odvozené z `request.session_dir`, dvě úrovně nad ním). Ostatní placeholdery nahradí jejich názvem v kebab-case (`<slug>` → `slug`), tedy tak, jak by prompt doslova vykonal agent.
- Záznam volání v `*.calls.jsonl` má nově pole `output`.
- `_plan` a `_document` ve `fake_scripts.py` píšou na `OUTPUT` místo `specs/`/`app_docs/{TASK_STEMS[...]}.md`. Nesoulad mezi promptem a hlídačem proto lokální validace teď odhalí.

**Ostatní**
- `aifactory/src/aifactory/engine/data_types.py`: komentář u `DocumentOutput.document_path` uvádí příklad `app_docs/<task-id>-<slug>.md`.

## Testy (bez volání modelu)

- `tests/validation/test_validation_prompt_paths.py` (nový) spouští `validation.worker task run M01-S01-T01` nad lokálním sandboxem s falešným harnessem. Skutečná CLI nahrazuje tripwire. Test je parametrizovaný:
  - `adw_id`: `{{spec_path}}` v promptu planneru se nahradí `specs/<adw_id>_<slug>.md` a změna se commitne. Očekává se exit 1, `run_failed`, „outside its task run“ a že documenter se nespustí.
  - `spec_path`: očekává se `ok` a výstupy `specs/M01-S01-T01-clamp.md` a `app_docs/M01-S01-T01-clamp.md`.
  - Bez `just` na PATH se test přeskočí.
- `test_validation_template.py::test_no_prompt_names_outputs_by_adw_id` hlídá, že `<adw_id>_` není v žádném souboru pod `aifactory/src` ani `aifactory/validation` (kromě `validation/results`) a `<adw_id>` v žádném promptu šablony. Dále kontroluje, že planner používá `{{spec_path}}` a documenter `{{doc_path}}`.
- `test_validation_unit.py`: unit testy pro `output_path` (první cesta, doplnění placeholderů, chyby bez `## Task` nebo bez cesty) a pro to, že `FakeHarness` zapíše soubor na cestu z promptu.
- `tests/run/test_task_run.py` a `run_repo.py`: testovací prompt obsahuje `doc={{doc_path}}` a ověřuje se, že obě proměnné jsou ve vykresleném promptu nahrazené.
- `test_validation_f2.py`: planner v F2 skriptu píše na `fake.OUTPUT`.

## Ověření

```
just test && just typecheck && just lint
just validate --remote local     # žádný scénář nesmí skončit failed
```

Plán je v `specs/cdb67cc3_task-output-prompt-paths_v2.md`.
