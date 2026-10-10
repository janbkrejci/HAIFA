# Plán 1.9: validační scénáře prototypu (`just proto-validate`)

## Cíl

`just proto-validate [--remote local|github]` připraví testovací repo se šablonou backlogu a spustí scénáře R1, R2, R3, R4, R5 a R10 z `docs/product-brief.md` (sekce Rizika). Každý scénář zapíše JSON s výsledkem, důkazy a měřením do `prototype/validation/results/<datum>/…`. Režim `local` běží bez sítě a bez modelů (bare repo v dočasném adresáři, falešný harness). Režim `github` používá sandbox `HAIFA_SANDBOX_REPO` a skutečné harnessy. Ten spouští jen engineer ručně.

Mimo rozsah: zpráva 1.10, Azure DevOps, jakékoli změny `vendor/`. Kód v `prototype/src/haifa_proto/` se **nemění**: validace ho volá jen přes CLI (`haifa_proto.cli.main`). Pokud se ukáže, že bez změny v `haifa_proto` scénář nejde, zapiš to jako pozorování do výsledku a produkční kód neupravuj.

## Co už existuje (zjištěno průzkumem, na tom stav)

- **CLI** `haifa_proto.cli.main(argv) -> int`. Příkazy s `--repo` a `--json`:
  - `task run ID [--note --force --auto]` vrací `{ok, run, pr, pr_error, chain}`, kde `run` má `run_id, branch, state, worktree, base_sha, head_sha…`;
  - `task show ID` vrací `{task, runs[], prs[]}`;
  - `task approve ID`;
  - `task return ID --note`;
  - `backlog check|list|sync`;
  - `harness check`.

  Chyby mají tvar `{"ok": false, "error": {"code", "message"}}` a exit 1. Operace „close PR“ v HAIFA **neexistuje** (stav `closed` jde jen přečíst).
- **Běh** (`run.py`):
  - worktree `<root>/.factory/worktrees/<run_id>`, větev `factory/<task-id>-<n>`; `next_branch` hledá jen lokální `refs/heads/factory/…` a `task_runs`;
  - `run_id == sessions.adw_id`;
  - trace DB a `data_dir` jsou z hlavního checkoutu (`observability.db` a `defaults.data_dir` ze sssf configu, na který ukazuje `.factory/config.yaml: agents_config`);
  - task, backlog, workflow a `roles.yaml` se berou z commitu `base`; `.factory/config.yaml` a sssf config z pracovního stromu hlavního checkoutu;
  - relativní cesty promptů se čtou z worktree, tedy z `base`.
- **Trace**: tabulky `task_runs`, `task_prs`, `sessions`, `phases(adw_id, seq, name, kind, owner, status, attempt…)`, `events`. Řádek `events` s `type='agent_start'` má v `payload_json` hodnoty `coding_agent, session_id, model, thinking`. Tabulka `agent_sessions` je navíc.
  - Každá session má adresář `<data_dir>/sessions/<run_id>/<agent>/`, v něm `prompts/{system,user}.md` (vykreslené), `raw_output.jsonl` a `<coding_agent>_sessions/`.
  - Codex si drží stav v `<session_dir>/<session_id>.codex.json` s `thread_id`. Opravné kolo (`fix_N`) na stejném agentovi a modelu jede přes `codex exec resume`.
- **Provider local**:
  - PR je jen větev s URL `<remote>#<branch>`;
  - stav se určuje takto: chybí větev → `closed`, tip je předek base → `merged`, jinak zkušební merge → `mergeable`/`conflict`;
  - `merged_prs()` hledá větve `factory/*`, které jsou předky base. Squash merge mimo HAIFA proto lokálně **nezachytí**.
- **Provider github**: volá `gh` s cwd v checkoutu (repo podle remote). Používá `pr create/edit/view/review/merge/comment/list`. `approve` se volá jen při `require_review: true`.
- **Kódový krok `test`**: vendor `quality.run_tests` spouští `just test` v cwd worktree. Testovací repo proto potřebuje `justfile` s receptem `test`.
- **Falešný harness v testech**: `prototype/tests/workflow_fakes.py`, třídy `FakeHarness` a `_no_real_harness`. Vkládá se do `agents.INTERFACES` pro `claude`, `codex`, `pi` a `claude_code`. `workflow.ensure_harnesses()` vložené položky nepřepisuje. **Runtime přepínač mimo pytest neexistuje**, validace si ho proto zavede sama (viz worker).
- **Fáze Python `adw_simple_sdlc`** jsou v `prototype/tests/test_workflow_simple_sdlc.py`, konstanty `HEAD`/`TAIL`/`TEST_1`/`REVIEW_1`:
  - šťastná cesta: `plan, commit_plan, build, test_1, review_1, commit_build, changes, document, commit_docs` (plus úvodní `request`);
  - s opravou: `…build, test_1, fix_1, test_2, review_1…`.

