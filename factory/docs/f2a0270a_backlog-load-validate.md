# Načtení a validace backlogu HAIFA

`haifa-proto` teď umí načíst backlog uložený jako strom adresářů s markdown soubory, zkontrolovat ho a vypsat se stavy odvozenými ze závislostí. Jde jen o čtení: nic se nezapisuje zpět do souborů a „blokuje“ se počítá pouze v paměti.

## Co změna dělá

- **Konfigurace** (`config.py`): čte `<repo>/.factory/config.yaml`, konkrétně klíče `levels` (výchozí `[module, step, task]`) a `backlog_dir` (výchozí `backlog`). Pokud soubor nebo klíč chybí, použijí se výchozí hodnoty. Neplatná konfigurace vyhodí `ConfigError`. To nastane u YAML, který není mapa, u `levels` s méně než 2 položkami nebo s duplicitní či prázdnou položkou a u absolutní cesty v `backlog_dir`.
- **Načtení** (`backlog.py`, `load_backlog`): každý adresář kontejneru (modul, step) má `index.md` s YAML hlavičkou `id` a `title`. Kontejner může mít i dědičné klíče `owner`, `source`, `target`, `test`, `workflow` a `auto_continue`. Task je `.md` soubor v adresáři poslední úrovně kontejnerů. Jeho hlavička obsahuje `id`, `title`, `status` a seznamy `depends_on`, `related` a `writes`.
- **Dědičnost** (`effective`): hodnoty se skládají od nejvyššího předka dolů, bližší kontejner přepisuje vzdálenější a vlastní hodnota tasku má přednost před všemi.
- **Odvozené stavy** (`derived_state`, `unmet`):
  - Task se stavem `done` nebo `cancelled` si stav ponechá.
  - Task `todo` je `ready`, když jsou splněné všechny závislosti, jinak `blocked` spolu se seznamem toho, co chybí.
  - Závislost na stepu (obecně na kontejneru) je splněná, když jsou hotové všechny jeho tasky kromě zrušených. Kontejner bez aktivních tasků se za hotový nepovažuje (důvod `empty`).
  - Závislost na zrušeném tasku se nepočítá jako splněná (důvod `cancelled`).
  - Neplatný `status` se ve výpisu zobrazí jako `invalid`.
- **„Blokuje“** (`blocks`): opačný směr `depends_on`, počítá se jen v paměti.
- **Validace** (`check_backlog`) hlásí chyby s těmito kódy:
  - `duplicate_id`: duplicitní id napříč tasky i kontejnery.
  - `unknown_ref`: neznámé id v `depends_on` nebo `related`.
  - `cycle`: cyklus závislostí, zpráva uvádí jeho cestu, např. `A -> B -> A`. Hledá se přes SCC v grafu, kde kontejner vede na své aktivní tasky, takže zachytí i cyklus přes step.
  - `invalid_status`: status mimo `todo`, `done` a `cancelled`.
  - `missing_index`: adresář bez `index.md`.
  - `id_prefix`: id tasku nebo stepu nezačíná na `<id předka>-` pro všechny předky.
  - Chyby zjištěné už při načítání: `invalid_frontmatter`, `missing_field`, `invalid_field`, `missing_backlog_dir`, `misplaced_file` a `misplaced_dir`.

## CLI (`cli.py`)

```
haifa-proto backlog check [--repo PATH] [--json]
haifa-proto backlog list  [--repo PATH] [--json]
```

- `--repo` určuje kořen cílového repa. Bez něj se použije aktuální adresář.
- `check` bez chyb vypíše `OK: 2 module, 3 step, 6 task` a vrátí 0. Při chybách vypíše řádky ve tvaru `cesta: kód: zpráva` a vrátí 1. S přepínačem `--json` vrací `{ok, errors[], counts}`.
- `list` vypíše strom se stavem, průběhem `[done/total]`, informací „waits for“ a „blocks“. S přepínačem `--json` vrací `{levels, backlog_dir, items[], issues[]}` a každý task v něm má `state`, `effective`, `blocked_by` a `blocks`. Vrací 1 jen tehdy, když chybí adresář backlogu. Ostatní problémy ohlásí na stderr s odkazem na `check`.
- Neplatná konfigurace vede u obou příkazů k návratovému kódu 1 a chybě `invalid_config`.
- Samotné `haifa-proto backlog` bez podpříkazu vypíše nápovědu.

## Vzorová data a testy

Vzorová data v `prototype/tests/fixtures/backlog/` obsahují 2 moduly (`M01-core`, `M02-ui`), 3 stepy a 6 tasků:

- `M01-S02-T01` závisí na stepu `M01-S01`.
- `M02-S01-T02` závisí na `M01-S02-T01`, tedy napříč moduly.
- `M01-S02-T02` je zrušený.

Fixture `sample_repo` v `conftest.py` kopie data do `tmp_path` a pomocná funkce `rewrite` v ní cíleně rozbije jeden soubor. Každá kontrola má vlastní test v `test_backlog_check.py`. Testy v `test_backlog_load.py` pokrývají stavy, dědičnost, zpětné vazby „blocks“, to, že čtení nic nezapisuje, a konfiguraci se dvěma úrovněmi. `test_cli_backlog.py` testuje CLI a `test_config.py` konfiguraci.

Změna obsahuje i specifikaci `specs/f2a0270a_backlog-load-validate.md`.

## Ověření

```
cd prototype
uv run pytest
uv run haifa-proto backlog check --repo tests/fixtures/backlog   # OK: 2 module, 3 step, 6 task
uv run haifa-proto backlog list  --repo tests/fixtures/backlog
```

Očekávaný výpis `list`, ukázka:

```
  M01-S02 API [0/1 done]
    M01-S02-T01 Endpoint  blocked (waits for: M01-S01 [M01-S01-T02])  (blocks: M02-S01-T02)
```
