# `factory upgrade`

Instalace novější verze HAIFA z rozeslaného bundlu jedním příkazem:

```bash
factory upgrade ~/Downloads/haifa-0.2.0.zip            # z cesty
factory upgrade https://example.com/haifa-0.2.0.zip    # z URL (jen https nebo file)
factory upgrade haifa-0.2.0.zip --dry-run --json       # jen kontrola, nic nespustí
```

Příkaz bundle rozbalí do dočasné složky, ověří `SHA256SUMS`, přečte verzi z wheelu a porovná ji s nainstalovanou. Vypíše současnou a cílovou verzi, `min_factory_version` knihovny a příkaz `uv tool install --force <wheel> --constraints constraints.txt`, který pak spustí. Pokud je cílová verze pod `min_factory_version` knihovny, přidá varování. Po úspěchu restartuj běžící dashboard (`factory obs`).

Chyby (`error.code` s `--json`):

- `up_to_date`: bundle není novější (exit 1).
- `bundle_invalid`: bundle chybí, není to zip nebo v něm chybí soubor.
- `checksum_mismatch`: soubor neodpovídá `SHA256SUMS`.
- `editable_install`: HAIFA běží z repa (vývoj), aktualizuj ho přes `git pull`.
- `invalid_url`, `download_failed`: URL má jiné schéma než `https`/`file`, nebo stažení selhalo.
- `uv_missing`, `upgrade_failed`: `uv` chybí nebo instalace selhala (exit 1, původní verze zůstává).

Kód: `aifactory/src/aifactory/upgrade.py`, testy `aifactory/tests/test_upgrade.py`.
