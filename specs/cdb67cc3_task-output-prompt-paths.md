# Plán: cesty výstupů tasku v promptech agentů (`{{spec_path}}`, `{{doc_path}}`)

## Problém

Validace proti GitHubu selhává ve všech scénářích s agentem: prompt planneru v šabloně
sandboxu (`aifactory/validation/template/.factory/prompts/planner/user.md`) říká
„zapiš spec jako `specs/<adw_id>_<slug>.md`“, ale hlídač zápisů tasku
(`aifactory/src/aifactory/run/scope.py`, `guard.py`) povoluje jen
`<specs_dir>/<task-id>-<slug>.md` a `<docs_dir>/<task-id>-<slug>.md`. Běh končí
`run_failed: planner changed paths outside its task run`. Stejná chyba je v promptu
documenteru (`app_docs/<adw_id>_<slug>.md`).

Lokální validace to neodhalila, protože falešný harness (`aifactory/validation/fake_scripts.py`)
píše na cestu `specs/{TASK_STEMS[task_id]}.md` podle vlastního pravidla a prompt vůbec nečte.

## Co už existuje (neměnit, jen ověřit)

- `aifactory/src/aifactory/run/task.py` (~ř. 472) už předává běhu proměnné promptu:
  `task_id`, `spec_path` (= `outputs.spec`), `doc_path` (= `outputs.doc`), `workdir`
  (+ `rebase_onto` u resolve). `engine/agents.py::execute` je vykreslí do system i user
  promptu (`prompts.render`), vlastní proměnné enginu mají přednost.
- `tests/engine/test_task_run_hooks.py::test_prompt_variables_are_rendered` ověřuje vykreslení.
- Hlídač zápisů a pojmenování `<task-id>-<slug>.md` z 2.9 se **nemění** (out of scope).

## Změny

### 1. Běh předává cesty (ověřit + test)

- `aifactory/src/aifactory/run/task.py`: kód už `spec_path` a `doc_path` posílá. Nic neměnit,
  pokud to neodhalí test níže.
- Přidat/rozšířit test v `aifactory/tests/run/` (vzor: `tests/run/run_repo.py`, který už má
  prompt `spec={{spec_path}}`): po `task run` přečíst uložený vykreslený prompt agenta
  (`<data_dir>/sessions/<run_id>/<agent>/prompts/user.md`) a ověřit, že obsahuje přesně
  `outputs.spec` i `outputs.doc` (tj. `specs/<task-id>-<slug>.md` a `app_docs/<task-id>-<slug>.md`)
  a žádný nevykreslený `{{spec_path}}` / `{{doc_path}}`. Pokud existující test v `tests/run/`
  už `spec_path` ověřuje, rozšiř ho o `doc_path` místo nového souboru. Pokud `run_repo.py`
  prompt nemá `doc={{doc_path}}`, doplň ho tam.

### 2. Prompty šablony sandboxu

Soubory:
- `aifactory/validation/template/.factory/prompts/planner/user.md`
- `aifactory/validation/template/.factory/prompts/documenter/user.md`
- zkontroluj i `system.md` obou a prompty `builder`/`reviewer` (grep na `adw_id`); další
  výskyty `<adw_id>_` přepiš stejně.

Planner — krok 2 nahradit (zachovej styl a zbytek souboru):

```
2. Copy that file into the repo as `{{spec_path}}`. The task run named it and allows only this path for the plan; do not pick another name, do not add a suffix. If the file already exists (an earlier run of this task), replace its content.
   **Copy it, do not retype it.** One bash call does the whole step:
   `mkdir -p "$(dirname "{{spec_path}}")" && cp "<context_handoff_dir>/plan.md" "{{spec_path}}"`
   ...(ponech odstavec o tom, proč nepsat podruhé přes write)
3. Emit your `Report` JSON, declaring BOTH paths in `artifacts`.
```

Report JSON: `"artifacts": ["<context_handoff_dir>/plan.md", "{{spec_path}}"]`; závěrečnou
větu změň na „The `artifacts` entry in the repo is exactly `{{spec_path}}`.“ Odstraň odstavce
o listování `specs/`, `<adw_id>`, `_v2`/`_v3`.