## Rozložení souborů

```
prototype/validation/
  __init__.py
  __main__.py          # argparse, vstup `python -m validation`
  runner.py            # orchestrace: pracovní adresář, setup repa, pořadí scénářů, zápis výsledků, kopie trace
  sandbox.py           # materializace šablony, local bare remote, github klon + base větev, gh helpery
  worker.py            # `python -m validation.worker <argv haifa-proto>`; volitelně zapne falešný harness
  fake.py              # skriptovaný falešný harness + pojistka proti skutečným adaptérům
  fake_scripts.py      # obálky a efekty agentů per task pro --remote local
  scenarios.py         # r1 … r10: funkce vracející ScenarioResult
  results.py           # dataclassy výsledků, JSON writer, summary
  safety.py            # safe_rmtree a kontrola cest (maže jen uvnitř vlastního workdir)
  template/            # šablona testovacího repa (doslovné soubory)
  results/.gitkeep
prototype/tests/
  test_validation_template.py
  test_validation_unit.py
  test_validation_local.py     # end-to-end `just proto-validate --remote local`
```

### pyproject a lint

V `prototype/pyproject.toml`:
- `[tool.pytest.ini_options]`: přidej `pythonpath = ["."]`, aby testy uměly `import validation`;
- `[tool.mypy] files = ["src", "tests", "validation"]`;
- ruff `src = ["src", "tests", "validation"]`.

Soubory v `validation/template/**` jsou data, ne kód projektu. Vynech je z mypy (`exclude = ["validation/template/"]`) i z ruff (`extend-exclude = ["validation/template"]`), protože obsahují vlastní `tests/` a sandbox kód.

### justfile

Do sekce `# ── prototype`:

```
# validation scenarios R1–R5, R10: just proto-validate --remote local|github
proto-validate *ARGS:
    cd prototype && uv run python -m validation "$@"
```

`set dotenv-load` už je nahoře, takže `HAIFA_SANDBOX_REPO` z `.env` projde. `__main__` navíc zavolá `dotenv.load_dotenv(<repo root>/.env)` bez přepisu, pro případ přímého spuštění.

### .gitignore (kořen)

Přidej `prototype/validation/results/*/local-*/`. Lokální běhy jsou šum. Výsledky z githubu se commitují pro 1.10.

## CLI `python -m validation`

Argumenty:
- `--remote {local,github}`, výchozí `local`;
- `--results-dir PATH`, výchozí `prototype/validation/results`, odvozené z `Path(__file__).parent / "results"`;
- `--workdir PATH`, výchozí `tempfile.mkdtemp(prefix="haifa-validate-")`;
- `--keep-workdir`: bez něj se na konci smaže workdir, ale jen ten, který skript sám vytvořil;
- `--only R1,R3,…`: podmnožina. Závislé scénáře, kterým chybí předpoklad, skončí `inconclusive` s pozorováním;
- `--r5-samples N`, výchozí 3.

Kódy návratu:
- 0: všechny spuštěné scénáře `passed` nebo `inconclusive`;
- 1: aspoň jeden `failed`;
- 2: chyba přípravy (chybí `HAIFA_SANDBOX_REPO`, `gh auth status` selže, `haifa-proto harness check --json` v režimu github není ok, `just` není na PATH).

Výstupní adresář: `<results-dir>/<YYYY-MM-DD>/<remote>-<HHMMSS>/`, obsahuje:
- `R1.json`, `R2.json`, `R3.json`, `R4.json`, `R5.json`, `R10.json`;
- `summary.json` s poli remote, sandbox repo, base větev, HAIFA `git rev-parse HEAD`, start a konec, výsledky a cesta k workdir;
- `trace/`: kopie `sssf.db` (přes `sqlite3` backup API, kvůli WAL) a `sessions/<run_id>/` všech běhů, na které výsledky odkazují.

Cesty v důkazech jsou relativní k tomuto adresáři (např. `trace/sessions/<id>/builder/raw_output.jsonl`), takže přežijí smazání workdir.

## JSON výsledku scénáře (`results.py`)

