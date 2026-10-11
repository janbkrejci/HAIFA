# Plán 2.21: skrytý test R10 se opravdu spustí, `resolve` má smyčku test → fix

Úkol: `backlog/phase-02/task-2.21.md`. Validace proti GitHubu (běh `github-160918`) ukázala dvě chyby:
1. R10: `test_1` prošel, jeho výstup neobsahuje `HiddenSlugifyTest`, `fix` neproběhl, výsledek je `inconclusive`.
2. `resolve`: po vyřešení konfliktu testy selhaly a běh skončil `accept not met`. Workflow nemá opravné kolo.

Omezení: `vendor/` ani `prototype/` neměň. Testy nesmí volat model. Modely v rosterech neměň.

---

## Část 1: skrytý test R10

### Diagnóza

Dnes to funguje takto (`validation/hidden.py`, `validation/context.py`, `validation/template/justfile`):
- skrytý test leží v `<workdir>/hidden/test_hidden_slugify.py`;
- `Context._spawn` dá každému příkazu `factory` proměnnou `HAIFA_VALIDATE_HIDDEN=<workdir>/hidden`;
- recept `test` v justfile sandboxu tento adresář spustí, pokud je proměnná nastavená.

Chyba je v tom, že agenti dědí stejné prostředí. Harnessy (`agent_cc.py`, `codex.py`, `agent_pi.py`) spouštějí CLI s `env=operator_env()`, což je kopie `os.environ`. Skutečný builder na GitHubu podle zadání („Done when `just test` passes“) sám spustí `just test`. Tím spustí i skrytý test, uvidí požadavek `x-empty` a splní ho už v kole `build`. Potom `test_1` projde, v tichém režimu `-q` se o úspěšném skrytém testu nic nevypíše, a `fix` tedy nenastane. Lokálně to neprojde, protože falešný harness `just test` nespouští.

Nové řešení musí splnit tři věci:
- Skrytý test běží jen v kódovém kroku `test` enginu.
- Při tomto kroku leží tam, kde ho `just test` sandboxu najde sám od sebe: `tests/test_hidden_slugify.py` ve worktree běhu.
- Agent ho nikdy nevidí na disku ani v prostředí. Nemůže ho ani smazat, protože se vkládá znovu při každém kroku `test`.

### Mechanismus

Proces `factory` ve validaci vždy běží přes `python -m validation.worker`. Ten proto může nainstalovat „hidden gate“:
- obalí `aifactory.engine.quality.test`, tedy blok, který přes `run_tests` volá interpret (`workflow/interpreter.py:67`) i `run_quality`;
- těsně před `just test` zapíše skrytý test do `<run.repo_root>/tests/test_hidden_slugify.py`;
- po testu ho v `finally` odstraní.

Worker si cestu přečte z `HAIFA_VALIDATE_HIDDEN` a proměnnou hned smaže z `os.environ`. Agenti ji proto nezdědí, protože `operator_env()` kopíruje `os.environ` až v okamžiku spuštění.

Engine (`src/aifactory/`) se nemění. `quality.test` je globální jméno modulu a `run_tests` ho hledá až při volání, takže stačí `setattr(quality, "test", wrapper)`.

### Změny souborů

**`aifactory/validation/hidden.py`**
- Konstanty `HIDDEN_ENV`, `HIDDEN_DIR`, `HIDDEN_FILE`, `HIDDEN_CLASS`, `HIDDEN_EXPECTED`, `HIDDEN_TEST` a funkce `write_hidden(workdir)` zůstávají. Zdroj dál leží mimo repo.
- Přidej `HIDDEN_TARGET = "tests/" + HIDDEN_FILE`, tedy relativní cestu ve worktree nebo checkoutu.
- Přidej `@contextmanager placed(root: Path, source: Path) -> Iterator[Path]`:
  - zkopíruje `source / HIDDEN_FILE` do `root / HIDDEN_TARGET`;
  - pokud tam soubor už je, zapamatuje si jeho obsah;
  - pokud `root/tests` neexistuje, nevloží nic a jen `yield`;
  - v `finally` soubor smaže, nebo vrátí původní obsah, a odstraní případný `tests/__pycache__/test_hidden_slugify.*.pyc`, aby po testu nezůstala stopa.
