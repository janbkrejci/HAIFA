# Plán: `just proto-validate --roster DIR`

## Cíl

`just proto-validate` dostane volbu `--roster DIR`. Pro daný běh přepíše v materializovaném sandboxu
`.factory/sssf.config.yaml` souborem `DIR/sssf.config.yaml` a `.factory/workflows/simple-sdlc.yaml`
souborem `DIR/workflows/simple-sdlc.yaml`. R1 a R10 hlásí `inconclusive` místo `failed`, když
použitý roster nemá harness, který ověřují:
- R1: v jednom workflow claude, codex i pi;
- R10: build i fix na codexu.

Bez `--roster` se chování nemění.

Mimo rozsah:
- změna výchozí šablony (`prototype/validation/template/`);
- přidání konkrétního rosteru do repa;
- jakákoli úprava `vendor/`.

## Současný stav (co už platí)

- `justfile:131` `proto-validate *ARGS: cd prototype && uv run python -m validation "$@"`. Platí `set positional-arguments`, takže nová volba projde bez změny receptu. Recept **neměň** (jen komentář na ř. 130 můžeš doplnit o `[--roster DIR]`).
- `validation/runner.py`: `EXIT_FAILED` se vrací jen pro `outcome == FAILED`, takže `inconclusive` už dává exit 0. Zachovej to a pokryj testem (viz níže).
- `validation/sandbox.py`: `materialize()` zkopíruje šablonu. `setup_local()` a `setup_github()` pak zavolají `commit_all()`. Roster se musí aplikovat mezi těmito dvěma kroky, aby byl součástí commitu base.
- `validation/scenarios.py`:
  - R1 má natvrdo `HARNESS_OF_PHASE` (plan=claude, build/fix/revise=codex, review=pi, document=claude) a check `harness_per_phase`;
  - R10 má checky `fix_ran_on_codex`, `same_session` a na githubu `thread_resumed`.
- Falešný harness (`validation/fake.py`) je klíčovaný jménem **agenta**, ne harnessu. S rosterem bez codexu proto lokální režim funguje beze změny fake skriptů.
- Pozdější scénáře stojí na R1 a R10. R3 mergne PR z R1 a schválí PR z R10, R4 potřebuje slugify z R10 v base. **R1 i R10 proto musí task spustit i s „nevhodným“ rosterem.** Nesmí skončit dřív, jinak by R3 a R4 nemohly projít.
- R4 upravuje `.factory/sssf.config.yaml` nahrazením řádku `"  - name: planner\n"`. Roster proto musí mít agenty `planner`, `builder`, `reviewer` a `documenter` ve stejném tvaru jako šablona. Prompty se materializují jen pro tyto agenty a fake skripty jsou klíčované stejnými jmény.

## Změny

### 1. Nový modul `prototype/validation/roster.py`

```python
"""The agent roster of the sandbox: the sssf config and the workflow, optionally from --roster DIR."""

ROSTER_FILES: tuple[tuple[str, str], ...] = (
    ("sssf.config.yaml", ".factory/sssf.config.yaml"),
    ("workflows/simple-sdlc.yaml", ".factory/workflows/simple-sdlc.yaml"),
)
WORKFLOW = ".factory/workflows/simple-sdlc.yaml"
AGENTS_CONFIG = ".factory/sssf.config.yaml"

def resolve_roster(value: Path) -> Path: ...
def apply_roster(dest: Path, roster: Path) -> list[str]: ...
def step_harnesses(repo: Path) -> dict[str, str]: ...
def harness_of_phase(harnesses: Mapping[str, str], phase: str) -> str | None: ...
```

- `resolve_roster(value)`:
  - relativní cestu vyhodnoť vůči `HAIFA_ROOT` (import ze `validation.sandbox`). Recept dělá `cd prototype`, takže cwd uživatele se ztratí; kořen repa, kde leží justfile, je přirozený základ;
  - vrať `.resolve()`;
  - když to není adresář nebo chybí některý ze souborů v `ROSTER_FILES`, vyhoď `SetupError` se jmény chybějících souborů.
