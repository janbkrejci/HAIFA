# Plan HAIFA-S03-T02: Úroveň module přejmenovaná na project (core, CLI, skill)

## Cíl
Výchozí úrovně backlogu jsou `[project, step, task]`. CLI filtruje volbou `--project`,
JSON vrací `filters.project`, neznámý projekt dává kód `unknown_project`. Texty CLI
a `factory --skill` mluví o projektu. Repo s explicitním `levels: [module, step, task]`
funguje dál (úrovně se berou z konfigurace, kód nesmí nikde natvrdo čekat jméno `project`).

## Pevná omezení
- Neměnit `.factory/`, `docs/`, `vendor/`, `prototype/`. Psát jen pod `aifactory/`,
  `justfile`, spec a `app_docs/HAIFA-S03-T02-uroven-module-prejmenovana-na-project-co.md`.
- Slovo „phase“ nepoužívat pro backlog.
- Mimo rozsah: web API a dashboard (`aifactory/src/aifactory/web/**`, `web/static`,
  frontend). Klíč `"module"` v `web/backlog.py` (řádek ~220), `module_id` ve `web/review.py`
  a hláška `no module or step` ve `web/backlog.py` ZŮSTÁVAJÍ. Testy ve `tests/web/` neměnit
  (používají explicitní `levels: [module, step, task]` z `backlog_fixture.py`, takže
  projdou beze změny).
- Testy nevolají model.

## Změny po souborech

### 1. `aifactory/src/aifactory/config/settings.py`
- `levels: tuple[str, ...] = ("project", "step", "task")` (řádek ~95).

### 2. `aifactory/src/aifactory/backlog/render.py`
- Přejmenovat `select_modules(backlog, module)` → `select_projects(backlog, project)`;
  docstring: „Top-level containers (projects), or those whose id or directory name is
  ``project``.“ `LookupError(project)`.
- `backlog_to_json(..., project: str | None = None)` — keyword `module` → `project`;
  `"filters": {"status": status, "project": project}`; docstring „unknown ``project``“.
- `format_tree(..., project: str | None = None)` — totéž.
- Starý název nezachovávat jako alias (veřejné API je interní; volá ho jen CLI a testy).
  Ověřit `grep -rn select_modules aifactory/src` → web jej nepoužívá.

### 3. `aifactory/src/aifactory/backlog/__init__.py`
- Import a `__all__`: `select_modules` → `select_projects`.
- Docstring řádek 3: „default ``project -> step -> task``“.

### 4. `aifactory/src/aifactory/backlog/model.py`
- Docstring modulu: „containers (project, step, ...)“; docstring `Container`:
  „(a project, a step, ...)“.

### 5. `aifactory/src/aifactory/backlog/edit.py`
- Tabulka kódů v docstringu: řádek `unknown_module` → ``unknown_project`` 2
  ``task list --project`` (CLI); `unknown_container` → „no project or step with that id“
  (zarovnání tabulky RST zachovat — sloupce mají pevnou šířku).
- `set_auto_continue`: hláška podle úrovní:
  ```python
  levels = backlog.settings.levels
  names = " or ".join(levels[:-1])   # "project or step"; u 2 úrovní jen "step"
  raise TaskEditError("unknown_container", f"no {names} '{container_id}'", id=container_id)
  ```
  (Pro `[module, step, task]` vyjde „no module or step 'X'“ — beze změny chování.)
  Pozor: u `[area, module, step, task]` vyjde „no area or module or step“ — přijatelné.

### 6. `aifactory/src/aifactory/cli.py`
- `backlog auto-continue` (řádky ~255–261): help/description „for a project or step“,
  „in the index.md of a project or step“, `auto.add_argument("id", ..., help="project or step id")`.
- `backlog list` (řádek ~289):
  `list_.add_argument("--project", metavar="ID", help="show only this project (id or directory)")`.
  Volbu `--module` odstranit (žádný alias).
- `_backlog_list` / blok kolem řádku 515–525:
  ```python
  payload = backlog_to_json(backlog, issues, status=args.status, project=args.project)
  lines = format_tree(backlog, status=args.status, project=args.project)
  except LookupError:
      level = backlog.settings.levels[0]
      message = f"unknown {level} '{args.project}'"
      if args.json:
          return _emit_fail("unknown_project", message, exit_code=2, id=args.project)
  ```
  (Ověřit, že `backlog` je v tom místě k dispozici — je, používá se výše pro `counts`.)
