---
id: HAIFA-S01-T42
title: "Backlog: dávka tasků i s novým projektem"
status: done
archived: true
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/backlog/edit.py, aifactory/src/aifactory/backlog/__init__.py, aifactory/tests/backlog/test_backlog_batch.py]
---

## Zadání
## Zadání

Nový záměr bude umět navrhnout i nový projekt. Proto `add_batch` v `aifactory/src/aifactory/backlog/edit.py` musí umět ověřit a zapsat celý nový projekt najednou: projekt, jeho nový step a tasky. Dnes umí jen tasky do existujícího stepu (`step=`) nebo nový step existujícího projektu (`project=` + `step_code`/`step_title`/`step_body`).

1. `add_batch` dostane nové keyword parametry `project_code`, `project_title` a `project_body` (výchozí `None` / `""`). Nový projekt dostane `project_code` s `project_title` a k tomu `step_code` a `step_title` jeho prvního stepu. V tomto režimu je `project` i `step` `None`. Kombinace `project_code` s `project` nebo `step` skončí `conflicting_options`.
2. Id, adresář a `index.md` nového projektu vzniknou stejně jako u `add_container(root, None, …)`: `compose_id`, slug, kořen backlogu včetně samostatných kořenů projektů z HAIFA-S03-T07. Společnou logiku vytáhni do pomocné funkce a nepiš ji podruhé. Kontroluje se `duplicate_id` projektu, `file_exists` jeho adresáře a neprázdný titulek (`invalid_value`). Všechny problémy se sbírají spolu s problémy stepu a tasků a vyhodí se najednou jako `backlog_invalid`.
3. Celá dávka se ověří na kopii backlogu stejně jako dnes. Bez `write` se nic nezapíše. S `write` se zapíše `index.md` projektu, `index.md` stepu a soubory tasků. Nic se necommitne.
4. `BatchResult` dostane pole `project_id`, `project_title`, `project_body`, `project_path` a `new_project` (bool). Pro existující step i existující projekt se vyplní nadřazený projekt a `new_project=False`. V backlogu bez úrovně projektu zůstanou pole prázdná (`""`). Stávající volající (`workflow/propose.py`, `web/intent.py`) fungují beze změny.
5. Backlog s méně než třemi úrovněmi (bez úrovně projektu) odmítne `project_code` s chybou `invalid_value`.

Mimo rozsah: propose, CLI, dashboard.

Hotovo znamená:
- Nový test `aifactory/tests/backlog/test_backlog_batch.py` pokrývá:
  - náhled (`write=False`) i zápis nového projektu se stepem a tasky,
  - odmítnutí duplicitního id projektu a existujícího adresáře,
  - odmítnutí prázdného titulku,
  - `conflicting_options`,
  - odmítnutí v backlogu bez úrovně projektu,
  - že u existujícího stepu a projektu jsou pole projektu v `BatchResult` vyplněná.
- `just lint`, `just typecheck` a `just pytest tests/backlog/ tests/workflow/test_backlog_propose.py` projdou.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-17 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/101 · náklady $1.32