- Přidej `wrap_test(original: Callable[[Any], Any], source: Path) -> Callable[[Any], Any]`. Vrací `def test(run): with placed(Path(run.repo_root), source): return original(run)`.
- Přidej `install(source: Path) -> None`: `from aifactory.engine import quality; quality.test = wrap_test(quality.test, source)`. Hlídej, aby se nenainstalovala dvakrát, například atributem `_haifa_hidden` na wrapperu.
- Přidej `exclude(repo: Path) -> None`: připíše `/tests/test_hidden_slugify.py` do `<git-common-dir>/info/exclude` sandboxu, pokud tam ještě není. Cestu zjistíš přes `git rev-parse --git-common-dir`. Worktree sdílí `info/exclude` s hlavním repem, takže soubor, který by po pádu procesu ve worktree zůstal, se nikdy necommitne, neobjeví se v `changes` ani ve write guardu. Do `.gitignore` šablony ho **nedávej**, protože `.gitignore` agent vidí.
- Přepiš docstring modulu podle nového mechanismu.

**`aifactory/validation/worker.py`**
- V `main()` před `fake.install`:
  ```python
  hidden_dir = os.environ.pop(HIDDEN_ENV, None)
  if hidden_dir:
      from validation import hidden
      hidden.install(Path(hidden_dir))
  ```
  Import `HIDDEN_ENV` ber z `validation.hidden`. Import `aifactory.engine.quality` uvnitř `install` je v pořádku, `aifactory.cli` se importuje až potom.
- Doplň docstring.

**`aifactory/validation/template/justfile`**
- Odstraň řádek s `HAIFA_VALIDATE_HIDDEN` a jeho komentář. Recept `test` bude jen `python3 -m unittest discover -s tests -t . -q`. Skrytý test ho najde sám, když leží v `tests/`.

**`aifactory/validation/sandbox.py`**
- V `setup_local` a `setup_github` po vytvoření nebo klonu repa zavolej `hidden.exclude(repo)`. Pozor na cyklický import: `hidden.py` nesmí importovat `sandbox.py`, takže zavolej `git` přes `subprocess`.

**`aifactory/validation/context.py`**
- `_spawn` dál nastavuje `HIDDEN_ENV`. Je to kanál pro worker a worker ho spotřebuje. Oprav jen komentář u pole `hidden`.
- `base_suite`: místo nastavení `HIDDEN_ENV` do `env` obal `subprocess.run(["just","test"], ...)` do `with hidden.placed(path, self.hidden)`, pokud `self.hidden` není `None`.

**`aifactory/validation/fake.py`**
- Do záznamu `call` v `FakeHarness.run` přidej dvě pole:
  - `"hidden_file": (cwd / HIDDEN_TARGET).exists()`;
  - `"hidden_env": HIDDEN_ENV in operator_env()`, kde `operator_env` pochází z `aifactory.engine.utils`.
- Zaznamenej je **před** `apply_edits`.

**`aifactory/validation/scenarios.py`, funkce `r10`**
- Kontroly `test_failed_first` a `hidden_test_failed_first` zůstávají.
- Přidej kontrolu `hidden_unseen_by_agents`:
  - v lokálním režimu projdi `<script>.calls.jsonl` příkazu R10 a ověř, že žádné volání nemá `hidden_file` ani `hidden_env` nastavené na true;
  - cestu ke skriptu zjistíš z `ctx.logs`: `_spawn` ho pojmenuje `f"{label}.script.json"`, kde label končí `-M01-S02-T01`. Když je to pohodlnější, ulož cestu skriptu do `Pending`/`Cmd` (nové pole `script: Path | None`) a vezmi ji odtamtud;
  - na GitHubu ověř aspoň, že diff PR nebo `head_sha` neobsahuje `tests/test_hidden_slugify.py`: `git ls-tree -r <head> -- tests/test_hidden_slugify.py` musí být prázdný. Pokud nejde ani to, zaznamenej `observe`.