- `apply_roster(dest, roster)`: `shutil.copyfile` obou souborů do `dest` (rodiče vytvoř). Vrátí seznam cílových relativních cest.
- `step_harnesses(repo)`: efektivní harness každého role kroku workflow v `repo`.
  - načti `load_workflow(repo / WORKFLOW)` z `haifa_proto.workflow`;
  - načti `yaml.safe_load(repo / AGENTS_CONFIG)` a z něj mapu `agents[].name -> coding_agent`;
  - pro každý `RoleStep` z `walk(workflow.steps)` spočítej `step.harness or agent_map.get(step.role.agent)`;
  - jméno kanonizuj přes `haifa_proto.harness.ALIASES` (`claude_code` → `claude`) a ulož pod klíč `step.phase_id`;
  - `WorkflowError`, `OSError` a `yaml.YAMLError` převeď na `SetupError` s důvodem;
  - krok, jehož agent v configu chybí, je taky `SetupError`.
- `harness_of_phase(harnesses, phase)`: jméno fáze z trace (`fix_1`, `review_2`, `plan`, …). Zkus přesnou shodu, pak `re.sub(r"_\d+$", "", phase)`. Když nic nesedí, vrať `None`.

`haifa_proto` je importovatelný (worker ho importuje; `pythonpath` testů a mypy `files` zahrnují `validation`). Hlídej jen, aby import nebyl v modulu, který se načítá před nastavením cest. `runner` se spouští z `prototype/` přes `uv run`, takže `haifa_proto` je nainstalovaný balíček.

### 2. `validation/sandbox.py`

- `setup_local(workdir, roster: Path | None = None)` a `setup_github(workdir, owner_name, when=None, roster: Path | None = None)`:
  - po `materialize(...)` a před `commit_all(...)` zavolej `if roster is not None: apply_roster(repo, roster)`;
  - import dej lokálně nebo nahoru. Pozor na cyklický import: `roster` importuje ze `sandbox` `HAIFA_ROOT` a `SetupError`. Import `roster` v `sandbox` proto dej dovnitř funkcí, nebo přesuň `HAIFA_ROOT` a `SetupError` do `roster` bez importu ze `sandbox`. Doporučuji lokální import uvnitř funkcí.

### 3. `validation/context.py`

- Do `Context` přidej pole `harnesses: dict[str, str] = field(default_factory=dict)`, tj. efektivní harness po krocích. Dej ho za `r5_samples`, před `state`.

### 4. `validation/runner.py`

- Do `build_parser()` přidej:
  ```python
  parser.add_argument("--roster", type=Path, default=None, metavar="DIR",
      help="replace the template's .factory/sssf.config.yaml and .factory/workflows/simple-sdlc.yaml "
           "with DIR/sssf.config.yaml and DIR/workflows/simple-sdlc.yaml (relative to the HAIFA root)")
  ```
- V `main()` uvnitř prvního `try` (před preflightem, aby se nic nespustilo zbytečně) vyhodnoť `roster = resolve_roster(args.roster) if args.roster else None`. Při `SetupError` vrať exit 2 jako dnes.
- `setup_local(workdir, roster)` a `setup_github(workdir, owner_name, moment, roster)`.
- Po setupu, ve stejném `try`, spočítej `harnesses = step_harnesses(sandbox.repo)`. Dělej to vždy, i bez `--roster`, protože R1 a R10 z mapy čtou očekávání. Když roster neprojde, spadne to jako chyba přípravy (exit 2, úklid workdir jako dnes).
- `Context(..., r5_samples=args.r5_samples, harnesses=harnesses)`.
- Do `summary` přidej klíče:
  - `"roster": str(roster) if roster else None`;
  - `"harness_per_step": harnesses`.

  Existující test kontroluje jen jednotlivé klíče, přidání mu nevadí.
- Do stderr výpisu `[validate] {remote}: repo …` přidej `roster …`, když je zadaný (nepovinné).
- Exit kód nech: `EXIT_FAILED if any(r.outcome == FAILED ...) else EXIT_OK`.

### 5. `validation/scenarios.py`

Pomocná funkce:

```python
def _roster_gap(res: ScenarioResult, why: str) -> ScenarioResult:
    """The roster cannot show what the scenario verifies: inconclusive unless a kept check failed."""
    if all(c.ok for c in res.checks):
        return res.inconclusive(why)
    res.observe(why)
    return res
```