```json
{
  "scenario": "R2",
  "risk": "Paralelní běhy mění stejné soubory a PR kolidují",
  "remote": "local",
  "outcome": "passed | failed | inconclusive",
  "started_at": "ISO", "ended_at": "ISO", "duration_s": 12.3,
  "checks": [{"name": "both_prs_opened", "ok": true, "detail": "..."}],
  "observations": ["volný text, co jsme viděli, včetně omezení prototypu"],
  "evidence": {
    "run_ids": ["ab12cd34"],
    "prs": [{"task_id": "...", "branch": "...", "url": "...", "state": "..."}],
    "commits": ["sha"],
    "trace": {"db": "trace/sssf.db", "sessions": ["trace/sessions/ab12cd34"], "files": []}
  },
  "measurements": {}
}
```

- `outcome` je `passed`, když jsou všechny checks ok, a `failed`, když některý není. `inconclusive` nastaví scénář výslovně jen tehdy, když ověření nešlo provést. Příklady: v režimu github model nespustil opravné kolo, chybí předpoklad z dřívějšího scénáře. Pravidlo zapiš jako docstring v `results.py` (pro 1.10 je to „prošel / selhal / pozorování“).
- Výjimka uvnitř scénáře nesmí shodit celý běh: `runner` ji chytí, zapíše `failed` s tracebackem v `observations` a pokračuje dalším scénářem.

## Šablona testovacího repa (`validation/template/`)

Malý Python projekt jen se stdlib: 2 moduly, 3 stepy, 6 tasků, každý na desítky řádků.

```
README.md
.gitignore                     # .factory/data/, .factory/worktrees/, __pycache__/
justfile                       # test: python3 -m unittest discover -s tests -t . -q
src/sandbox/__init__.py
src/sandbox/mathx.py           # __all__: list[str] = []   (sdílený soubor R2, jeden řádek, který oba tasky mění)
src/sandbox/text.py            # prázdný modul s docstringem
src/sandbox/cli.py             # minimální main(argv) -> int, vrací 0
tests/__init__.py
tests/test_mathx.py            # testy clamp/lerp se skipUnless(hasattr(mathx, "clamp"/"lerp"))
tests/test_text.py             # testy slugify/truncate se skipUnless(hasattr(...))
tests/test_cli.py              # testy greet/--version se skipUnless
.factory/config.yaml.tmpl      # vykreslí sandbox.py (base, git_provider)
.factory/sssf.config.yaml.tmpl # roster čtyř agentů (vykreslí sandbox.py: data_dir/db relativně)
.factory/workflows/simple-sdlc.yaml
backlog/M01-core/index.md
backlog/M01-core/S01-math/index.md
backlog/M01-core/S01-math/M01-S01-T01-clamp.md
backlog/M01-core/S01-math/M01-S01-T02-lerp.md
backlog/M01-core/S02-text/index.md
backlog/M01-core/S02-text/M01-S02-T01-slugify.md
backlog/M01-core/S02-text/M01-S02-T02-truncate.md
backlog/M02-cli/index.md
backlog/M02-cli/S01-commands/index.md
backlog/M02-cli/S01-commands/M02-S01-T01-greet.md
backlog/M02-cli/S01-commands/M02-S01-T02-version.md
```

Testy v base musí být zelené, proto každý test funkce, kterou teprve přidá task, se přeskočí, dokud funkce neexistuje. `sys.path` na `src` nastav v `tests/__init__.py`.

**Tasky** (všechny `status: todo`, `workflow: simple-sdlc` zděděné z `index.md` modulu):

| id | co | writes | poznámka |
|---|---|---|---|
| M01-S01-T01 | `clamp(x, lo, hi)` v `mathx.py`, přidat `"clamp"` do `__all__` | `[src/sandbox/mathx.py, tests/test_mathx.py]` | R2, stejný soubor |
| M01-S01-T02 | `lerp(a, b, t)` v `mathx.py`, přidat `"lerp"` do `__all__` | totéž | R2, stejný soubor |
| M01-S02-T01 | `slugify(text)` v `text.py`: „lowercase, mezery na pomlčky“ | `[src/sandbox/text.py, tests/test_text.py]` | R10. Test v base navíc čeká odstranění diakritiky a interpunkce (`"Příliš žluťoučký kůň!" -> "prilis-zlutoucky-kun"`). Skrytý požadavek vyvolá opravné kolo. Zadání o testech mlčí |
| M01-S02-T02 | `truncate(text, n)` s `…` | totéž | R3: vrácení a zavření PR |
| M02-S01-T01 | příkaz `greet NAME` v `cli.py`, používá `slugify` | `[src/sandbox/cli.py, tests/test_cli.py]` | `depends_on: [M01-S02-T01]` (vazba přes modul), R3 a R4 |
| M02-S01-T02 | `--version` v `cli.py` čte `sandbox.__version__` | `[src/sandbox/cli.py, src/sandbox/__init__.py, tests/test_cli.py]` | R1, merge mimo HAIFA |

