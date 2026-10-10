# HAIFA-S03-T04: Zakládání a úprava projektu a stepu (CLI, API)

## Cíl

Projekt a step lze založit a upravit jejich `index.md` z CLI (`factory backlog add|edit`)
i z API dashboardu, přes tytéž funkce core. Dosud se `index.md` psal ručně.

## Návrh

### Core (`aifactory/src/aifactory/backlog/`)

- `edit.py`
  - `add_container(root, parent, container_id, title, *, body="")`: bez rodiče projekt
    (první úroveň `levels`), s rodičem step v projektu. Kód odpovídá `_ID_RE` (`invalid_id`),
    název nesmí být prázdný (`invalid_value`), rodič musí existovat (`unknown_container`)
    a smí držet podúrovně (jinak `invalid_value`). Duplicitní kód vrátí `backlog_invalid`
    s issue `duplicate_id`; kód stepu mimo prefix projektu odmítne validace (`id_prefix`).
    Adresář `<kód>-<slug>`; step zahodí prefix projektu (`M01-S03` -> `S03-<slug>`), jak
    to dělá stávající backlog. Existující adresář: `file_exists`.
  - `edit_container(root, id, *, title=None, values=None, clear=())`: změna názvu, nastavení
    nebo smazání klíčů `CONTAINER_KEYS` (`workflow`, `writes`, `test`, `source`, `target`,
    `specs_dir`, `docs_dir`, `auto_continue`). Úpravy po řádcích (`set_field`/`remove_field`),
    takže neznámé klíče a popis zůstanou. Chyby: `no_changes`, `conflicting_options`,
    `invalid_value`, `unknown_container`, `duplicate_id`, `no_index`, `backlog_invalid`.
  - `find_container` (veřejné hledání s kontrolou duplicit).
  - Zápis přes `_write_checked`: validace na kopii, jen soubory pod `backlog_dir`, nic se
    necommituje.
- `taskfile.py`: `new_index_text(id, title, body)`.
- `derived.py`: `effective_sources(node, settings)` – pro každý zděděný klíč `value` a
  `origin` (`own`/`inherited` s úrovní, id a cestou; `config` s klíčem `.factory/config.yaml`;
  `default` pro nenastavený flag; `None`). Klíče `test`, `test_timeout`, `specs_dir`,
  `docs_dir` a flagy přeskakují `null` jako `effective_test`; ostatní berou nejbližší
  úroveň s klíčem jako `effective`.
- `render.py`: `container_detail_json(backlog, container)` – název, popis, `own`, `extra`,
  `effective`.

### CLI (`cli.py`)

- `factory backlog add [PARENT] --id KÓD --title NÁZEV [--body TEXT] [--json]`
- `factory backlog edit ID [--title] [--workflow] [--writes ...] [--test ARG ...] [--source]
  [--target] [--specs-dir] [--docs-dir] [--auto-continue on|off] [--clear KEY ...] [--json]`
  (`--test` s jedním argumentem uloží řetězec, s více seznam).

### API (`web/backlog.py`, `web/app.py`)

- `GET /api/backlog/containers/{id}` – detail (`container`, `editable_keys`, `issues`).
- `POST /api/backlog/containers` – `{parent?, id, title, body?}`.
- `POST /api/backlog/containers/{id}/edit` – `{title?, <klíč>: hodnota|null, clear?: [...]}`.

### Skill

Příkazy se do `factory --skill` dostanou automaticky z argparse; postup „Plan -> backlog“
je popisuje místo ručního psaní `index.md`. `usage` volitelný poziční argument píše v `[...]`.

## Testy

- `aifactory/tests/backlog/test_backlog_container_edit.py` – core a CLI.
- `aifactory/tests/web/test_web_backlog_containers.py` – API nad dočasným git repem.
