# Plán v3: zrychlení testové sady prototypu — ověření a uzavření

Navazuje na `specs/e1f8b8ce_test-suite-speedup.md` (v1) a `specs/e1f8b8ce_test-suite-speedup_v2.md` (v2).
**Kroky v1 i v2 jsou implementované v pracovním stromu (necommitnuté)** a na nezatíženém stroji splňují zadání.
Nový kód se nepíše, v3 je ověření, případné drobné opravy a uzavření práce.

## Kritéria hotovo (beze změny)

- `just test` projde a celý doběhne do **120 s**.
- Žádný záznam v `just test --durations=10` není delší než **5 s**.
- Počet testů ≥ 299 (teď **301**, dva přibyly s commitem `9973a77` „Switch trace DB to WAL…“), 0 skipped/xfail,
  nic neoslabeného.
- Beze změn ve `vendor/` a `prototype/src/haifa_proto/`, výchozí chování CLI se nemění.

## Stav (změřeno 2026-09-27)

Změněné/nové soubory v pracovním stromu (všechny patří k této práci):
`prototype/pyproject.toml`, `prototype/uv.lock` (pytest-xdist, psutil, `addopts = -n auto --dist loadfile`),
`prototype/tests/conftest.py` (přímý git místo xcrun shimu, `GIT_CONFIG_GLOBAL` bez auto-maintenance,
sdílený fake `gh`, zahřátí importů, šablony repozitářů), `prototype/tests/gh_fake.py`,
`prototype/tests/repo_templates.py` (nový), `prototype/tests/task_repo.py`, `prototype/tests/workflow_fakes.py`,
`prototype/tests/test_auto_continue.py` (`_setup` přes `change_with_remote` se šablonou, obsah stejný).

| běh | zátěž stroje (load avg) | výsledek | real | nejhorší test |
|---|---|---|---|---|
| 1 | normální | 301 passed | 53 s | 3,77 s (`test_dependent_task_skipped_until_approve`) |
| 2 | normální | 301 passed | 64 s | 3,93 s (tentýž) |
| 3 | 17 (Spotlight `mds_stores`, další agenti) | 301 passed | 111 s | 9,62 s |
| 4 | 85–159 (cizí procesy: WindowServer, Orca, syspolicyd, jiné relace `claude`) | 301 passed | 204 s | 22 s |

`just lint` = 0, `just typecheck` = 0. Běhy 3 a 4 zpomalila **cizí zátěž** stroje (2 fyzická jádra):
žádný pytest ani `gh` z této sady neběžel navíc. Nejsou to regrese a nejde je vyřešit v kódu testů.

## Kroky pro buildera

1. **Neměnit fungující řešení.** Nepřidávat další optimalizace, nesnižovat počet workerů, neměnit
   `--dist loadfile`, nic neskipovat.
2. **Měřit jen na klidném stroji.** Před každým měřením `uptime`. Pokud je 1min load average > 4,
   počkej (smyčka se `sleep 10` až 10 min). Když neklesne, uveď to v reportu i s naměřenými hodnotami
   a neoznačuj práci jako selhání kvůli časům.
3. Ověření (posuzuj podle exit statusu):
   - `time just test --durations=10` **3×**: exit 0, ≥ 299 passed, 0 skipped, real < 120 s, žádný řádek > 5,00 s.
     Do reportu zapiš ke každému běhu load average, real a nejhorší test.
   - `just test -n0 -q`: sériový běh projde (čas není kritérium).
   - `cd prototype && uv run pytest --collect-only -q | tail -1` ≥ 299.
   - `just lint`, `just typecheck` projdou.
   - `git status --short`: změny jen v `prototype/tests/*`, `prototype/pyproject.toml`, `prototype/uv.lock`
     a `specs/e1f8b8ce_*`. `git diff --quiet -- vendor prototype/src` musí vrátit exit 0.
4. Rychlá revize, že nic není oslabené: `git diff prototype/tests/test_auto_continue.py` smí měnit jen
   způsob přípravy repa (`_setup` → `change_with_remote` + `_chain_backlog`). Žádná aserce se nesmí změnit.
   Šablony (`repo_templates.py`) mají fallback na původní stavbu, když session fixtura neběží.
5. Pokud vše projde, commitni práci jedním commitem (např. „Speed up prototype test suite: direct git,
   shared fake gh, repo templates, xdist“). Specs v1–v3 commitni také.

## Co NEdělat

- Nesahat do `vendor/` ani `prototype/src/`.
- Nehonit časy naměřené pod cizí zátěží dalšími úpravami kódu.