- Každý task má `## Zadání` s cílem, místem, významem hotovo a omezením „jen stdlib, nanejvýš 40 řádků“.
- Workflow a writes se dědí z index souborů. Writes stepu se dědí, ale task je může upřesnit. Hlavičky dej tak, aby `haifa-proto backlog check` prošel (ID prefixy `M01-S01-…`).

**`.factory/workflows/simple-sdlc.yaml`**: kopie `prototype/src/haifa_proto/defaults/workflows/simple-sdlc.yaml` beze změny struktury, jen s overrides:
- `plan: {harness: claude}`;
- `build`, `fix` a `revise: {harness: codex}`;
- `review: {harness: pi}`;
- `document` bez override (agent documenter má claude).

Přidej komentář, že jde o R1 a R10. Build i fix běží na codexu, aby opravné kolo mohlo navázat na thread. Známé omezení: build na claude a fix na codexu začne nový thread.

**`.factory/sssf.config.yaml.tmpl`**:
- agenti `planner` (`coding_agent: claude`, `model: sonnet`), `builder` (`coding_agent: codex`, `model: gpt-5.5`), `reviewer` (`coding_agent: pi`, `model: google/gemini-3.6-flash`), `documenter` (`coding_agent: claude`, `model: haiku`);
- prompty `.factory/prompts/<agent>/{system,user}.md` jako relativní cesty; `writes` podle `adws/adw_sssf_config/sssf.config.yaml` (planner `specs/`, documenter `app_docs/`);
- `protected_files: [.factory/]`, `data_dir: .factory/data`, `observability.db: .factory/data/sssf.db`.

Modely jsou levné výchozí hodnoty. Komentář v souboru řekne engineerovi, kde je změnit. Ověř, že `harness.install()` + `agents.load_config` + `workflow.preflight` šablonu přijmou: to je unit test níže (s falešnými harnessy).

**`.factory/config.yaml.tmpl`**:
- `levels`, `backlog_dir: backlog`, `base: {base}`, `git_provider: {provider}`, `merge_strategy: squash`, `require_review: false`;
- `agents_config: .factory/sssf.config.yaml`, `specs_dir: specs`, `docs_dir: app_docs`, `remote: origin`.

`require_review: false` platí i pro github, protože GitHub nedovolí schválit vlastní PR. Zapiš to jako pozorování do R3.

**Prompty**: `sandbox.materialize()` zkopíruje `adws/adw_data/prompt_engineering/{planner,builder,reviewer,documenter}/{system,user}.md` z kořene HAIFA (jen čtení) do `.factory/prompts/`. Na konec každého `user.md` připojí řádek `<!-- haifa-validate: committed prompt -->`, sentinel pro R4.

## Příprava repa (`sandbox.py`)

Společné:
- `materialize(dest, base, provider)` zkopíruje šablonu, vykreslí `.tmpl` přes `str.format` nebo `string.Template` a zkopíruje prompty.
- Hlavní checkout („main checkout“) je vždy klon uvnitř workdir: `<workdir>/repo`.

**local**:
1. `git init --bare <workdir>/remote.git`.
2. `git init <workdir>/repo`, lokální `user.name`/`user.email` (`HAIFA Validate`, `haifa-validate@example.invalid`), materializace s `base=main`, `provider=local`, commit „validation sandbox“, `remote add origin <workdir>/remote.git`, `push -u origin main`.

**github**:
1. `HAIFA_SANDBOX_REPO` přijmi jako `owner/name`, `https://github.com/owner/name(.git)` i `git@github.com:owner/name.git` a normalizuj na `owner/name`. Chybí? Exit 2.
2. Preflight: `gh auth status`, `just --version`, `haifa-proto harness check --json` (přes worker bez fake). Výstup má `ok: true`, rozhoduj podle exit kódu a pole `ok`.
3. `gh repo clone owner/name <workdir>/repo`.
4. Base je nová větev `haifa-validate/<YYYYMMDD-HHMMSS>` z `origin/main`. Na ní se materializuje šablona (`base=<ta větev>`, `provider=github`), commit a `push -u origin <base>`. **`main` sandboxu se nemění.**
5. `git fetch origin 'refs/heads/factory/*:refs/heads/factory/*'` (tolerantní k prázdnému výsledku). Tak `next_branch` uvidí čísla větví z dřívějších validací a push nové větve nenarazí na existující jméno.

Worker a scénáře vždy předávají `--repo <workdir>/repo`.

## Worker a falešný harness

