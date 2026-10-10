---
id: HAIFA-S10-T03
title: Jedna kořenová složka dokumentů factory
status: todo
depends_on: []
---

## Zadání
Repo má jediné nastavení složky: kořen dokumentů factory (klíč `docs_root`; výchozí název navrhne plán, např. `factory/`). Pod ním jsou podadresáře `backlog/`, `specs/`, `docs/` a v každém struktura `projekt/step/task`: spec úkolu je `specs/<projekt>/<step>/<task-id>-<slug>.md`, dokumentace `docs/<projekt>/<step>/<task-id>-<slug>.md`.

Kde: `aifactory/src/aifactory/config/settings.py` (ProjectSettings), `backlog/` (loader, derived: per-kontejnerové `specs_dir`/`docs_dir`/`workdir` zrušit), `run/scope.py` (output_paths), `library/install*.py`, `web/settings.py` a UI nastavení (`SettingsForm.vue`, `ProjectSettings.vue` zrušit), skill.md.

Hotovo znamená:
- V `.factory/config.yaml` je jediné nastavení složky; `backlog_dir`, `backlog_dirs`, `specs_dir`, `docs_dir` a per-projektová nastavení složek zmizí (staré klíče se při čtení tiše ignorují nebo převedou, ne chyba).
- Spec a dokumentace úkolu leží ve struktuře projekt/step pod kořenem.
- Repo HAIFA je převedené: `backlog/`, `specs/`, `app_docs/` přesunuté pod nový kořen (git mv), odkazy v backlogu a dokumentech fungují.
- `just check` a `just e2e` projdou.

Mimo rozsah: dědičnost z knihovny (HAIFA-S10-T04).

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