- Kontrolu přidej ke společným kontrolám před větví `if not fixes`, aby se počítala v obou režimech.

**`aifactory/validation/README.md`**
- Přepiš odstavec „test → fix (R10)“:
  - skrytý test vkládá worker jen na dobu kódového kroku `test` do `tests/` worktree;
  - proměnná slouží jen jako kanál do workeru a agenti ji nedostanou;
  - soubor je v `info/exclude`.

### Testy (část 1)

Uprav **`aifactory/tests/validation/test_validation_template.py`**:
- `_suite(repo, hidden_dir)`: místo env použij `with hidden.placed(repo, hidden_dir)`. Test `test_base_suite_is_green_with_and_without_the_hidden_test` musí dál platit: slugify ještě neexistuje, takže se skrytý test přeskočí.
- `_hidden_result` a `test_hidden_test_fails_the_first_build_and_passes_the_fix` přepni na `placed`. Test dál ověřuje, že `HIDDEN_CLASS` je ve výstupu prvního buildu a oprava projde.
- Nový test `test_justfile_has_no_hidden_hook`: `justfile` šablony neobsahuje `HAIFA_VALIDATE_HIDDEN` a `test_hidden_is_outside_the_template` zůstává.

Přidej unit testy (nový soubor `aifactory/tests/validation/test_validation_hidden.py` nebo do `test_validation_unit.py`):
- `placed` vloží soubor do `tests/`, po bloku ho smaže a to i po výjimce. Existující soubor se stejným jménem vrátí do původního stavu. Bez `tests/` neudělá nic.
- `wrap_test`: falešný `original` zaznamená, jestli během volání `tests/test_hidden_slugify.py` existuje (má být True). Po návratu soubor neexistuje.
- `worker` s `HAIFA_VALIDATE_HIDDEN` zavolá `hidden.install` a proměnnou odstraní z `os.environ`. Test přes `monkeypatch`:
  - nahraď `hidden.install` záznamníkem a `aifactory.cli.main` stubem, který vrátí `os.environ.get(HIDDEN_ENV)`;
  - ověř, že stub vidí `None` a install dostal cestu;
  - nesmí zůstat trvale nainstalovaný wrapper, proto patchuj `quality.test` přes `monkeypatch`.
- `exclude` zapíše řádek do `info/exclude` jen jednou a `git status --porcelain` soubor v `tests/` neukáže.

Uprav **`aifactory/tests/validation/test_validation_local.py::test_r10`**, který je požadavkem „Done means“ pro lokální režim:
- explicitně ověř, že kontroly `test_failed_first`, `hidden_test_failed_first` a `hidden_unseen_by_agents` mají `ok: true`;
- ověř, že `measurements.repair_rounds >= 1`.
Pomocné funkce pro čtení kontrol podle jména v souboru už jsou, například `_stage`/`_review_round`, tak je použij.

---

## Část 2: `resolve` se smyčkou test → fix

### Změny

