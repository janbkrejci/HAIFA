---
id: HAIFA-REFINEMENT-T105
title: Kopie factory-advice se na Windows nemažou kvůli dlouhým cestám
status: done
depends_on: []
writes: [aifactory/src/aifactory/workflow/adaptive.py, aifactory/tests/workflow/test_workflow_advice.py]
---

## Zadání
Kopie repa pro doporučení workflow (`%TEMP%\factory-advice-*`, každá asi 2 GB) se na Windows nemažou a plní disk. Na stroji NEO_HEF jich za týden přibylo 20 (40 GB) a disk C klesl na 2 GB volných.

Příčina (naměřeno 2026-11-05): aifactory/src/aifactory/workflow/adaptive.py `remove_tree` volá `shutil.rmtree` s běžnými cestami. Cesty uvnitř kopie mají až 279 znaků, stroj má `LongPathsEnabled=0`, takže mazání skončí `OSError`. `advice_dir` ho ve `finally` tiše spolkne a `cleanup_orphans` při `except OSError: continue` taky. Kopie z dlouho běžícího procesu řetězu `factory task run` navíc čekají, až proces skončí, protože `_orphaned` bere jako sirotky jen adresáře mrtvého vlastníka nebo vlastního procesu, a ten čistí až při dalším doporučení, kde mazání znovu selže.

Co udělat:
- `remove_tree` na Windows maže přes prefix `\\?\` (absolutní cesta), aby prošly cesty nad 260 znaků. Read-only soubory (git objekty) dál řeší stávající handler.
- Selhání mazání v `advice_dir` a `cleanup_orphans` se zaloguje (cesta a výjimka), už se nespolkne tiše.

Mimo rozsah: zapínání `LongPathsEnabled`, změna místa nebo velikosti kopie.

Hotovo znamená:
- Test v aifactory/tests/workflow/test_workflow_advice.py: `advice_dir` smaže adresář se souborem v cestě delší než 260 znaků (na Windows; jinde se test přeskočí nebo ověří stejné chování). Test bez opravy zčervená.
- Test: `cleanup_orphans` smaže osiřelý adresář mrtvého vlastníka s takto dlouhou cestou.
- Stávající testy workflow_advice a web_system procházejí.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-05 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/202 · náklady $0.00
