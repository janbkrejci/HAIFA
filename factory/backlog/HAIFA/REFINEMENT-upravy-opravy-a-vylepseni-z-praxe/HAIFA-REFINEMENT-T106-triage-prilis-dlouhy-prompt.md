---
id: HAIFA-REFINEMENT-T106
title: Triage follow-upů selhává na příliš dlouhém promptu u velkého backlogu
status: done
archived: true
depends_on: []
writes: [aifactory/src/aifactory/run/triage.py, aifactory/tests/run/]
---

## Zadání
Triage následných úloh (`aifactory/src/aifactory/run/triage.py`) na NEO_HEF od 2026-11-05 selhává pokaždé (8 z 8 sezení `.factory/data/triage/triage-*`). Model odpoví „Prompt is too long“, triager pak nevrátí `TriageOutput` JSON a následné úlohy se zakládají bez porovnání s backlogem. Důsledek: například ROB-TODO-T122 vznikla, přestože ji běh ROB-S11-T003 sám splnil, a factory ji zbytečně spustila.

Příčina: `context()` posílá do promptu všechny todo tasky celého backlogu bez ohledu na projekt nebo krok, každý s tělem až `BODY_LIMIT = 6000` znaků, a celkovou velikost nijak neomezuje. NEO_HEF má přes 500 todo tasků v několika projektech (MAT, ROB, UIR…).

Co udělat:
- Omezit kandidáty, které `context()` posílá: přednostně tasky stejného projektu jako hlášené follow-upy a jejich závislosti, pak ostatní.
- Zavést celkový rozpočet velikosti promptu. Když se kandidáti nevejdou, zkrátit těla (nejdřív u vzdálenějších tasků) a případně poslat jen id a titulek. Do kontextu přidat příznak, že seznam je zkrácený.
- Když triage selže, zalogovat důvod (včetně textu odpovědi modelu) tak, aby byl vidět v trace a na dashboardu, ne jen „no JSON object found“.

Mimo rozsah: změna logiky rozhodování triageru, změna formátu `TriageOutput`.

Hotovo znamená:
- Test v aifactory/tests/run/: backlog s 600 todo tasky po 6000 znacích dá kontext pod nastaveným rozpočtem a tasky stejného projektu jsou v něm celé.
- Test: selhání triageru s odpovědí „Prompt is too long“ zapíše tuto odpověď do chyby fáze.
- Stávající testy triage procházejí.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-08 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/203 · náklady $0.00
