---
id: HAIFA-S05-T04
title: "Manifest repa, stavy položek a brána formátu"
status: done
depends_on: [HAIFA-S05-T03]
---

## Zadání
Přidej do `.factory/` manifest s původem každé položky a se značkou onboardingu, stavy položek proti knihovně a bránu formátu pro běhy. Repo bez manifestu (formát 0) běží beze změny. Repo s manifestem bere workflow jen ze své kopie, aby tentýž task běžel na každém stroji stejně (D32).

Where: `aifactory/src/aifactory/config/` (`loader.py`, `source.py`, `status.py`, `run.py`), `aifactory/src/aifactory/run/task.py` (`named_workflow`, `run_task`), `aifactory/src/aifactory/library/` (z L1 a L2), `aifactory/src/aifactory/cli.py`, `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/config/`, `aifactory/tests/run/` a `aifactory/tests/library/`.

Done means:
- `.factory/manifest.yaml` má `format` (1), `written_by`, `library` (`id`, `name`, `remote`, nebo null), `onboarding` (`source` `init`, `sssf` nebo `pre_library`, `source_commit`, `at`, `by`, `factory`, `library_commit`) a `items` po typech (`agents`, `workflows`, `skills`, `extensions`, klíč je jméno v repu, hodnota `{item, version}`). Model, čtení a zápis manifestu jsou funkce pro další úkoly.
- `load_config` manifest načte, manifest je ve `SHARED_FILES` (varování D4 a `config_changes`) a ve `FactoryConfig.digest`. `format` vyšší než podporovaný vrátí chybu `format_unsupported` se zprávou o nainstalované verzi a příkazu `factory upgrade`, takže běh skončí před startem.
- V repu s manifestem bere `named_workflow` workflow jen z `.factory/workflows/` v base, interní `resolve` z balíčku. Chybějící workflow dá `unknown_workflow` s opravou `factory config add workflow <jméno>`. Repo bez manifestu má dnešní fallback na balíček.
- Stavy podle R (hash kopie), M (verze v manifestu), L (hlava knihovny, bez knihovny semínko) a H (historie položky): `local`, `missing`, `synced` (R = L), `unknown` (M není v H), `outdated`, `modified` a `diverged`, vyhodnocené v tomto pořadí.
- `factory config items [--repo] [--base] --json` vrátí pro každou položku stav, verze R, M a L a položku knihovny. Bez `--base` porovná pracovní strom.
- `factory --skill` popisuje manifest a stavy. Nové kódy jsou v `skill/codes.py`.
- Testy (pytest): repo bez manifestu beze změny chování, formát 2 odmítnut před startem běhu, každý stav nad dočasnou historií knihovny, semínko bez knihovny, varování D4 pro manifest, workflow jen z repa a `resolve` z balíčku.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: zápis manifestu příkazy (init, onboard, add), skilly v bězích, aktualizace, dashboard.

Pevná omezení:
- `.factory/` repa HAIFA se nemění.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/51 · náklady $2.88