Documenter — obdobně krok 3: `Copy that file into the repo as `{{doc_path}}`...`, cp do
`"{{doc_path}}"`, Report: `"document_path": "{{doc_path}}"`,
`"artifacts": ["<context_handoff_dir>/document.md", "{{doc_path}}"]`. Odstraň `<adw_id>`
a `_v2` pravidla.

Důležité pro falešný harness (bod 4): v sekci `## Task` musí být **první** backtickem
ohraničená relativní cesta končící `.md` (mimo cesty začínající `<context_handoff_dir>` nebo `/`)
právě `{{spec_path}}` resp. `{{doc_path}}`. `<context_handoff_dir>/plan.md` smí být před ní
(je vyloučena). Sentinel řádek na konci (`sandbox.materialize`) nevadí.

### 3. Ostatní výskyty `<adw_id>_` v `aifactory/`

- `aifactory/src/aifactory/engine/data_types.py:126` komentář
  `# the doc in the repo, e.g. app_docs/<adw_id>_<slug>.md` → `e.g. app_docs/<task-id>-<slug>.md`.
- `grep -rn "<adw_id>_" aifactory --exclude-dir=__pycache__ --exclude-dir=.venv` musí po změně
  najít výskyty jen v `aifactory/tests/` (testy smí tento literál obsahovat).
- Mimo `aifactory/` (`adws/adw_data/prompt_engineering/`, `vendor/`, `prototype/`) **neměnit**.

### 4. Falešný harness čte cestu výstupu z vykresleného promptu

`aifactory/validation/fake.py`:

- Nová konstanta `OUTPUT = "@output"` a veřejná funkce
  `output_path(prompt: str, adw_id: str) -> str`:
  1. Vezme text za posledním řádkem přesně `## Task` (když chybí → `ValueError`).
  2. Najde backtick spany `` `([^`\n]+)` `` v pořadí; vezme první, který končí `.md`, obsahuje
     `/`, neobsahuje mezeru ani `"`, nezačíná `/`, `.` ani `<context_handoff_dir>`.
     Žádný → `ValueError("validation fake: no output path in the prompt")`.
  3. Dosadí zástupné symboly tak, jak by to udělal agent: `<adw_id>` → `adw_id`,
     jakýkoli jiný `<name>` → `name` převedené na kebab-case (`re.sub(r"[^a-z0-9]+", "-", ...)`),
     tj. `specs/<adw_id>_<slug>.md` → `specs/<adw_id-hodnota>_slug.md`.
  (V docstringu nepiš literál `<adw_id>_` — hlídá to test z bodu 5; napiš např.
  „a placeholder such as <adw_id> is filled in“.)
- `FakeHarness.run`: `adw_id = Path(request.session_dir).parent.parent.name`
  (session_dir = `.../sessions/<adw_id>/<agent>/<harness>_sessions`). Pokud se `OUTPUT`
  vyskytuje v `entry` (v `path` některé edit nebo v libovolném řetězci envelope), spočti
  `output_path(request.prompt, adw_id)` a nahraď `OUTPUT` ve všech `path` edits a rekurzivně ve
  všech řetězcích envelope (listy, dict). Chybu `ValueError` nech propadnout (fáze selže nahlas).
  Zaznamenej výslednou cestu do `call` záznamu (`"output": ...`) pro diagnostiku.
- Aktualizuj docstring modulu (popis `@output`).

`aifactory/validation/fake_scripts.py`:

- `_plan`: `spec = fake.OUTPUT` (import `from validation.fake import OUTPUT`), tedy edit
  `{"path": OUTPUT, ...}`, `artifacts=[OUTPUT]`.
- `_document`: `doc = OUTPUT`, `artifacts=[OUTPUT]`, `document_path=OUTPUT`.
- `TASK_STEMS` ponech (používají ho testy `test_validation_template.py:94` a
  `test_validation_f2.py:136`), jen uprav komentář nad ním: stem popisuje, co hlídač povolí,
  fake cestu bere z promptu.
- Ověř, že scénáře (`validation/scenarios.py`) nekontrolují cestu spec/doc způsobem, který by
  se změnou rozbil (grep `specs/`, `app_docs/`, `document_path`); pokud kontrolují existenci
  `specs/<stem>.md`, nech to — je to nezávislá kontrola proti hlídači.

### 5. Testy

