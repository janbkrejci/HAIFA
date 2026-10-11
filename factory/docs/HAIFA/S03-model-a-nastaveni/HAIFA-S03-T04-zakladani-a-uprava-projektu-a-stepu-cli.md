# HAIFA-S03-T04: Zakládání a úprava projektu a stepu (CLI, API)

## Co se změnilo a proč

Projekt a step (adresář s `index.md`) se dřív zakládaly a upravovaly ručně. Teď to umí
CLI i API dashboardu a obojí volá tytéž funkce core. Zápis se nejdřív ověří na kopii
backlogu (`check_backlog`), mění jen soubory pod `backlog_dir` a nic necommituje
(commit dělá `factory backlog commit`).

## Použití

```sh
factory backlog add --id M01 --title "Jádro" --body "Datový model a API." --json
factory backlog add M01 --id M01-S03 --title "Export" --json      # backlog/M01-jadro/S03-export/index.md
factory backlog edit M01 --workflow build-test --writes src/ tests/ --test "just check" --json
factory backlog edit M01-S03 --auto-continue on --clear source target --json
```

- Kód odpovídá vzoru id tasků (`^[A-Za-z0-9][A-Za-z0-9._-]*$`, jinak `invalid_id`), je
  jedinečný (jinak `backlog_invalid` s issue `duplicate_id`) a kód stepu začíná kódem
  projektu a `-` (jinak `backlog_invalid` s `id_prefix`). Nic se nezapíše.
- Adresář je `<kód>-<slug>` (slug z názvu); step zahodí prefix projektu jako stávající
  backlog (`M01-S03` -> `S03-export`).
- `edit` mění název a nastavuje nebo maže (`--clear`) klíče `workflow`, `writes`, `test`,
  `source`, `target`, `specs_dir`, `docs_dir`, `auto_continue`. Ostatní klíče (např.
  `owner`) i popis zůstávají beze změny. `--test` s jedním argumentem uloží řetězec,
  s více seznam.
- `--json` vrací `{action, changed, path, container, issues}`; `container` je detail níže.

## API

- `GET /api/backlog/containers/{id}` – `{container, editable_keys, issues}`.
- `POST /api/backlog/containers` – `{parent?, id, title, body?}`.
- `POST /api/backlog/containers/{id}/edit` – `{title?, workflow?, writes?, test?, source?,
  target?, specs_dir?, docs_dir?, auto_continue?, clear?}`; `null` u klíče ho smaže.
- Neplatný zápis: `backlog_invalid` (HTTP 422), `invalid_id`/`invalid_value`/`no_changes`
  (400), `unknown_container` (404), `file_exists` (409).

Detail (`container`): `id`, `title`, `level`, `path`, `index_path`, `parent`, `children`,
`body` (popis), `own` (zděděné klíče v `index.md`), `extra` (ostatní klíče) a `effective`:
pro každý zděděný klíč `{value, origin}`. `origin` je
`{source: own|inherited, level, id, path}` (úroveň, která hodnotu dává),
`{source: config, path: ".factory/config.yaml", key}` (`test_command`, `test_timeout`,
`specs_dir`, `docs_dir`), `{source: default}` (nenastavené `auto_continue`/`auto_merge` =
`false`) nebo `null`.

## Kde to je

- `aifactory/src/aifactory/backlog/edit.py`: `add_container`, `edit_container`,
  `find_container`, `CONTAINER_KEYS`.
- `aifactory/src/aifactory/backlog/taskfile.py`: `new_index_text`.
- `aifactory/src/aifactory/backlog/derived.py`: `effective_sources`.
- `aifactory/src/aifactory/backlog/render.py`: `container_detail_json`.
- `aifactory/src/aifactory/cli.py`: `factory backlog add|edit`.
- `aifactory/src/aifactory/web/backlog.py`, `web/app.py`: endpointy výše.
- `aifactory/src/aifactory/skill/skill.md`, `commands.py`, `codes.py`: postup „Plan ->
  backlog“, `[PARENT]` v usage, význam `file_exists`.
- Testy: `aifactory/tests/backlog/test_backlog_container_edit.py`,
  `aifactory/tests/web/test_web_backlog_containers.py`.