`worker.py` (`python -m validation.worker <argv pro haifa-proto>`):
1. Když je v prostředí `HAIFA_VALIDATE_FAKE=<cesta ke skriptu.json>`, zavolá `fake.install(script_path)`.
2. Potom `sys.exit(haifa_proto.cli.main(argv))`.

`fake.install`:
- `harness.install()`;
- pro claude, codex a pi nahradí `harness.load(name).run` funkcí, která vyhodí `RuntimeError("validation: real harness reached")`;
- vloží `FakeHarness(name)` do `agents.INTERFACES` pro `claude`, `codex`, `pi` i `claude_code`.

Před psaním ověř, že `cli.main` ani `run_task` nevolají `harness.install()` bezpodmínečně. Podle průzkumu volají jen `ensure_harnesses()`, které vložené položky nepřepisuje. Kdyby volaly, patchni `harness.install` na no-op, který vrátí `agents`.

`FakeHarness` je vzor podle `tests/workflow_fakes.py` a testy nesmí importovat:
- `resolve_model` vrací `("fake", pattern)`, `context_window` vrací 0, `ToolCallTracker` je no-op;
- `run(request, …)` určí agenta z `Path(request.session_dir).parent.name` a vezme další položku ze skriptu `script["agents"][agent]`. Položka je `{"envelope": {...}, "writes": {"rel/path": "obsah"}}`.
- Soubory zapíše do `request.cwd`.
- Do `<script>.calls.jsonl` připíše `{harness, agent, model, thinking, cwd, session_id}`.
- Vrátí `data_types.AgentResult(text=json.dumps(envelope), returncode=0, session_id=request.session_id)`.
- Frontu drží v souboru `<script>.state.json`, protože `task return` spouští nový proces, který musí pokračovat ve frontě. Scénář místo toho pro každý subprocess zapíše nový skript. Vyber jednu variantu. Doporučení: nový skript per spuštění, bez stavu.

`fake_scripts.py` obsahuje funkce `script_for(task_id, variant)` s obálkami podle typů výstupů. Pole ověř ve `vendor/sssf/templates/adws/adw_modules/data_types.py` a vzory ber z `test_workflow_simple_sdlc.py`:
- planner zapíše `specs/<task>.md` a vrátí `ok(summary, commit_message)`;
- builder zapíše kód a vrátí `changed_files` a `commit_message`;
- reviewer vrátí `approved=True`;
- documenter zapíše `app_docs/<task>.md`.

Kód, který fake zapisuje, musí skutečně projít `just test` v šabloně. Kódové kroky (test, commit, changes) běží **skutečně** přes `EngineCodeRunner`.
- Varianta `slugify_with_repair`: build zapíše naivní slugify (test_1 selže), fix zapíše správnou.
- R2: clamp a lerp přepíšou stejný řádek `__all__` různě. Každý task také přidá funkci na konec souboru, takže konflikt nastane jistě.
- Varianta `return` pro `truncate`: druhý běh změní implementaci.

Scénáře spouštějí worker takto:

```
subprocess.run([sys.executable, "-m", "validation.worker", *argv, "--repo", repo, "--json"], cwd=<prototype dir>, env=env)
```

V režimu local má `env` nastavené `HAIFA_VALIDATE_FAKE`. JSON se parsuje ze stdoutu (narace jde na stderr). Stderr ulož do `<workdir>/logs/<n>-<cmd>.log`.

## Scénáře (`scenarios.py`)

Pořadí v `runner`: R1 → R10 → R2 → R3 → R4 → R5. Sdílený stav (run_id, PR) předávej přes objekt `Context`. Každý scénář si předpoklady ověří a při jejich chybění vrátí `inconclusive`.

Pomocné funkce:
- `db(ctx)`: sqlite3 read-only na trace DB (`<repo>/.factory/data/sssf.db`);
- `phases(run_id)`: `name, kind, owner, status, seq`;
- `agent_starts(run_id)`: join `events` s `type='agent_start'` na `phases` přes `phase_id` → `(phase, coding_agent, session_id, model, thinking)`;
- `base_status(task_id)`: `git fetch origin <base>`, pak `git show origin/<base>:<task path>` → `parse_frontmatter`;
- `pr_ops`: local nebo github implementace „merge mimo HAIFA“ a „close mimo HAIFA“.

