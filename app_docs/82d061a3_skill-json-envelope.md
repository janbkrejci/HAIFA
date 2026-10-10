# `factory --skill` a jednotná `--json` obálka (D12)

## Co se změnilo a proč

1. **`factory --skill`** vypíše markdownový skill pro coding agenta, který ovládá HAIFA z příkazové řádky. Generuje se z aktuálního kódu, takže nemůže zastarat. Seznam příkazů vzniká průchodem argparse definice CLI, ne ručním psaním. Formáty a kódy chyb se berou z modulů, které je definují. `factory --skill --json` vrátí stejná data v obálce.
2. **Každý příkaz s `--json` vrací stejnou obálku:**
   ```json
   {"ok": bool, "data": {...} | null, "error": {code, message, path, id, issues} | null, "warnings": [str]}
   ```
   Starý tvar (`{"ok": ..., <payload>}` nebo `{"ok": false, "errors": [...]}`, u config/workflow `"error": str`) je pryč. Payload příkazu je teď pod `data`. `warnings` se přesunuly na nejvyšší úroveň obálky. Problémy validace jsou v `error.issues`, resp. v `data.issues`, dříve `errors`.
3. **Stabilní kódy chyb** jsou v jednom registru (`skill/codes.py`), každý s exit kódem. Skill je vypisuje jako tabulku. Test hlídá, že v registru nechybí žádný kód použitý v kódu.

**Exit kódy:**
- `0`: ok.
- `1`: příkaz doběhl, ale našel problém: `run_failed`, `pr_failed`, `backlog_invalid`, `workflow_invalid`, `harness_missing`.
- `2`: příkaz nemohl svou práci udělat a nic nezměnil.

Platí, že `ok == (exit == 0)`.

## Soubory

**Nový balíček `aifactory/src/aifactory/skill/`**
- `envelope.py`: obsahuje tyto funkce:
  - `envelope_ok` a `envelope_fail` sestaví obálku.
  - `strip_payload` oddělí ze starých `to_json()` payloadů `ok`/`warnings`.
  - `envelope_problems(obj)` je spustitelná specifikace pravidel obálky. Vrací seznam porušení, prázdný seznam znamená, že je obálka platná.
- `codes.py`: obsahuje dvě struktury:
  - `ERROR_CODES` (`ErrorCode(code, exit, meaning)`): všechny možné hodnoty `error.code`, včetně nových `usage_error`, `internal_error`, `backlog_invalid`, `workflow_invalid`, `harness_missing`, `run_failed`, `pr_failed` a `invalid_roles`.
  - `ISSUE_CODES`: kódy `issues[].code` podle skupin backlog / workflow / roles / config.
- `commands.py`: `iter_commands(parser)` projde subparsery a vrátí `CommandSpec` pro každý list, včetně argumentů, skupin a příznaků `has_json` / `has_repo`. `format_commands` z nich udělá markdownovou referenci.
- `render.py`: `render_skill()` vyplní placeholdery `{{…}}` v šabloně. Obsah placeholderů se bere z kódu: příkazy, kódy chyb, stavy, pořadí polí hlavičky, `index.md`, klíče `ProjectSettings`, vestavěné workflow, role, harnessy, úrovně thinking, důvody přeskočení a zastavení řetězu. Pokud nějaký placeholder zůstane nevyplněný, funkce vyhodí `RuntimeError`. `skill_json()` je `data` pro `--skill --json`.
- `skill.md`: šablona skillu. Obsahuje sekce:
  - konvence volání a obálka,
  - Commands, Error codes,
  - Backlog format (hlavička tasku, `index.md`, `.factory/config.yaml`),
  - Workflow format,
  - Procedures: Plan → backlog, Run, Review, Approve, Return, Resolve, Sync and cleanup.
- `__init__.py`: re-exporty.

