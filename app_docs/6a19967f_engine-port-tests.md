# Engine sssf přenesený do `aifactory.engine` + testy chování (R6)

## Co se změnilo a proč

Engine sssf teď žije v balíčku jako `aifactory.engine` a importuje se bez úprav `sys.path` a bez `vendor/`. Testy s falešným harnessem hlídají chování, na které spoléhá prototyp i sssf (riziko R6). Model se v testech nevolá.

- **Moduly enginu se zkopírovaly bajt po bajtu** z `vendor/sssf/templates/adws/adw_modules/` (20 souborů, `__init__.py` je prázdný). Moduly už používají jen relativní importy, takže fungují beze změny. Neupravil se ani import, ani formátování. Že se logika nezměnila, dokazuje `diff -r` proti vendoru.
- **Rozšíření z prototypu:**
  - `engine/loader.py` (z `prototype/src/haifa_proto/engine.py`) obsahuje jen `load_engine_module(name)` přes `importlib`, plus `ENGINE_PACKAGE` a `ENGINE_DIR`. Nic z prototypu, co pracovalo se `sys.path`, se nepřeneslo.
  - `engine/role_registry.py` (z `prototype/src/haifa_proto/roles.py`) má jiný název, protože `roles.py` už patří vendorovému modulu. Oproti prototypu se liší jen:
    - importem `from aifactory.engine import loader as engine`,
    - hodnotou `DEFAULTS_DIR = resources.files("aifactory.engine") / "defaults"`,
    - docstringem.

    Logika i texty chyb zůstaly stejné.
  - `engine/defaults/roles.yaml` je shodný s YAML z prototypu.
- **`aifactory/pyproject.toml`:** vendorové moduly jsou vyjmuté z kontrol:
  - v ruffu přes `extend-exclude`,
  - v mypy přes `[[tool.mypy.overrides]] ignore_errors = true`,
  - přidané je `untyped_calls_exclude = ["aifactory.engine"]`, aby typovaný kód mohl volat netypovaný engine.

  Oba seznamy vyjmenovávají moduly výslovně, bez wildcardu. `loader.py` a `role_registry.py` tak zůstávají pod strict mypy i ruffem.

## Testy (`aifactory/tests/engine/`)

**Pomocné soubory:**

| soubor | co dělá |
|---|---|
| `engine_fakes.py` | `FakeHarness` se vkládá do `agents.INTERFACES`. Vrací surové texty ze `Script`, spouští efekty agenta na repo, volá `on_spawn`/`on_exit` s pid `FAKE_CHILD_PID` a nabízí hook `during`. Dále obsahuje `build_repo`, `start`, `rows`, `agent_phase` a `events_of`. |
| `conftest.py` | Fixture `engine_env`: dočasné git repo jako cwd a config se čtyřmi agenty: `builder` (`writes: allowed/**`), `free` (bez omezení), `keyholder` (`protected.md`), `reader` (read-only). `protected_files: [protected.md]`, data a trace DB leží mimo repo. Skutečné `agent_cc.run` a `agent_pi.run` vyhodí `AssertionError`. Handlery SIGINT/SIGTERM se po testu obnoví. |

**Testované chování:**

| soubor | co ověřuje |
|---|---|
| `test_import.py` | Import všech modulů v podprocesu mimo repo. `sys.path` neobsahuje `vendor` ani `adw_modules`. `loader` vrací moduly z balíčku. |
| `test_role_registry.py` | Přenesené testy registru rolí z prototypu. Porovnávají se s `aifactory.engine.roles`. |
| `test_permissions.py` | Rollback zápisů mimo `writes` (smazání nového souboru, `git checkout` sledovaného souboru). Rollback `protected_files` i u neomezeného agenta. Uvedení chráněného souboru ve `writes` ho odemyká. Nový soubor read-only agenta se smaže. Předem rozpracovaný soubor zůstane „left as-is“. Pravidla `permitted`. |
| `test_envelope_retry.py` | Nevalidní JSON nebo špatný tvar vede k re-promptu do téže `session_id` a zapíše se do `envelopes`. JSON v code fence projde napoprvé. Po `JSON_FIX_ATTEMPTS + 1` pokusech skončí `RuntimeError`. |
| `test_gate_correction.py` | Selhaná gate vyvolá opravu v téže session. Ověřuje řádky `gate_results`, události `gate_fail`/`gate_pass` a legacy gate vracející `list[str]`. `retries=0` vede na `GateFailure`. Nevalidní JSON uvnitř opravy zůstane v téže session. `status: fail` vede na `RuntimeError`. |
| `test_sigterm.py` | SIGTERM během agenta vede na `SystemExit(128+SIGTERM)`. Řádky `processes` pro `adw` i `agent` (dítě) mají `ended_at`. Session i fáze jsou `fail`. `session.ensure` instaluje handlery. |
| `test_trace.py` | Fáze a události se zapisují do trace DB i `events.jsonl`: kódová fáze, agentní fáze a výjimka ve fázi. Pokrývá `run.finish(accepted=True/False)`, včetně výchozího důvodu, běhu bez fází a běhu s failnutou fází. Připojený běh pokračuje v `seq`. |

**Upozornění k SIGTERM:** engine při SIGTERM dětské procesy agenta sám nezabíjí. Handler v `session` jen uzavře všechny jejich řádky v `processes` a ukončí běh. Test ověřuje přesně toto chování, nic dalšího.

Plán, podle kterého se změna dělala: `specs/6a19967f_engine-port-tests.md`.

## Ověření

```bash
# logika beze změny – nesmí vypsat nic
diff -r -x __pycache__ -x loader.py -x role_registry.py -x defaults \
  vendor/sssf/templates/adws/adw_modules aifactory/src/aifactory/engine
diff prototype/src/haifa_proto/defaults/roles.yaml aifactory/src/aifactory/engine/defaults/roles.yaml

just test        # nebo: just test tests/engine
just typecheck
just lint
```

## Na co myslet

- **Vendorové moduly v `aifactory/src/aifactory/engine/` needitujte.** Jakákoli úprava rozbije důkaz přes `diff -r`. Chyby lintu a typů se u nich řeší konfigurací, ne úpravou kódu.
- **Nový modul enginu** přidejte do seznamů v `pyproject.toml` jen tehdy, když jde o kód převzatý z vendoru.
- **Mimo tuto změnu zůstaly:** harnessy claude/codex/pi, interpret workflow a napojení na `aifactory` CLI.