- `TASK_EPILOG` (řádek ~563): „of the step, then of the project, starts“.
- `task list` (řádek ~629): `--project` místo `--module`, help „only this project (id or directory)“.
- `task run` description (řádek ~639): „step or project“; `--auto` help (řádek ~653):
  „of the project (auto-continue)“.
- `_task_list` (řádky ~800–846): import `select_projects`; `if args.project is not None:`;
  `projects = select_projects(backlog, args.project)`;
  ```python
  level = backlog.settings.levels[0]
  raise TaskEditError("unknown_project", f"unknown {level} '{args.project}'", id=args.project) from None
  ```
  `"filters": {"status": status, "project": args.project, "step": args.step}`.
  Hláška stepu už používá `levels[-2]` — ponechat.
- Projít `grep -n -i module aifactory/src/aifactory/cli.py` a přepsat každý zbývající
  výskyt v textech CLI týkající se backlogu na „project“.

### 7. `aifactory/src/aifactory/run/queue.py`
- Docstring modulu (řádky 9–15): „task, step or project ``index.md``“, „another step of
  the project“, „rest of the same project“.
- `candidates`: docstring „rest of its project“; proměnná `module` → `project`
  (`project = ancestors(after)[-1]`). Chování beze změny.
- Řádek ~189 („Through the module attribute…“) se týká Python modulu — NEMĚNIT.
- `aifactory/src/aifactory/run/__init__.py` řádek ~23 („then of the module“) → „then of
  the project“ (je v allowed paths, text o backlogu).

### 8. `aifactory/src/aifactory/skill/codes.py`
- Nahradit `("unknown_module", "2", "no module with this id or directory")` za
  `("unknown_project", "2", "no project with this id or directory")`.
- `unknown_container`: „no project or step with this id“.
- `tests/test_skill.py` skenuje zdroje a kontroluje úplnost registru; po změně nesmí
  `unknown_module` zůstat nikde ve zdrojích (kromě nic) — zkontrolovat
  `grep -rn unknown_module aifactory/src` → prázdné.

### 9. `aifactory/src/aifactory/skill/skill.md`
- Strom: `<backlog_dir>/<project>/<step>/<task>.md`.
- „Every container directory (project, step) has …“.
- „Example `{{index_file}}` of a project:“ (příklad `id: M01`, `title: Core` může zůstat —
  kód projektu je libovolný a krátký; text těla „Core: the data model and the API.“ OK).
- Test step: „(step, then project)“.
- Postup „Plan -> backlog“, bod 2: „Map every module (or project) of the plan to a project
  directory `<backlog_dir>/<project-id>-<slug>/` with `{{index_file}}` … Put shared
  defaults … into the project or step index.“ Doplnit větu, že modul z plánu se stane
  projektem a jeho kód (např. `M01`) zůstává krátký.
- Run bod 5: „in the project or step `{{index_file}}`“, „then of the project, starts“.
- Kde skill zmiňuje filtry seznamu nebo příklady s `--module`, přepsat na `--project`
  (příkazová reference se generuje z argparse, takže se změní sama).
- Po úpravě: `grep -n -i module aifactory/src/aifactory/skill/skill.md` → žádný výskyt
  týkající se backlogu.

### 10. `aifactory/validation/template/.factory/config.yaml.tmpl`
- `levels: [project, step, task]`.
- Volitelně `aifactory/validation/template/README.md` řádek 5: „2 projects, 3 steps“;
  docstringy `aifactory/validation/f2.py`, `f2_backlog.py` („modules M03 and M04“ →
  „projects M03 and M04“) — jen texty.

## Testy (`aifactory/tests/`)

Upravit existující:
- `tests/config/test_config_settings.py:29` → `("project", "step", "task")`.
- `tests/backlog/test_backlog_load.py:193` (výchozí levels bez configu) →
  `("project", "step", "task")`. Ostatní řádky v tom souboru používají fixture
  `fixtures/sample/.factory/config.yaml` s explicitním `levels: [module, step, task]` —
  NECHAT, to je právě pokrytí starého repa.
- `tests/backlog/test_backlog_render.py`: import `select_projects`, parametr
  `project=`, filtr `{"status": ..., "project": ...}`; přejmenovat testy
  (`test_project_filter`, `test_unknown_project`). `data["levels"]` zůstává
  `["module", "step", "task"]` (fixture se starým levels).
