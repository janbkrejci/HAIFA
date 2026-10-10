# HAIFA-S03-T01: Krok `test` podle `test` a `test_command`, ne vždy `just test`

## Co se změnilo a proč

Krok `test` ve workflow měl dřív příkaz natvrdo zapsaný jako `["just", "test"]` (`engine/quality.py`).
Pole `test` z backlogu ani `test_command` z `.factory/config.yaml` nikdo nečetl, takže
běhy HAIFA s `test_command: [just, check]` vynechávaly typecheck a lint.

Teď běh tasku najde příkaz jednou, ještě před startem, a použije ho pro **každý** krok
s akcí `test`. Patří sem i kroky pod jiným `id` (např. `retest`) a běhy přes
`factory task resolve`, protože příkaz se hledá dřív, než se cesta pro resolve oddělí. Pořadí:

1. `test` v tasku,
2. `test` v nejbližším `index.md` nad taskem (step, potom modul); úroveň bez klíče nebo s `null` se přeskočí,
3. `test_command` v `.factory/config.yaml`,
4. výchozí `just test`.

Hodnota `test` je buď řetězec, který se dělí jako v shellu (`"uv run pytest -q"`), nebo
seznam neprázdných řetězců (`[uv, run, pytest, -q]`). Událost `quality:test` v trace
nese příkaz, který opravdu běžel.

## Kde to je

- `aifactory/src/aifactory/config/settings.py`: nové `split_command(value)` převede hodnotu
  na argv. Při jiném typu, chybě `shlex`, prázdném výsledku nebo prázdné části vyhodí `ValueError`.
  Exportuje ho `config/__init__.py`.
- `aifactory/src/aifactory/backlog/derived.py`: `effective_test(task)` vrátí nejbližší
  hodnotu `test`, která není `None` (nejdřív task, pak předci). Exportuje ho `backlog/__init__.py`.
- `aifactory/src/aifactory/backlog/loader.py`: neplatné `test` v tasku i v `index.md`
  ohlásí `invalid_field`. Hodnota se přitom **ponechá**, aby běh selhal a tiše nepřešel
  na zděděný příkaz.
- `aifactory/src/aifactory/run/task.py`: `DEFAULT_TEST_COMMAND = ("just", "test")` a
  `resolve_test_command(task, settings)`. Funkce se volá v `run_task` ještě před vytvořením
  worktree a větve. Při neplatné hodnotě vyhodí `TaskRunError("invalid_test", …)`. Výsledek
  putuje přes `_Job.test_argv` do `run_workflow(test_command=…)`.
- `aifactory/src/aifactory/workflow/interpreter.py`: `run_workflow` má nový parametr
  `test_command` a nastaví z něj `run.test_argv`.
- `aifactory/src/aifactory/engine/runner.py`: nový atribut `Run.test_argv` (výchozí `None`).
  `aifactory/src/aifactory/engine/quality.py`: `test()` použije `run.test_argv`, a když
  chybí, použije `["just", "test"]`. Obě změny v enginu mají značku `# aifactory 2.9:`.
- `aifactory/src/aifactory/skill/codes.py`: nový chybový kód `invalid_test` (exit 2).
- `aifactory/src/aifactory/skill/skill.md`: popis pole `test` a toho, odkud krok `test`
  bere příkaz (`factory --skill`).

## Testy

- `aifactory/tests/run/test_task_test_command.py`: skutečný běh `run_task` s opravdovým
  podprocesem (`sys.executable -c …`). Příkaz, který proběhl, čte z událostí `quality:test`
  v `.factory/trace.db`. Ověřuje, že task přebije `index.md` i config, `index.md` stepu
  přebije config, `index.md` modulu se dědí a config přebije výchozí příkaz. Dál ověřuje,
  že výchozí příkaz je `just test`, že nenulový návratový kód krok shodí (`accept not met`)
  a že `retest` spustí stejný příkaz. Neplatné `test` (v tasku nebo ve stepu) skončí
  `invalid_test` dřív, než vznikne worktree, větev nebo volání agenta.
- `aifactory/tests/workflow/test_workflow_test_command.py`: `run_workflow(test_command=…)`
  pro návratový kód 0 a pro nenulový. Bez nastavení zůstává `just test`.
- `aifactory/tests/backlog/test_backlog_test_field.py`: `split_command` (platné a neplatné
  vstupy), hlášení `factory backlog check --json` a pravidla dědění v `effective_test`.
- `aifactory/tests/validation/test_validation_template.py`: `test_workflow_names_three_harnesses`
  teď volá `chdir` do sandboxu, protože `workflow check` čte seznam modelů z pracovního
  adresáře.

## Jak ověřit

```sh
just test && just typecheck && just lint
```

Ručně: do tasku nebo do `index.md` přidejte `test: [just, check]` (nebo `test_command`
do `.factory/config.yaml`), spusťte `factory task run <id>` a v trace u události
`quality:test` zkontrolujte pole `command`. Neplatná hodnota (např. `test: 5`) se objeví
ve `factory backlog check` jako `invalid_field` a `factory task run` skončí s `invalid_test`.
