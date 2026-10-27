---
id: HAIFA-REFINEMENT-T94
title: "API System info: volné místo na disku, volná paměť a úklid disku"
status: done
archived: true
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/web/system.py, aifactory/src/aifactory/web/app.py, aifactory/tests/web/test_web_system.py]
---

## Zadání
Backend pro nový čip System info v topbaru. Dashboard má umět říct, kolik je volného místa na disku a volné paměti, a na požádání uklidit disk od toho, co po sobě nechala factory.

Co udělat:
- Nový modul `aifactory/src/aifactory/web/system.py`:
  - `system_info(home, repos)` vrátí, kolik místa je volné a kolik celkem (`shutil.disk_usage`) na svazcích, kde leží domov HAIFA, systémový temp (`tempfile.gettempdir()`) a registrovaná repa. Každý svazek jen jednou (podle zařízení nebo kořene disku), s cestami, které na něm leží. Dál vrátí volnou a celkovou fyzickou paměť: na Windows přes `ctypes` `GlobalMemoryStatusEx`, na Linuxu z `/proc/meminfo` (`MemAvailable`), na macOS přes `sysctl hw.memsize` a `vm_stat`. Kde se hodnota nedá zjistit, vrať `null`, ne chybu. Nepřidávej závislost `psutil`.
  - Stav `ok` nebo `warning` podle prahů v konstantách: disk pod 10 GB nebo pod 10 % volného, paměť pod 1 GB nebo pod 10 % volné.
  - `cleanup(home, repos)` uklidí jen bezpečné věci: osiřelé adresáře `factory-advice-*` (`aifactory.workflow.adaptive.cleanup_orphans`) a pro každé registrované repo hotové worktrees a větve sloučených PR (`aifactory.review.clean_worktrees`, totéž co `factory task clean`). Chyba jednoho repa úklid nezastaví, skončí ve `warnings`. Vrátí, co se odstranilo, kolik místa se uvolnilo (rozdíl volného místa před a po úklidu) a varování. Běžící běhy, otevřené PR ani nic mimo factory se nemaže.
- `aifactory/src/aifactory/web/app.py`: přidej `GET /api/machine/system` a `POST /api/machine/cleanup` vedle `/machine/check`. POST musí projít stávající ochranou zápisových požadavků (Origin, Sec-Fetch-Site, JSON). Blokující práci spusť mimo event loop (`run_in_threadpool` nebo jak to dělají sousední handlery). Souběžný druhý úklid vrátí 409.
- Testy `aifactory/tests/web/test_web_system.py`: tvar odpovědi, prahy warning a ok (disk a paměť podstrčené přes monkeypatch), nedostupná paměť dá `null`, úklid zavolá `cleanup_orphans` a `clean_worktrees` pro každé repo a chybu jednoho repa vrátí jako warning, POST bez platného Origin se odmítne.

Mimo rozsah: UI čipu (samostatný task), mazání archivovaných běhů, logů a trace.db, úklid mimo adresáře factory.

Hotovo znamená:
- `GET /api/machine/system` vrátí svazky s volným a celkovým místem, paměť a stav `ok` nebo `warning`.
- `POST /api/machine/cleanup` odstraní osiřelé advice adresáře a hotové worktrees registrovaných rep a vrátí, co odstranil a kolik místa uvolnil.
- Prochází `aifactory/tests/web/test_web_system.py` i stávající testy ochrany zápisových požadavků.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-27 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/183 · náklady $0.00
