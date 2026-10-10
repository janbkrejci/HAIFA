# HAIFA-S03-T02: Úroveň module přejmenovaná na project

Nejvyšší úroveň backlogu se teď jmenuje `project` místo `module`. Strom je
project → step → task. Kód projektu je dál libovolný krátký řetězec, například `M01` nebo `HAIFA`.

## Co se změnilo

- **Výchozí úrovně:** `ProjectSettings.levels` v `aifactory/src/aifactory/config/settings.py`
  je `("project", "step", "task")`.
- **CLI (`aifactory/src/aifactory/cli.py`):** `factory backlog list` a `factory task list` mají
  volbu `--project ID` (id nebo jméno adresáře). Volba `--module` zmizela a argparse ji
  odmítne s exit kódem 2.
- **JSON:** `filters` obsahuje klíč `project` místo `module`. Neznámý projekt vrací
  kód `unknown_project` (exit 2). V registru kódů (`skill/codes.py`) nahradil `unknown_module`.
- **Hlášky podle `levels`:** neznámý projekt hlásí `unknown <levels[0]> 'X'`.
  `backlog auto-continue` s neznámým id hlásí `no <úrovně kromě poslední, spojené „or“> 'X'`
  (`backlog/edit.py`). Výchozí podoba je `no project or step 'X'`.
- **API balíčku `backlog`:** funkce `select_modules` se přejmenovala na `select_projects`
  (`render.py`, export v `__init__.py`). Funkce `backlog_to_json` a `format_tree` berou keyword `project=`.
- **Texty:** help CLI, docstringy (`backlog/model.py`, `run/__init__.py`, `run/queue.py`)
  a `factory --skill` (`skill/skill.md`) mluví o projektu, včetně cesty
  `<backlog_dir>/<project>/<step>/<task>.md` a příkladu `index.md` projektu. V postupu převodu
  plánu se modul z plánu stane projektem a jeho kód (např. `M01`) zůstává.
- **Šablona validace:** `aifactory/validation/template/.factory/config.yaml.tmpl` má
  `levels: [project, step, task]`. Úměrně tomu se upravil i `template/README.md`.

## Kompatibilita

Repo s explicitním `levels: [module, step, task]` funguje dál beze změny. Volba se ale vždy jmenuje
`--project` a kód chyby je vždy `unknown_project`. Jen text hlášky bere jméno úrovně
z konfigurace, takže zní `unknown module 'M9'` nebo `no module or step 'X'`.

## Ověření

- `just test`, `just typecheck`, `just lint`.
- Nový soubor `aifactory/tests/backlog/test_backlog_project_level.py` pokrývá výchozí úrovně,
  filtr `--project` v obou příkazech, `unknown_project`, hlášku `auto-continue`, odmítnutí
  `--module` a repo se starým `levels: [module, step, task]`.
- `aifactory/tests/test_skill.py::test_skill_uses_project_level` kontroluje, že skill
  obsahuje `--project` a `unknown_project` a neobsahuje `<module>`, `--module` ani `unknown_module`.
- Ručně: `factory backlog list --json --project M01` vrátí `"filters": {"status": null, "project": "M01"}`.
