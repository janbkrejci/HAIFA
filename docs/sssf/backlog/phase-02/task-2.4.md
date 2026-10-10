Implementuj konfiguraci projektu v `.factory/` podle sekcí „Architektura“ a „Dashboard / Nastavení projektu“ v `docs/product-brief.md`. Běh čte veškerou konfiguraci ze stejného commitu v `base`, ne z pracovního stromu.

Where: `aifactory/src/aifactory/config/`, CLI, `aifactory/tests/`.

Done means:
- Načte se `.factory/config.yaml` (sdílené nastavení), `.factory/local.yaml` (lokální: port, cesta k trace DB, mimo git), `.factory/agents.yaml`, `.factory/roles.yaml`, `.factory/prompts/<agent>/{system,user}.md` a `.factory/workflows/*.yaml`. Chybějící soubor má rozumný default a chybu s cestou.
- Funkce pro běh načte konfiguraci ze stromu commitu v `base` (bez checkoutu). Dva běhy spuštěné z téhož commitu dostanou stejnou konfiguraci, i když se pracovní strom mezi nimi změní.
- `factory config status [--json]` vypíše necommitnuté změny v `.factory/` proti `base`. Stejné varování vrací spuštění běhu (v `--json` jako pole `warnings`).
- Testy v dočasném git repu: necommitnutá změna promptu i `agents.yaml` se do konfigurace běhu nedostane a objeví se ve varování.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: commit konfigurace tlačítkem (dashboard, F4), spouštění běhů (2.9).

Pevná omezení:
- `.factory/local.yaml` se nikdy nečte z `base` a nepatří do gitu.
- `vendor/` a `prototype/` se nemění.
