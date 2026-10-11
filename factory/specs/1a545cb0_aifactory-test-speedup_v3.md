# Plán v3: zrychlení testové sady `aifactory` — paralelní běh bez zbytečného čekání (ověření a uzavření)

Navazuje na `specs/1a545cb0_aifactory-test-speedup.md` (v1, limity 120 s / 5 s) a
`specs/1a545cb0_aifactory-test-speedup_v2.md` (v2, limity 180 s / 10 s). Zadání se znovu změnilo:
**časové cíle se neověřují.** Stroj je souběžnými běhy přetížený (load average kolem 80 na 4 jádrech),
takže měření by nebylo férové.

## Kritéria hotovo

- `just test` projde a **běží paralelně** (pytest-xdist, výchozí `addopts`).
- Pomalé testy nečekají zbytečně (přímý git místo xcrun shimu, žádná automatická údržba gitu,
  zkrácené čekání jen parametrem nebo konfigurací).
- Počet testů ≥ 673 (před prací), 0 skipped/xfail, nic oslabeného.
- `vendor/`, `prototype/` a `aifactory/src/` beze změn. Výchozí chování CLI a `just validate` se nemění.
- Výstup `--durations=15` z **jednoho** běhu se jen vloží do souhrnu buildu, jako informace.

## Stav pracovního stromu (2026-09-28 15:18, necommitnuto)

Kroky v1/v2 jsou v pracovním stromu **už implementované** (předchozí build):

- `aifactory/pyproject.toml` a `uv.lock`: `pytest-xdist>=3.8.0`,
  `addopts = "-n auto --dist loadgroup"`.
- `aifactory/tests/conftest.py` (nový): přímý git, tichý `GIT_CONFIG_GLOBAL`, zahřátí importů a
  hook `pytest_xdist_auto_num_workers` (1,5× logických CPU). Předchozí build naměřil na 4 CPU
  6 workerů za 133 s a 4 workery za 160 s.
- `aifactory/tests/repo_templates.py` (nový) a jeho použití v `config_repo.py`, `engine_fakes.py`,
  `provider_repo.py`, `run_repo.py`, `workflow_fakes.py` a `test_validation_f2.py`.
- `aifactory/tests/engine/conftest.py` je smazaný. Fixture `engine_env` se přesunula do
  `tests/engine/engine_fakes.py` (`engine_env_fixture`) a testy v `tests/engine/*` na to mají upravené
  importy.
- Validace: `validation/runner.py` (make_context, write_results), `validation/f2.py` (fáze),
  `validation/scenarios.py` (fáze scénářů podle kroku 4f), `tests/validation/local_validation.py`
  (nový), přepsané `test_validation_local.py` a `test_validation_roster.py`.
- `pytest --collect-only -n0` hlásí **702 testů** (bylo 673).

Nový kód se nepíše. Úkolem je ověřit, případně opravit a uzavřít práci.

## Kroky pro buildera

1. **Neměnit fungující řešení.** Nepřidávat další optimalizace, neměnit počet workerů ani `--dist`,
   nehonit časy. Opravuj jen to, co v kroku 2 nebo 3 selže.
2. **Ověření** (posuzuj podle exit statusu, ne podle textu výstupu):
   - `just test --durations=15` jednou: exit 0, v hlavičce je vidět xdist (`created: N/N workers`),
     `passed ≥ 673`, 0 skipped, 0 xfailed. Výpis durations vlož do souhrnu, časy nejsou kritérium.
   - `just test -n0 -q`: projde i sériově, protože testy ve skupině `xdist_group` musí fungovat bez
     xdist. Kdyby to pod zátěží trvalo neúnosně dlouho, stačí sériově pustit aspoň
     `tests/validation tests/engine`.
   - Test puštěný samostatně musí projít, protože pomocník si doběhne předchozí scénáře a fáze:
     `just test -n0 "tests/validation/test_validation_local.py" -k "r4 or f2_final"`. Uprav `-k`
     podle skutečných názvů testů.
   - `just validate --remote local` (celý, mimo pytest): exit 0 a všech 9 scénářů `passed`. To
     dokazuje, že refaktor `runner.py`, `f2.py` a `scenarios.py` nezměnil chování.
   - `cd aifactory && uv run pytest --collect-only -q -n0 | tail -1` ≥ 673.
   - `just lint` a `just typecheck` projdou.
   - `git diff --quiet -- vendor prototype aifactory/src` vrátí exit 0.
3. **Revize, že nic není oslabené:**
   - `git diff aifactory/validation/scenarios.py aifactory/validation/f2.py`: texty `res.check`,
     `res.observe` a podmínky checků se nemění, jen se přesouvají do funkcí fází. Scénářová funkce
     prochází fáze a končí při prvním `False` stejně jako dřív. Pořadí `ORDER` je beze změny.
   - `git diff aifactory/tests/validation/`: každá aserce ze starého `test_validate_local` a
     `test_validate_local_pi_haiku_roster` má protějšek v nových testech. Patří sem outcome, checky
     R1/R10/R2/RESOLVE/B1/F2, `overlap_s`, `auto_chain`, 5 `run_ids`, 5× `merged`, souhrn (`remote`,
     `workdir_kept`, `logs`, `roster`, `harness_per_step`) a tripwire `not marker.exists()`.
     Chybějící aserci doplň.
   - Jediné `skipif` jsou dřívější podmínky `just` není na PATH. Nový `skip` ani `xfail` nesmí přibýt.
   - `git diff aifactory/tests/engine/`: změny smí jen přepojit fixture `engine_env` z odstraněného
     `conftest.py`, aserce se nemění.
4. **Commit** jedním commitem, pokud vše projde, například „Speed up aifactory test suite: parallel
   xdist run, direct git, repo templates, validation split into scenario tests“. Commitni spolu s ním
   i `specs/1a545cb0_aifactory-test-speedup*.md` (v1–v3).

## Co NEdělat

- Nesahat do `vendor/`, `prototype/` ani `aifactory/src/`. V `src/` se žádné čekání, které by se dalo
  zkrátit, nenašlo: `sleep` v providerech je injektovaný parametrem a `sleep(10)` ve validaci běží jen
  v GitHub režimu.
- Neměnit výchozí hodnoty (`UNKNOWN_DELAY`, timeouty) ani chování `just validate`.
- Neoznačovat práci za selhání kvůli naměřeným časům.