- `tests/backlog/test_backlog_cli.py`: `--module` → `--project`
  (ř. 97, 102, 115), `data["filters"] == {"status": "ready", "project": "M01"}`,
  `test_list_unknown_project`: stderr obsahuje `unknown module 'M9'` (fixture má level
  `module` → hláška používá jméno úrovně z levels!) a JSON kód `unknown_project`.
  Řádky 29/34/158 (`OK: 2 module, …`) nechat — fixture se starými levels.
- `tests/backlog/test_task_cli.py:127,135`: `--project`, `"unknown_project"`.
- `tests/validation/test_validation_template.py:76` a `tests/validation/test_validation_f2.py:93`:
  `n["level"] == "project"` (sandbox vzniká ze šablony), proměnné přejmenovat na `projects`.

Přidat nové testy:
1. **Výchozí úrovně + `--project`**: v `tests/backlog/test_backlog_cli.py` (nebo novém
   `tests/backlog/test_backlog_project_level.py`) vytvořit v `tmp_path` repo s
   `.factory/config.yaml` BEZ `levels` (jen např. `backlog_dir: backlog`), backlog
   `backlog/P1-core/index.md` (`id: P1`), `backlog/P1-core/S01-x/index.md` (`id: P1-S01`),
   task `P1-S01-T01-a.md` (status todo, workflow, writes) a druhý projekt `P2`. Inspirovat se
   helpery `write`/fixturami v `test_backlog_load.py` (řádky ~170–195). Ověřit:
   - `load_backlog(...)`: kořenový kontejner má `level == "project"`; `counts` má klíč `project`.
   - `main(["backlog", "list", "--json", "--repo", root, "--project", "P1"]) == 0`,
     `data["filters"] == {"status": None, "project": "P1"}`, items jen P1;
     `data["levels"] == ["project", "step", "task"]`.
   - `main(["backlog", "list", "--repo", root, "--project", "P9"]) == 2` a stderr
     obsahuje `unknown project 'P9'`; s `--json` je `error.code == "unknown_project"`.
   - `main(["task", "list", "--json", "--repo", root, "--project", "P2"])` vrací jen tasky P2,
     `filters.project == "P2"`; s neznámým projektem `unknown_project` (exit 2) a zpráva
     `unknown project '…'`.
   - `backlog auto-continue NOPE --on --json` → `unknown_container`, zpráva
     `no project or step 'NOPE'`.
2. **Staré repo `levels: [module, step, task]`**: se sample fixture (má explicitní
   module levels) ověřit, že `backlog check` projde, `--project M01` filtruje,
   neznámý dává kód `unknown_project` se zprávou `unknown module 'M9'`, a
   `auto-continue` neznámého id dává `no module or step 'X'`. Část už pokrývají upravené
   existující testy — doplnit jen chybějící aserce (zpráva podle levels, auto-continue).
3. **Argparse**: `--module` už není přijímáno (`main([... "--module", "M01"])` →
   `SystemExit` / usage_error exit 2 — podle toho, jak CLI zachází s argparse chybami;
   zjistit z existujících testů usage_error).
4. **Skill**: v `tests/test_skill.py` přidat test, že výstup `factory --skill`
   (renderovaný text, viz existující testy v souboru) obsahuje
   `<backlog_dir>/<project>/<step>/<task>.md`, `default [project, step, task]`,
   `--project` a `unknown_project`, a neobsahuje `<module>` ani `unknown_module`.

## Ověření
Z kořene worktree:
- `grep -rn -i "unknown_module\|select_modules\|--module" aifactory/src aifactory/tests` → prázdné.
- `grep -n -i module aifactory/src/aifactory/cli.py aifactory/src/aifactory/skill/skill.md aifactory/src/aifactory/backlog/*.py aifactory/src/aifactory/run/queue.py` → jen Pythonové
  „module“ (docstring „see the module docstring“, „module attribute“), nic o backlogu.
- `just test`, `just typecheck`, `just lint` — vše exit 0. (`just test` spouští i
  frontend kontroly `web-test`; frontend neměníme.)
- Ručně: `cd aifactory && uv run factory backlog list --help` ukazuje `--project`;
  `uv run factory --skill | grep -n project`.

## Dokumentace
Builder/documenter zapíše `app_docs/HAIFA-S03-T02-uroven-module-prejmenovana-na-project-co.md`:
co se změnilo (výchozí levels, `--project`, `filters.project`, `unknown_project`, hlášky
podle levels), kompatibilita se starým `levels: [module, step, task]`, a že dashboard API
(`module`, `module_id`) a `.factory/config.yaml` HAIFA se mění samostatně.