**`aifactory/src/aifactory/defaults/workflows/resolve.yaml`**
```yaml
# A pull request that conflicts with base (step 6 of "Běh úkolu"): factory task resolve <task-id>.
# Phases: engineer(request) -> git(rebase) [-> builder(resolve), only on a conflict]
#         -> code(test) [-> builder(fix) -> code(test) ... bounded, only on a conflict]
# Code commits and pushes after the workflow: only without conflict markers and with a green suite.
name: resolve
description: Bring a conflicting pull request up to date with base and prove the suite is still green
steps:
  - rebase
  - resolve:
      when: rebase.conflict
      description: Settle every conflict in the files the rebase reported, keeping both sides' intent
  - repeat: {max: 3, until: test.passed}
    steps:
      - test:
          description: Re-run the suite on the rebased branch before it is pushed
      - fix:
          when: rebase.conflict
          description: Repair what the suite reported, from its verbatim output, only in the conflicted files
accept: test.passed
```
Proč má `fix` podmínku `when: rebase.conflict`:
- Bez konfliktu má `ConflictWriteGuard` prázdný scope, takže jakákoli oprava by byla porušením guardu.
- `finish_resolve` bez konfliktu nic necommituje, takže by se oprava ani nepushnula.
- S konfliktem guard povolí přesně konfliktní soubory. `finish_resolve` je stáhne přes `git add -A -- <files>` a změny z `fix` tak jdou do commitu rozlišení.

Bez konfliktu se červený test prostě zopakuje, maximálně třikrát, a běh skončí `accept not met`. To je stejný výsledek jako dnes.

Ověř ještě dvě věci. Parser má u role `fix` povolit `when` a interpret má dávat fázím jména `test_1`, `fix_1`, `test_2`. Obojí platí i pro `simple-sdlc`. `test.passed` čte poslední výsledek.

**`aifactory/src/aifactory/engine/defaults/roles.yaml`**
- Role `fix` už existuje: `agent: builder`, `BuildOutput`, `gates: [diff_matches_claims]`. Popis je obecný („Repair what the previous step reported“), takže se nemění.
- Pokud `workflow check` nebo `test_role_registry` vyžaduje něco jiného, uprav jen komentář.

**`aifactory/src/aifactory/run/resolve.py`**
- Uprav jen docstring modulu: „Then the suite runs, with up to two repair rounds (`fix`) on the conflicted files.“
- Logika zůstává. `finish_resolve` čte jen `rebase`.

**Vyhledej další závislosti na fázi `test` v `resolve`**
- Hledej `grep -rn '"test"' aifactory/src/aifactory/review aifactory/src/aifactory/run`. `prbody.py` a `publish` už `test_N` znají ze `simple-sdlc`, ale ověř to.
- Scénář `RESOLVE` ve `validation/scenarios.py` už bere poslední `test(_\d+)?`.

### Testy (část 2)

**`aifactory/tests/workflow/test_default_workflows.py::test_resolve_structure`**
- Rozbal kroky jako `rebase, resolve, loop = workflow.steps`.
- Ověř:
  - `loop` je `Repeat` s `max == 3` a `until.source == "test.passed"`;
  - kroky jsou `test` (CodeStep) a `fix` (RoleStep, `role.agent == "builder"`, `when.source == "rebase.conflict"`).

**`aifactory/tests/run/test_task_resolve.py`**
- `test_red_suite_restores_branch`: suite je teď `ResolveCode([False, False, False])`.
  - Builder dostane tři skriptované položky: `resolve` a pak `fix_1` a `fix_2`. Každá přes `resolver(script, settle, changed_files=[MODEL])` nebo s efektem, který mění jen `MODEL`.
  - Ověř `len(builder_calls(script)) == 3` a `assert_restored`.
  - Pozor na `diff_matches_claims`: když `fix` zapíše stejný obsah, diff je prázdný. Zapisuj proto pokaždé jiný obsah, například `VALUE = 4`, `VALUE = 5`, nebo ověř, jak gate hodnotí prázdný diff, a podle toho uprav `changed_files`.
