---
id: HAIFA-REFINEMENT-T110
title: Zjednodušit Přehled a opravit Play při vypnutém auto continue
status: done
workflow: build-test-review
depends_on: []
writes: [aifactory/web/src/components/overview/LocalRepoControls.vue, aifactory/web/src/components/overview/LocalRepoControls.test.ts, aifactory/src/aifactory/web/control.py, aifactory/src/aifactory/web/launcher.py, aifactory/src/aifactory/run/queue.py, aifactory/tests/web/test_web_control.py, aifactory/tests/web/test_web_launcher.py, aifactory/tests/run/test_factory_start.py, aifactory/tests/web/test_manual_factory_start.py, aifactory/tests/e2e/test_multi_repo_browser.py, aifactory/src/aifactory/web/static/]
---

## Zadání
Na Přehledu v aifactory/web/src/components/overview/LocalRepoControls.vue odstranit viditelný nadpis „Na tomto počítači“, oba vysvětlující odstavce „Platí pouze pro novou Factory na tomto počítači. Ukládá se ihned.“ a „Staré volby v backlogu nová Factory nepoužívá. Bez místních voleb jsou automatizace vypnuté.“ a poznámku „Aktuální běhy doběhnou, další se nespustí“. Zachovat ovládací prvky, ukládání, chybové stavy a přístupné označení sekce; texty nepřesouvat jinam.

Reprodukovat Play s místním auto_continue=false a alespoň jedním ready taskem. FactoryControl.start v aifactory/src/aifactory/web/control.py nyní volá launcher.start s automatic=True; v aifactory/src/aifactory/web/launcher.py to nastavuje původ auto-continue, který podléhá bariéře automatických startů. Opravit rozlišení explicitního kliknutí od automatického pokračování: Play musí spustit ready práci i při vypnutém auto continue. Zachovat dosavadní výběr počáteční dávky podle volných slotů, pořadí fronty, závislostí, vyloučení a kolizí writes. Kliknutí nesmí zapnout ani přepsat místní auto continue; po dokončení počáteční dávky se při false nesmí automaticky doplňovat sloty ani spouštět retry/heal. Při true musí dosavadní pokračování fungovat dál. Automatické pokračování musí nadále respektovat bariéru při vypnutí. V queue.py upravit nepravdivý popis automatického původu ručního startu podle výsledného řešení; plošná změna politiky automatizací není součástí úlohy.

Regresi pokrýt přes skutečnou cestu control → launcher → přijetí běhu, ne pouze mockem start_factory, který politiku neověřuje. Použít existující testy test_web_control.py, test_web_launcher.py a test_factory_start.py podle přímých volajících; podle potřeby doplnit samostatný testovací soubor test_manual_factory_start.py. V LocalRepoControls.test.ts a test_multi_repo_browser.py aktualizovat očekávání odstraněných textů a ověřit ovládání. Testy nesmějí potřebovat živé modely ani služby. Před změnou dohledat přímé volající a očekávání textů v celém aifactory/tests/ a webových testech.

Hotovo znamená:
- Uvedené texty nejsou na Přehledu viditelné a místní ovládací prvky dál fungují.
- Play při auto_continue=false spustí ready task při volném slotu a ponechá uloženou hodnotu false.
- Po dokončení ručně spuštěné dávky nevznikne při false další automatický běh; test zahrnuje další čekající ready task.
- Testy potvrzují pokračování při true a zachování bariéry automatických startů při false.
- Projdou just lint, just typecheck, just web-test, cílené just pytest pro změněné chování a všechny editované testovací soubory včetně just pytest tests/e2e/test_multi_repo_browser.py -n0.
- Proběhne just web-build a aktualizuje se distribuovaný statický frontend.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-10 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/214 · náklady $0.00