### R1: YAML `simple-sdlc` se třemi harnessy
- `task run M02-S01-T02`, v local režimu se skriptem `happy`.
- Checks:
  - `run_ok` (`ok` a `state == succeeded`);
  - `pr_opened`;
  - `phase_order`: fáze `plan, commit_plan, build, test_1, review_1, commit_build, changes, document, commit_docs` se objeví jako podposloupnost v tomto pořadí. Konstantu `PYTHON_SIMPLE_SDLC_HAPPY` odvoď z `tests/test_workflow_simple_sdlc.py` a docstringu `vendor/sssf/templates/adws/adw_simple_sdlc.py` a zapiš ji s odkazem. V režimu github smí být navíc `fix_N`, `test_N`, `review_N` a `revise_N`;
  - `harness_per_phase`: z `agent_starts`: `plan` → claude, `build`/`fix_*`/`revise_*` → codex, `review_*` → pi. Přijmi i `claude_code` jako alias claude;
  - `all_phases_ok`: žádná fáze ve stavu failed kromě `test_N` před opravou.
- Measurements:
  - `phase_count`;
  - `duration_s`;
  - `sessions.total_tokens` a `total_cost`;
  - náklad per fáze, pokud je v `events.tokens` nebo v payloadu. Když ne, zapiš jen session.
- Pozorování: seznam fází přesně, jak proběhly, a rozdíl proti Python verzi (známý rozdíl revise_2 z komentáře v YAML).

### R10: opravné kolo na Codexu
- `task run M01-S02-T01`, v local režimu `slugify_with_repair`.
- Checks:
  - `test_failed_first` (fáze `test_1` failed nebo envelope `passed=false`, podle toho, co trace ukládá. Ověř na local běhu);
  - `fix_ran_on_codex` (`fix_1` s `coding_agent == codex`);
  - `test_passed_after_fix`;
  - `run_ok`.
- `same_session`: `session_id` u `build` a `fix_1` je stejné.
- Jen v režimu github navíc `thread_resumed`: soubor `sessions/<run>/builder/codex_sessions/<session_id>.codex.json` existuje a všechny `thread.started.thread_id` v `builder/raw_output.jsonl` jsou stejné. Předpoklad: resume nevyhlásí nový `thread.started`, případně ho vyhlásí se stejným id. Ověř na formátu fixture `tests/fixtures/harness/codex_resume.jsonl`. Pokud resume žádný `thread.started` nevydá, check je „jeden thread_id v souboru + stav codex.json“.
- V local režimu místo toho pozorování „resume codex threadu v local režimu neověřeno (falešný harness), pokrývá contract test `test_codex_correction_turn_resumes_same_thread`“.
- Když v režimu github `fix_1` vůbec neproběhl, protože model trefil testy napoprvé, outcome je `inconclusive` s pozorováním.
- Measurements: počet opravných kol, tokeny a náklad builderu.

### R2: dva paralelní tasky nad sdíleným souborem
1. Spusť `task run M01-S01-T01` a `task run M01-S01-T02` jako dva `subprocess.Popen` současně a počkej na oba.
2. Checks:
   - `both_runs_ok`;
   - `runs_overlapped`: z `task_runs.started_at/ended_at` platí `max(start) < min(end)`. Zapiš `overlap_s`;
   - `both_prs_opened`, `distinct_worktrees`;
   - `shared_file_touched`: `git diff --name-only <base_sha>..<head_sha>` obou větví obsahuje `src/sandbox/mathx.py`.
3. `task approve M01-S01-T01` → check `first_merged` (status `done` v base).
4. `task approve M01-S01-T02` → check `second_reports_conflict`: exit 1, `error.code == "conflict"`, base se nezměnil (sha `origin/<base>` před a po).
5. Pozorování: konflikt se v prototypu řeší ručně nebo rebase, workflow `resolve` neexistuje. Otevřený PR zůstává.
6. Measurements: `overlap_s` a délky obou běhů.

### R3: cesty PR a `status: done` v base
1. **Vazba přes modul**: dokud M01-S02-T01 není done, `task run M02-S01-T01` skončí exit 1 s `unmet_dependencies` (check `dependency_blocks`). Tento běh se nespustí, takže nemá náklady.
2. **Schválení v HAIFA**: `task approve M01-S02-T01` (PR z R10). Checks:
   - `approve_ok`;
   - `done_in_base`: `status: done` a řádek pod `## Běhy` s URL PR v `origin/<base>`;
   - `pr_merged` (provider status, případně `task show` → `prs[].state == merged`).
3. **Merge mimo HAIFA + sync**, PR z R1 (M02-S01-T02):
   - local: druhý klon `<workdir>/outside` z `remote.git`, `git merge --no-ff origin/<branch>`, push base;
   - github: `gh pr merge <n> --squash` v klonu (ne přes HAIFA).

   Pak `backlog sync --json`. Checks: `sync_updated` (task v `updated`), `done_in_base`, `status_before_sync == todo`.

   Pozorování pro local: squash merge mimo HAIFA lokální provider nezachytí, protože tip větve není předkem base, proto se použil `--no-ff`. Na githubu se ověřuje squash.
