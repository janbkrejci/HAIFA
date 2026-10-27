---
id: HAIFA-REFINEMENT-T96
title: "API System info: jeden disk stroje, kde běží factory"
status: todo
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/web/system.py, aifactory/tests/web/test_web_system.py]
---

## Zadání
## Zadání
Čip System info v topbaru má ukazovat jen disk a paměť stroje, na kterém běží factory, bez cest. Backend k tomu teď vrací jen seznam `volumes`, v každém svazku s cestami `paths` (domov HAIFA, temp a registrovaná repa). Z toho nejde spolehlivě poznat, který svazek je ten pravý.

Co udělat v `aifactory/src/aifactory/web/system.py`:
- `system_info(home, repos)` vrátí navíc pole `disk: {free, total, status}`. Jsou to volné a celkové místo a stav svazku, na kterém leží domov HAIFA (`home`). Pokud domov ještě neexistuje, použije se nejbližší existující nadřazený adresář, stejně jako v `_volumes`. Pole `disk` nemá žádné cesty ani id. Hodnoty, které nejde zjistit, jsou `null`, nikdy chyba.
- Celkový `status` se bude počítat jen z `disk` a `memory`.
- Pole `volumes` a `cleanup()` zůstanou beze změny, aby dál fungoval výpočet `freed_bytes` a nerozbili se stávající klienti.

Testy v `aifactory/tests/web/test_web_system.py`:
- `disk` odpovídá svazku domova a nemá klíč `paths`.
- Prahy ok a warning pro `disk` (přes monkeypatch, stejně jako stávající testy).
- Nedostupný `disk_usage` dá `free`/`total` `null`.
- Celkový `status` nezávisí na svazcích rep na jiném disku.

Mimo rozsah: UI čipu (HAIFA-REFINEMENT-T97), změny úklidu a endpointu `/api/machine/cleanup`.

Hotovo znamená:
- `GET /api/machine/system` vrací `disk` (free, total, status) pro svazek domova HAIFA, bez cest.
- `status` odpovědi vychází jen z `disk` a `memory`.
- Prochází `aifactory/tests/web/test_web_system.py`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
