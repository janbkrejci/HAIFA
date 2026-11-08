---
id: HAIFA-REFINEMENT-T107
title: Retry s --allow-writes nepřenese rozšířený writes do obnovené session agenta
status: done
archived: true
depends_on: []
writes: [aifactory/src/aifactory/run/, aifactory/tests/run/]
---

## Zadání
Na NEO_HEF 2026-11-08 skončil běh `0567cad5` (ROB-S12-T001) ve fázi build s `writes_needed` pro 4 skripty skillu. `factory task retry ROB-S12-T001 --allow-writes --auto` cesty správně přidal do writes tasku v base (commit 939096cbc). Builder ale obnovil svou původní session a za 40 s odpověděl: „Rozšíření writes je pouze v uživatelském zadání; nadřazený Write scope role builder stále zakazuje potřebné čtyři soubory.“ Běh skončil `invalid_output` s `cause: already_allowed_repair`. Retry s `--allow-writes` je tedy pro obnovenou session neúčinný.

Co udělat:
- Zjistit, kde obnovená session (`retry`, rejoin) bere Write scope role. Zajistit, aby po `allow_writes` dostala aktuální writes tasku ze stejného zdroje jako nová session, ne jen v poznámce k retry.
- Pokud harness neumí scope obnovené session změnit, spustit po `--allow-writes` fázi v nové session.
- Test: po `allow_writes` obsahuje scope, který dostane agent pokračující fáze, nově povolené cesty.

## Běhy

- 2026-11-08 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/204 · náklady $0.00