Zdůvodnění: `inconclusive` nahrazuje jen `failed` způsobené chybějícím harnessem. Skutečná chyba (běh neprošel, chybí PR, špatné pořadí fází) zůstává `failed`.

**R1:**
- Odstraň `HARNESS_OF_PHASE`. Očekávaný harness fáze ber z `harness_of_phase(ctx.harnesses, start["phase"])`. Pro výchozí šablonu dává mapa stejné hodnoty jako dnešní konstanta, takže se chování bez `--roster` nemění. Nahraď i `ALIASES`/`_harness` kanonizací (můžeš nechat `_harness`, ale mapuj přes `haifa_proto.harness.ALIASES`).
- Na začátku (po `ScenarioResult(...)`) spočítej `mix = set(ctx.harnesses.values())` a `missing = sorted({"claude", "codex", "pi"} - mix)`.
- Task spusť vždy a checky `run_ok`, `pr_opened`, `phase_order` a `all_phases_ok` i `measurements` nech beze změny.
- Check `harness_per_phase`:
  - `missing` prázdné: check jako dnes (každá fáze na harnessu podle rosteru a `{"claude","codex","pi"} <= used`);
  - `missing` neprázdné: check **nepřidávej**. Místo toho zaznamenej `measurements["harness_per_phase"]` jako dnes a na konci funkce (před `return res`, po observacích a `trace_files`) vrať `_roster_gap(res, f"roster nemá v workflow harness {', '.join(missing)}: R1 (claude, codex i pi v jednom workflow) nejde ověřit; harness po krocích: {ctx.harnesses}")`.
- Early return `if not run_id: return res` nech. Bez run_id je `run_ok` false, takže výsledek je správně `failed`.

**R10:**
- `on_codex = ctx.harnesses.get("build") == "codex" and ctx.harnesses.get("fix") == "codex"`.
- Task (`variant="slugify_with_repair"`) spusť vždy. `ctx.state["R10"]` nastav jako dnes.
- Když `not on_codex`:
  - ponech `run_ok`, `measurements`, a pokud proběhl fix, i `test_failed_first` a `test_passed_after_fix`;
  - vynech `fix_ran_on_codex`, `same_session` a `thread_resumed` a vynech i local observaci o codex resume;
  - když fix neproběhl: na githubu zůstane dnešní `inconclusive` („model prošel testy napoprvé…“). V local nepřidávej failing check `fix_ran_on_codex`, jen jdi na `_roster_gap`;
  - `trace_files.append(builder/raw_output.jsonl)` nech;
  - vrať `_roster_gap(res, f"build běží na {ctx.harnesses.get('build')}, fix na {ctx.harnesses.get('fix')}, ne oba na codexu: R10 (opravné kolo v Codex threadu) nejde ověřit")`.
- Když `on_codex`: beze změny.

Docstring modulu a README doplň o větu, že roster bez potřebných harnessů dává R1/R10 `inconclusive`.

### 6. `validation/README.md`

- Do seznamu přepínačů přidej `--roster DIR`. Uveď:
  - které dva soubory nahrazuje;
  - že relativní cesta se bere od kořene HAIFA;
  - že roster musí mít agenty `planner`, `builder`, `reviewer` a `documenter`;
  - že R1 a R10 hlásí `inconclusive`, když roster nemá, co ověřují.
- U R1/R10 v tabulce scénářů zmiň, že očekávané harnessy se berou z rosteru.
- Piš česky, s diakritikou.

### 7. Testy

**Nový test v `prototype/tests/test_validation_roster.py`.** `tests/test_validation_local.py` se nesmí měnit. Obsah:

1. Unit testy (rychlé, bez `just`):
   - `step_harnesses` na materializované výchozí šabloně (`sandbox.materialize(tmp, "main", "local")`) vrátí `{"plan": "claude", "build": "codex", "fix": "codex", "review": "pi", "revise": "codex", "document": "claude"}`;
   - `harness_of_phase(h, "fix_2") == "codex"`, `harness_of_phase(h, "review_1") == "pi"`, `harness_of_phase(h, "retest") is None`;
   - `resolve_roster` na adresáři bez `workflows/simple-sdlc.yaml` vyhodí `SetupError`;
   - `apply_roster` přepíše oba soubory;
   - `_roster_gap`: se samými ok checky vrátí `inconclusive`, s jedním neok checkem `failed`.