a) `aifactory/tests/validation/test_validation_unit.py` (nebo nový `test_validation_prompt_paths.py`):
- `output_path` z promptu s `## Task` a `` `<context_handoff_dir>/plan.md` `` + `` `specs/T1-x.md` ``
  → `specs/T1-x.md`.
- starý text s `` `specs/<adw_id>_<slug>.md` `` a `adw_id="abcd1234"` → `specs/abcd1234_slug.md`.
- bez `## Task` / bez cesty → `ValueError`.
- `FakeHarness.run` s entry obsahující `@output` (vzor: `test_fake_harness_applies_edits_and_returns_the_envelope`):
  soubor vznikne na cestě z promptu, envelope má cestu místo `@output`.

b) Hlídací test „žádný prompt v `aifactory/` nemá pojmenování podle adw_id“
(např. do `tests/validation/test_validation_template.py`, vzor `test_review_rule_is_not_in_the_product`):
projdi všechny soubory pod `AIFACTORY_DIR / "src"` a `AIFACTORY_DIR / "validation"`
(vynech `__pycache__` a `validation/results/`), a assertuj, že žádný neobsahuje `"<adw_id>_"`.
Navíc explicitně: každý `*/prompts/*/*.md` v `TEMPLATE_DIR` nemá `<adw_id>`, planner `user.md`
obsahuje `{{spec_path}}`, documenter `user.md` obsahuje `{{doc_path}}`.

c) E2E test v lokální validaci (nový `tests/validation/test_validation_prompt_paths.py`,
`@pytest.mark.skipif(shutil.which("just") is None, ...)` jako `test_validation_local.py`),
parametrizovaný `("spec_path", "adw_id")`:
1. `sb = sandbox.setup_local(work)` (`work = tmp_path / "work"`, vytvoř `mkdir`).
2. Pro variantu `adw_id`: v `sb.repo/.factory/prompts/planner/user.md` nahraď `{{spec_path}}`
   za `specs/<adw_id>_<slug>.md`, `git commit -am` a `git push -q origin main`
   (task run čte konfiguraci a prompty z base commitu).
3. Zapiš `fake_scripts.script_for("M01-S01-T01")` do JSON a spusť
   `sys.executable -m validation.worker task run M01-S01-T01 --repo <repo> --json` s
   `cwd=repo`, `env`: `PYTHONPATH` obsahuje `AIFACTORY_DIR`, `HAIFA_VALIDATE_FAKE=<script>`,
   tripwire pro `AIFACTORY_GH`, `CODEX_PATH`, `CLAUDE_CODE_PATH`, `PI_PATH` (převzít `_tripwire`),
   `UV_NO_SYNC=1`, bez `HAIFA_SANDBOX_REPO`/`HAIFA_VALIDATE_HIDDEN` (vzor `Context._spawn`).
4. `data = context.parse_stdout(proc.stdout)`:
   - `adw_id`: `proc.returncode == 1`, `data["error"]["code"] == "run_failed"`, a
     „outside its task run“ v textu chyby (message nebo `data["data"]["run"]["error"]`, podle toho,
     kde je; viz `cli.py:894`). Documenter se nevolal (`<script>.calls.jsonl` nemá agenta
     `documenter`).
   - `spec_path`: `proc.returncode == 0`, `data["ok"] is True`; v `calls.jsonl` má planner
     `output == "specs/M01-S01-T01-clamp.md"` a documenter `app_docs/M01-S01-T01-clamp.md`.
   - Tripwire marker neexistuje.

d) Bod 1: test vykreslení `spec_path`/`doc_path` v `tests/run/`.

Testy nesmějí volat model (fake harness + tripwire to zajišťují).

## Ověření

Z kořene repa (`/Users/jbk/Documents/HAIFA`):

1. `just test` — projde (včetně `test_validate_local` a nových testů).
2. `just typecheck` a `just lint` — projdou (`ruff format` spusť na změněné soubory).
3. `just validate --remote local` — souhrn bez `failed`.
4. `grep -rn "<adw_id>_" aifactory --exclude-dir=__pycache__ --exclude-dir=.venv` — jen `aifactory/tests/`.
5. `git status` — žádné změny ve `vendor/` ani `prototype/`.

## Omezení

- `vendor/`, `prototype/` se nemění; hlídač (`run/guard.py`, `run/scope.py`) a pojmenování z 2.9 se nemění.
- Testy nevolají model.