4. **Vrácený PR**: `task run M01-S02-T02`, potom `task return M01-S02-T02 --note "Zkrať na n znaků včetně …"`. Checks:
   - `return_new_run` (nový run_id, stejná větev);
   - `pr_updated` (head_sha se změnil, na githubu `gh pr view` ukáže stejné číslo PR);
   - `base_unchanged_after_return` (status todo).
5. **Zavřený PR**, tentýž task:
   - local: `git worktree remove` worktree běhu (v klonu ve workdir), `git branch -D <branch>`, `git push origin --delete <branch>` do bare remote ve workdir;
   - github: `gh pr close <n>`.

   Checks:
   - `approve_refused` (`task approve` → `pr_not_open`);
   - `sync_ignores_closed` (sync ho nedá do `updated`);
   - `base_unchanged_after_close`.

   Pozorování: hodnota `task_prs.state` po zavření (podle průzkumu zůstává `open`, protože HAIFA stav `closed` nikdy nezapisuje). Zapiš skutečnou hodnotu z DB.
6. Measurements: počet commitů přidaných do base na každé cestě (`rev-list --count`).

### R4: necommitnutá změna promptu
1. V hlavním checkoutu připiš na konec `.factory/prompts/planner/user.md` řádek `<!-- R4-UNCOMMITTED <uuid> -->`. Zároveň v `.factory/sssf.config.yaml` změň `thinking` planneru, třeba na `high` (necommitnuto). Check `tree_dirty`: `git status --porcelain` obě změny ukáže.
2. `task run M02-S01-T01`, bez `--force`, pokud M01-S02-T01 je done. Jinak s `--force` a pozorováním.
3. Checks:
   - `prompt_change_invisible`: vykreslený `sessions/<run>/planner/prompts/user.md` neobsahuje marker, ale obsahuje sentinel `haifa-validate: committed prompt`. Přesný název souboru s vykresleným promptem ověř ve vendor `agents.py`;
   - `run_ok`.
4. Pozorování, bez vlivu na outcome: zda se změna `thinking` v sssf configu projevila (`agent_starts` pro plan). Podle průzkumu ano, protože config se čte z pracovního stromu. Jde o nekonzistenci pro 1.10. Dále: varování před spuštěním (D4) v prototypu není.
5. Nakonec `git checkout -- <oba soubory>` v klonu.

### R5: náklad worktree
- Proveď `--r5-samples`krát v hlavním checkoutu: `git worktree add --detach <workdir>/r5/<i> origin/<base>`, změř čas (`time.perf_counter`), velikost stromu (`os.walk`, součet `st_size` bez souboru `.git`) a počet souborů, pak `git worktree remove --force <workdir>/r5/<i>`.
- Změř i velikost už existujících worktree běhů v `.factory/worktrees/*`, pokud ještě existují, a velikost `.git` klonu.
- Measurements: `add_seconds` (seznam, medián, max), `worktree_bytes`, `worktree_files`, `git_dir_bytes`, `run_worktrees` (id → bytes). Checks: `measured` a `cleanup_ok` (worktree po remove neexistuje a `git worktree list` ho nemá).
- Pozorování: sandbox je malý, čísla jsou dolní mez. Náklad buildu (.NET, `node_modules`) tu není zastoupen. Úklid po merge dělá approve (`removed_worktrees`).

## Bezpečnost mazání (`safety.py`)

`safe_rmtree(path, root)` smaže jen tehdy, když `path.resolve()` leží uvnitř `root.resolve()`, `root` vytvořil tento běh (je v registru `Context.owned_dirs`) a `path != root.parent`. Jinak vyhodí výjimku. Všechny mazací operace skriptu jdou přes něj nebo přes git příkazy v klonu uvnitř workdir. Na githubu se maže jen ve sandbox repu: zavření PR, případně větví `factory/*` a `haifa-validate/*`, které skript sám vytvořil. `main` sandboxu se nemaže ani nepřepisuje. Nikde se nepoužívá `--force` push.

## Testy (`prototype/tests/`)

Žádný test nespouští `--remote github` ani `gh`, `claude`, `codex` a `pi`.