**`aifactory/src/aifactory/cli.py`**
- Kořenový parser dostal volby `--skill` a `--json` (`dest="root_json"`). `--json` bez `--skill` vrátí `usage_error`.
- `_Parser.error` vyhodí `_UsageError`, takže s `--json` jde i chyba argparse ven jako obálka `usage_error` (exit 2). Bez `--json` se chová jako dřív: vypíše usage na stderr a skončí s `SystemExit(2)`.
- `main` s `--json` obalí dispatch. Neočekávaná výjimka vypíše traceback na stderr a vrátí obálku `internal_error`.
- Ruční JSON výstupy nahradily společné helpery:
  - `_emit_ok` a `_emit_fail` vypisují obálku.
  - `_fail_from_exception` mapuje výjimky: `TaskEditError`, `TaskRunError`, `ReviewError` si nesou vlastní kód, `ConfigError` a `HarnessConfigError` dávají `invalid_config` a `RolesError` dává `invalid_roles`.
  - `_emit_runs` rozhoduje mezi `run_failed` a `pr_failed` podle prvního selhaného běhu. `pr_failed` znamená, že běh doběhl jako succeeded, ale selhal push nebo PR.
  - `_problem_warnings` převádí počet problémů na warning.
- Staré helpery `_print_json` a `_config_error` jsou odstraněné. Epilog s kódy chyb se zkrátil a odkazuje na `factory --skill`.

**`aifactory/src/aifactory/run/queue.py`**: přidané konstanty `STOP_REASONS` a `SKIP_REASONS`, ze kterých čte skill.

**`aifactory/pyproject.toml`**: `pythonpath = ["tests"]`, aby šel importovat sdílený helper `tests/cli_json.py`.

**Testy**
- `tests/cli_json.py`: `read_envelope` a `run_json`. Oba ověří `envelope_problems(obj) == []` a `run_json` navíc `ok == (rc == 0)`.
- `tests/test_skill.py` hlídá tyto věci:
  - každý listový příkaz a každá jeho volba jsou ve skillu,
  - každý příkaz má `--json`,
  - skill obsahuje kódy chyb a sekce,
  - fungují `--skill` i `--skill --json`,
  - AST sken zdrojů najde literály kódů chyb a issue kódů a ověří, že všechny jsou v `ERROR_CODES` / `ISSUE_CODES`.
- `tests/test_json_envelope.py` hlídá tyto věci:
  - pro každý příkaz z `iter_commands` sestaví argv s dummy argumenty, spustí ho s `--json` a ověří platnou obálku a to, že kód není `internal_error`,
  - obálku `usage_error` a `internal_error`,
  - úspěšné cesty backlog, task a workflow a samotné helpery obálky.
- Existující CLI testy (backlog, task, config, harness, run, workflow) byly přepsány na nový tvar: `env["data"][…]` a `env["error"]["code"]`. Kde se dřív kontrolovalo `errors[0]["code"]`, teď se kontroluje `error.issues[0].code`. `test_smoke.py` navíc ověří `--skill` v `--help`.

**`specs/82d061a3_skill-json-envelope.md`**: specifikace této změny.

## Použití a ověření

```bash
factory --skill                 # markdown skill pro tuto verzi
factory --skill --json          # {ok, data: {version, skill, commands, error_codes, issue_codes}, ...}
factory task show X-T01 --json  # data.task …, nebo error.code "unknown_task" (exit 2)
factory task bogus --json       # error.code "usage_error" (exit 2)
```

Ověření: v `aifactory/` spusťte `just test`, `just typecheck` a `just lint`. Klíčové testy jsou `tests/test_skill.py` a `tests/test_json_envelope.py`.

**Pro konzumenty JSON výstupu je to breaking change:**
- payload je teď pod `data`,
- chyby jsou v `error` místo `errors`,
- `backlog check` a `workflow check` s problémy vrací `ok: false` s kódem `backlog_invalid` / `workflow_invalid` a problémy jsou v `data.issues` i `error.issues`,
- `harness check` s chybějícím harnessem vrací `harness_missing`.

**Kde přidat nový kód:** nový kód chyby se musí přidat do `skill/codes.py`, jinak spadne `test_error_codes_complete`. Nový subcommand se ve skillu objeví automaticky, ale musí mít `--json`.