- `test_clean_rebase_red_suite_restores_branch`: `ResolveCode([False, False, False])` a `builder_calls == []`, protože `fix` se bez konfliktu nespustí.
- Nový test `test_fix_repairs_what_resolve_broke`, požadovaný v „Done means“:
  - Kódový runner `SuiteCode(ResolveCode)`, kde `test(run)` vrátí `_result(passed, "test")`. `passed` je True, právě když `Path(run.repo_root) / MODEL` neobsahuje `BROKEN`. Nepoužívej skriptovaný seznam. Suite je tak skutečná funkce obsahu worktree.
  - `run_both(repo, script)`, `before = tip(repo)`.
  - `resolver(script, lambda wt: write(wt, MODEL, "VALUE = 3\nBROKEN = True\n"), changed_files=[MODEL])`: resolve odstraní markery, ale rozbije test.
  - `resolver(script, lambda wt: write(wt, MODEL, "VALUE = 3\n"), changed_files=[MODEL], commit_message="Fix model")`: fix test opraví.
  - `result = resolve_task(repo, T02, code=SuiteCode([]))`.
  - Ověř:
    - `result.run.state == "succeeded"`;
    - `len(builder_calls(script)) == 2`;
    - fáze workflow jsou `rebase, resolve, test_1, fix_1, test_2`. Čti je z `result.workflow_run.records`, nebo z tabulky phases v trace DB podle toho, co už ostatní testy používají;
    - `git show <branch tip>:src/app/model.py` je `VALUE = 3\n` bez markerů;
    - `before` je předek nového tipu, nebo tip obsahuje merge base T01, podle vzoru `test_conflict_resolve_then_approve`.
  - Druhý `fix` builder nesmí dostat: skript je vyčerpaný, takže by `FakeHarness` selhal.
- Zkontroluj ostatní testy s `ResolveCode([True])`. Beze změny projdou, protože `until` skončí po `test_1`.

**`aifactory/tests/workflow/test_default_workflows_run.py`** a **`test_rebase.py`**
- Pokud spouštějí `resolve.yaml` se skriptovaným testem `[False]`, doplň hodnoty, případně builder položky, jako výše. `FakeCodeRunner` jinak vyhodí „no scripted test result left“.

### Lokální validace RESOLVE

`validation/fake_scripts.py::_lerp_resolve` dává builderu jednu položku. Rozlišení `resolved_mathx()` suite projde, takže `fix` nenastane a skript stačí. Neměň to. Kdyby `just validate --remote local` hlásil „no scripted entry left for 'builder'“, rozlišení je červené a je potřeba opravit `resolved_mathx`, ne přidávat položku.

---

## Ověření

Spouštěj z kořene repa (`/Users/jbk/Documents/HAIFA`), kde je justfile:
1. `just test`: celá sada `aifactory` včetně `tests/validation` a `tests/run/test_task_resolve.py`.
2. `just typecheck`
3. `just lint`
4. `just validate --remote local`: `summary.json` nesmí mít žádný scénář `failed`. R10 musí být `passed` s `hidden_test_failed_first`, `test_failed_first` a `hidden_unseen_by_agents` ok. RESOLVE musí být `passed`.

Výsledek posuzuj podle exit kódu, ne podle slov ve výstupu.

Rychlá ruční kontrola na sandboxu z `--keep-workdir`:
- ve worktree po běhu R10 není `tests/test_hidden_slugify.py`;
- `command.log` fáze `test_1` obsahuje `HiddenSlugifyTest` a `exit: 1`.

## Shrnutí dotčených souborů
- `aifactory/validation/hidden.py`, `worker.py`, `context.py`, `sandbox.py`, `fake.py`, `scenarios.py`, `README.md`, `template/justfile`
- `aifactory/src/aifactory/defaults/workflows/resolve.yaml`
- `aifactory/src/aifactory/run/resolve.py` (jen docstring)
- `aifactory/src/aifactory/engine/defaults/roles.yaml` (jen pokud je to nutné; role `fix` existuje)
- `aifactory/tests/validation/test_validation_template.py`, `test_validation_local.py`, nový `test_validation_hidden.py`
- `aifactory/tests/workflow/test_default_workflows.py` (+ případně `test_default_workflows_run.py`, `test_rebase.py`)
- `aifactory/tests/run/test_task_resolve.py`
