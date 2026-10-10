# HAIFA-S07-T03: `factory upgrade`

## Cíl

`factory upgrade <BUNDLE> [--dry-run] --json` nainstaluje novější HAIFA z bundlu `haifa-<verze>.zip` (cesta, `https` nebo `file` URL).

## Návrh

- Nový modul `aifactory/src/aifactory/upgrade.py`, funkce `run_upgrade(source, dry_run)` a výjimka `UpgradeError(code, message, exit_code, data)`.
- Postup: odmítnout editovatelnou instalaci (`direct_url.json`, `dir_info.editable`), stáhnout URL do dočasné složky (jen `https`, `file`), rozbalit zip (ochrana proti `..`), ověřit každý soubor ze `SHA256SUMS`, najít jediný wheel `aifactory-*.whl` a `constraints.txt`, přečíst `Version` z `METADATA` wheelu, porovnat s `__version__` (`library.remote.version_key`), přečíst `min_factory_version` knihovny (`library.remote.library_min_factory_version`), pak bez `--dry-run` spustit `uv tool install --force <wheel> --constraints constraints.txt` v rozbaleném bundlu.
- CLI `upgrade` v `cli.py`, kódy v `skill/codes.py`, postup `### Upgrade` v `skill/skill.md`.

## Kódy

| kód | exit | kdy |
|---|---|---|
| `editable_install` | 2 | vývoj z repa, poradí `git pull` |
| `invalid_url` | 2 | URL jiného schématu než `https`/`file` |
| `download_failed` | 2 | stažení selhalo |
| `bundle_invalid` | 2 | chybí bundle, není to zip, chybí soubor |
| `checksum_mismatch` | 2 | součet neodpovídá `SHA256SUMS` |
| `up_to_date` | 1 | verze bundlu není vyšší |
| `uv_missing` | 2 | `uv` není na PATH |
| `upgrade_failed` | 1 | `uv tool install` selhal |

## Testy

`aifactory/tests/test_upgrade.py`: bundle stavěný v testu, falešný `uv` na PATH, bez sítě.