1. `test_validation_template.py`:
   - materializuj šablonu do tmp s `base=main, provider=local` a commitni;
   - `haifa_proto.cli.main(["backlog", "check", "--repo", …, "--json"])` → ok;
   - počty: 2 moduly, 3 stepy, 6 tasků (z `backlog list --json`);
   - právě dva tasky mají v `writes` `src/sandbox/mathx.py`;
   - právě jeden task má `depends_on` na task jiného modulu;
   - každý task má `## Zadání`;
   - `workflow check .factory/workflows/simple-sdlc.yaml` → ok a obsahuje overrides claude, codex a pi;
   - v base projde `python3 -m unittest discover -s tests -t .` (subprocess);
   - `user.md` promptů obsahuje sentinel.
2. `test_validation_unit.py`:
   - `safe_rmtree` odmítne cestu mimo root a root, který nevlastní;
   - normalizace `HAIFA_SANDBOX_REPO` pro všechny tři tvary;
   - `--remote github` bez `HAIFA_SANDBOX_REPO` skončí exit 2, **dřív** než se spustí jakýkoli subprocess. Patchni `subprocess.run` a `Popen` na assert a ověř, že nebyly volány;
   - JSON writer: tvar výsledku, pravidlo pro `outcome`, výstupní cesta `<results>/<YYYY-MM-DD>/local-<HHMMSS>/`;
   - fake harness v workeru: s pojistkou vyhodí chybu při dosažení skutečného adaptéru.
3. `test_validation_local.py`, end-to-end. Když `shutil.which("just")` je None, `pytest.skip`.
   - Spustí z kořene repa `just proto-validate --remote local --results-dir <tmp>/results --workdir <tmp>/work`, případně ekvivalent `uv run python -m validation` s `cwd=prototype`, pokud by vnořený `uv` v testu dělal potíže.
   - Prostředí:
     - `HAIFA_GH=<tmp>/nogh` (neexistuje);
     - `CODEX_PATH`, `CLAUDE_CODE_PATH`, `PI_PATH` na skript, který zapíše marker a skončí 97;
     - bez `HAIFA_SANDBOX_REPO`;
     - `GIT_CONFIG_GLOBAL` zdědí z `_fast_test_env`.
   - Asserty:
     - exit 0;
     - existuje právě jeden adresář `results/<dnešní datum>/local-*`;
     - obsahuje `R1/R2/R3/R4/R5/R10.json` a `summary.json`, všechny s `outcome == "passed"`;
     - každý má neprázdné `evidence.run_ids` (kromě R5) a `measurements`;
     - cesty v `evidence.trace` existují relativně k adresáři výsledků;
     - marker skutečných harnessů nevznikl;
     - R2 má `overlap_s > 0` a check `second_reports_conflict` ok.
   - Test musí doběhnout do ~90 s. Pokud je delší, spusť ho s `--keep-workdir` a změř, kde čas utíká (typicky import enginu per subprocess), a zmenši počet subprocessů. Nesnižuj pokrytí scénářů.

## Postup implementace

1. Nastav `pyproject.toml`, `justfile` a `.gitignore`, vytvoř kostru `validation/` a `results/.gitkeep`.
2. Šablona + `sandbox.materialize` + `test_validation_template.py`. Zelené dřív, než přijdou scénáře.
3. `fake.py`, `worker.py`, `fake_scripts.py`. Ruční sonda: local repo a jeden `task run` přes worker s fake → `succeeded`.
4. `results.py`, `safety.py`, `runner.py`, `__main__.py`.
5. Scénáře v pořadí R1, R10, R2, R3, R4, R5. Po každém spusť `just proto-validate --remote local --keep-workdir` a zkontroluj JSON.
6. `test_validation_unit.py`, `test_validation_local.py`.
7. V `prototype/validation/README.md`: jak spustit oba režimy, co stojí github běh (6 tasků × simple-sdlc, 2 až 3 běhy navíc pro return a R4), kde jsou výsledky, jak číst JSON a jak po githubu uklidit PR a větve `haifa-validate/*` ručně.

## Ověření

- `just test` (celá sada, zelená, do ~2 min),
- `just typecheck` a `just lint`,
- `just proto-validate --remote local` z čistého stromu → exit 0, výsledky v `prototype/validation/results/<dnes>/local-*/`, strom repa kromě ignorovaného `local-*` čistý (`git status`), žádné zbylé `/tmp/haifa-validate-*` bez `--keep-workdir`.
- `--remote github` se **nespouští**. Stačí, že `just proto-validate --remote github` s prázdným `HAIFA_SANDBOX_REPO` skončí exit 2 se srozumitelnou zprávou (pokryto unit testem).

## Pevná omezení (opakování)

- `vendor/` a `prototype/src/haifa_proto/` se neupravují.
- Mazat jen ve workdir vytvořeném během a v sandbox repu. `main` sandboxu se nemění, nepoužívá se force push.
- Testy nikdy nevolají model, síť, `gh` ani režim github.