2. E2E test `test_proto_validate_local_roster_without_codex(tmp_path)`:
   - stejná kostra jako `test_proto_validate_local` (tripwire, env, `skipif just`, `timeout=300`). Kostru zkopíruj, neimportuj z druhého testovacího modulu;
   - roster vygeneruj z šablony, ať se nerozjede:
     - `cfg = (TEMPLATE_DIR/".factory/sssf.config.yaml").read_text()` a v něm `"coding_agent: codex\n    model: gpt-5.5"` → `"coding_agent: claude\n    model: sonnet"`;
     - workflow: `(TEMPLATE_DIR/".factory/workflows/simple-sdlc.yaml").read_text().replace("harness: codex", "harness: claude")`;
     - `assert "codex" not in` obou textů po odstranění komentářů. Komentáře v YAML codex zmiňují, takže kontroluj parsované hodnoty: `yaml.safe_load` → žádný `coding_agent == "codex"` a žádné `harness: codex` v krocích. Jednodušší je kontrola `"harness: codex" not in wf and "coding_agent: codex" not in cfg`;
     - zapiš do `tmp_path/"roster"/sssf.config.yaml` a `tmp_path/"roster"/workflows/simple-sdlc.yaml`;
   - spusť `just proto-validate --remote local --roster <abs> --results-dir … --workdir …`;
   - ověř:
     - `proc.returncode == 0`, tedy `inconclusive` nezpůsobí nenulový exit;
     - `summary["results"] == {"R1": "inconclusive", "R10": "inconclusive", "R2": "passed", "R3": "passed", "R4": "passed", "R5": "passed"}`;
     - `summary["roster"]` končí na `roster`;
     - `summary["harness_per_step"]["build"] == "claude"`;
     - v `R1.json` není check `harness_per_phase`;
     - v `R10.json` není check `fix_ran_on_codex`;
     - všechny checky v R1 a R10 jsou `ok`;
     - observace R1 zmiňuje `codex`;
     - `not marker.exists()`.
   - Jestli E2E běží dlouho (dnešní local test je v řádu desítek sekund až minut), je to přijatelné. Nepřidávej `--only`, protože R3 a R4 potřebují R1 a R10.
3. Test, že `failed` dává nenulový exit, aby „failed ano“ z Done bylo pokryté. Stačí unit test bez subprocessu:
   - monkeypatchni v `validation.runner` `ORDER` na jeden scénář, který vrátí `ScenarioResult` s neok checkem, a druhý, který vrátí `inconclusive`;
   - `setup_local` nech skutečný a `step_harnesses` nech běžet na šabloně;
   - `main(["--remote","local","--results-dir",str(tmp/"r"),"--workdir",str(tmp/"w")])` vrátí `1`; se samými `inconclusive` vrátí `0`.

   `runner` importuje `ORDER` přímo (`from validation.scenarios import ORDER`), takže patchni `validation.runner.ORDER`. `main` potřebuje `just` na PATH, proto test označ `skipif(shutil.which("just") is None)`. Pokud už `tests/test_validation_unit.py` podobný test obsahuje, doplň ho tam (nový soubor není povinný).

Ruff: dodrž styl projektu (line length podle `pyproject.toml`, `from __future__ import annotations`). Mypy: všechny nové funkce plně typované.

## Ověření

Z kořene HAIFA:

```
just test tests/test_validation_roster.py
just test tests/test_validation_local.py tests/test_validation_template.py tests/test_validation_unit.py
just test
just typecheck
just lint
git diff --stat -- vendor/ prototype/tests/test_validation_local.py prototype/validation/template/   # musí být prázdné
```

Ručně (nepovinné):
- `just proto-validate --remote local --roster /nonexistent` → exit 2 a hláška o chybějícím rosteru;
- `just proto-validate --remote local` → všech šest `passed`.

## Soubory

- nový: `prototype/validation/roster.py`, `prototype/tests/test_validation_roster.py`
- upravit: `prototype/validation/runner.py`, `sandbox.py`, `context.py`, `scenarios.py`, `README.md`
- `justfile`: jen komentář u `proto-validate` (volitelné)
- neměnit: `vendor/`, `prototype/validation/template/`, `prototype/tests/test_validation_local.py`
