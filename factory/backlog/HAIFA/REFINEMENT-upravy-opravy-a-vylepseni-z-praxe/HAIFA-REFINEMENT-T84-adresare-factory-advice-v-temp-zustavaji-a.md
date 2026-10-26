---
id: HAIFA-REFINEMENT-T84
title: "Adresáře factory-advice-* v %TEMP% zůstávají a zaplní disk"
status: done
depends_on: []
related: [HAIFA-REFINEMENT-T18]
writes: [aifactory/src/aifactory/web/workflow_advice.py, aifactory/src/aifactory/workflow/adaptive.py, aifactory/tests/]
---

## Zadání
Továrna po sobě nechává v `%TEMP%` adresáře `factory-advice-*`, každý zhruba 2 GB. Za den provozu jich bylo 12 a disk C: došel. Běh pak spadl na `[Errno 28] No space left on device`. HAIFA-REFINEMENT-T18 (únik dočasných adresářů) je hotová, ale tenhle únik v 0.1.482 trvá.

## Současný stav (naměřeno v NEO_HEF 2026-10-22, factory 0.1.482)

- Běh `ROB-TODO-T40` selhal na plném disku C: (0 GB volna).
- Ve `%TEMP%` leželo 12 adresářů `factory-advice-*` po asi 2 GB, nejstarší z předchozího dne. Po jejich smazání a `factory task clean` bylo volno 32,9 GB.
- Adresáře vytváří `web/workflow_advice.py` / `workflow/adaptive.py` (jediné výskyty řetězce `factory-advice`).

## Co udělat

1. Najít, kde se adresář `factory-advice-*` vytváří a proč se neuklidí (výjimka, ukončení procesu, chybějící `finally` / context manager).
2. Úklid zaručit i při pádu a při ukončení dashboardu. Staré adresáře z minulých běhů uklidit při startu `factory obs` nebo `factory task clean`.
3. Zvážit, zda kopie celého repa je pro radu (advice) potřeba. Pokud ne, použít menší výřez (navazuje na T18).

## Hotovo znamená

- Po dni provozu nezůstane v `%TEMP%` žádný `factory-advice-*` starší než běžící operace.
- Test ověří úklid při úspěchu i při výjimce.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-26 · workflow build-test-review · bez změn, běh e02e5612 · už hotovo: 9a9bb7c1a6aef4a112b96efdc8f4ab73db012b8c — Remove orphaned factory-advice temp dirs and delete read-only git files, aifactory/src/aifactory/workflow/adaptive.py — advice_dir, cleanup_orphans, remove_tree a git clone --shared, aifactory/src/aifactory/web/app.py — cleanup_orphans při startu dashboard… · náklady $0.00
