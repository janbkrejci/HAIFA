---
id: HAIFA-REFINEMENT-T118
title: Gantt automaticky sleduje pravý konec a respektuje ruční posun
status: done
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T112]
writes: [aifactory/web/src/components/runs/RunWaterfall.vue, aifactory/web/src/components/runs/RunWaterfall.test.ts, aifactory/tests/e2e/test_run_waterfall_scroll_browser.py, aifactory/src/aifactory/web/static/]
---

## Zadání
V aifactory/web/src/components/runs/RunWaterfall.vue doplnit automatické horizontální sledování pravého konce existující oblasti waterfall-scroll. Při otevření detailu s přetékajícím Ganttem zobrazit pravý konec. Dokud je sledování zapnuté, držet pohled vpravo také po aktualizaci dat, růstu plátna a změně dostupné šířky; posun provádět až po aktualizaci rozměrů DOM. Scrollovatelnost určovat skutečným scrollWidth > clientWidth, nikoli pouze timeline.overflow, protože posun může vzniknout i na úzkém viewportu.

Ruční odscrollování od pravého okraje sledování vypne a další aktualizace ponechají uživatelův pohled na místě. Ruční návrat na pravý okraj sledování znovu zapne. Použít malou toleranci v pixelech pro zaokrouhlené rozměry. Rozlišit posun vyvolaný uživatelem od změn rozměrů a vlastního programového posunu tak, aby růst grafu automatické sledování omylem nevypínal. Obsluha musí fungovat pro scrollbar, touchpad i klávesnici.

Nad posouvanou oblast přidat přístupný přepínač „Automaticky posouvat pohled“, viditelný pouze při skutečném horizontálním přetečení. Jeho stav odpovídá sledování: vypnutí ponechá aktuální pozici, zapnutí okamžitě přesune pohled na pravý konec. Ruční odscrollování a návrat doprava aktualizují stejný stav přepínače. Stav držet pouze pro aktuálně otevřený běh; změna run_id obnoví výchozí zapnuté sledování, výběr jiné fáze stejného běhu jej neresetuje. Pokud graf přestane přetékat, ovládání skrýt a při pozdějším opětovném přetečení začít sledovat pravý konec. Ošetřit také přechod z prázdného detailu na první fáze a uklidit observery či naplánované callbacky při odmountování.

Zachovat existující geometrii bloků, společný posun osy a swimlanes, přichycené popisky, tooltipy a výběr fáze. Neměnit backend, výpočet časové osy ani zavádět ukládání preference mezi běhy.

Doplnit komponentové testy v aifactory/web/src/components/runs/RunWaterfall.test.ts. V aifactory/tests/e2e/test_run_waterfall_scroll_browser.py nahradit dosavadní očekávání počátečního scrollLeft == 0 očekáváním pravého konce a rozšířit syntetická data o aktualizace, které skutečně zvětší plátno. Ověřit sledování při růstu, zachování ručně odscrollované pozice, obnovení po návratu doprava, obě akce přepínače a změnu šířky. Použít deterministické čekání na stav či geometrii, bez živých modelů a služeb. Před implementací dohledat přímé volající a související testy v celém aifactory/tests/. Spustit just lint, just typecheck, just web-test a just pytest tests/e2e/test_run_waterfall_scroll_browser.py -n0; nepouštět celou Python ani browser sadu. Spustit just web-build a zahrnout aktualizovaný distribuovaný frontend z aifactory/src/aifactory/web/static/.

Hotovo znamená:
- Přetékající Gantt se po otevření zobrazí na pravém konci a při růstu i resize jej automaticky sleduje.
- Ruční posun doleva vypne sledování; aktualizace grafu uživatele nevracejí doprava.
- Ruční návrat na pravý konec obnoví sledování a následující růst grafu posune pohled doprava.
- Přepínač „Automaticky posouvat pohled“ odpovídá skutečnému stavu, funguje klávesnicí a zobrazuje se jen při horizontálním přetečení.
- Krátký graf nemá přepínač ani zbytečný scroll; přechody mezi přetékáním a stavem bez přetečení fungují podle zadání.
- Jiný běh začíná se zapnutým sledováním, výběr fáze stejného běhu zachová stav a ruční pozici.
- Browser test nad rostoucím grafem prokáže pozastavení i obnovení sledování a zachová kontroly zarovnání, nepřekrývání bloků a šířky dokumentu.
- Projdou just lint, just typecheck, just web-test, cílený browser test a just web-build; distribuovaný frontend obsahuje změnu.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-11 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/220 · náklady $0.00
