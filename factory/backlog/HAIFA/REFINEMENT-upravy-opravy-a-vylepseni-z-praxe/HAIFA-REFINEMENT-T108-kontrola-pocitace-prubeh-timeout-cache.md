---
id: HAIFA-REFINEMENT-T108
title: "Průběh, časový limit a čerstvé výsledky kontroly počítače"
status: done
depends_on: []
related: [HAIFA-REFINEMENT-T57]
writes: [aifactory/]
---

## Zadání
Při ruční kontrole počítače dashboard dlouho ukazoval pouze točící se chip bez informace, na co čeká. Uživatel zvažoval restart; kontrola nakonec sama doběhla. Předtím kontrola počítače ukazovala starý stav knihovny 2 ahead / 7 behind, přestože Git i /api/library už vracely 0 / 0 a synced. Neoznačovat tento incident za prokázaný deadlock ani za pouhou cache otevřené stránky: kontrola počítače má vlastní serverovou cache.

Prověřit celý řetězec ruční kontroly: web/machine.py::check_view a GlobalState, check/run_check a jeho subprocess probes, /api/machine/check, web/src/lib/readiness.ts, OverviewReadiness.vue a kontrolu počítače v SetupView.vue. Readiness čeká také na knihovnu, registry, roster a backlog; zjistit a zobrazit skutečný čekající krok. Ověřit vliv cache_lock drženého během run_check a souběžných požadavků. Vycházet z měření jednotlivých kroků, nikoli jen přidat delší timeout.

Hotovo znamená:
- Ruční kontrola průběžně a srozumitelně ukazuje aktuální krok a uplynulý čas; informace je dostupná i z chipu, ne jen v serverovém logu.
- Celá kontrola má jeden konečný časový rozpočet včetně čekání na zámek, probe procesy a navazující požadavky. Jednotlivá timeoutovaná závislost nezanechá UI trvale ve stavu checking. Pouhé skrytí spinneru při pokračujícím neomezeném backendovém čekání není oprava.
- Po vypršení limitu zobrazit konkrétní nedokončený krok a možnost opakovat kontrolu. Zachovat poslední známé výsledky s časem a označením jejich stáří; timeout nesmí znamenat úspěch. Pozdější odpověď starší kontroly nepřepíše novější výsledek.
- Opakované kliknutí či souběžné otevření dashboardu nezpůsobí nekontrolovanou frontu drahých kontrol. Ukončování zasahuje pouze procesy dané kontroly, nikoli běžící tasky či jiné aplikace.
- Kontrola počítače po dokončené synchronizaci knihovny neprezentuje staré ahead/behind jako aktuální. Vyřešit invalidaci nebo aktualizaci cache i pro změnu provedenou CLI/Gitem mimo dashboard; ruční čerstvá kontrola musí číst současný stav. Zachovat rozdíl mezi načtením cache a výslovnou kontrolou, bez automatického spouštění drahých kontrol při každé navigaci.
- Doplnit regresní testy úspěchu i selhání: pomalá nebo neodpovídající probe, timeout při čekání na sdílenou kontrolu/zámek, neodpovídající navazující request, opakování po timeoutu, pozdní odpověď, souběžné požadavky a změna knihovny mimo dashboard. Používat fakes nebo ohraničené lokální procesy, bez živých modelů a služeb.

Před implementací vyhledat přímé volající v celém aifactory/tests/. Spustit just lint, just typecheck, relevantní backendové testy, just web-test, všechny editované testové soubory a cílený browser test změněné kontroly/chipu; přegenerovat statický frontend přes just web-build. Limity testů stanovit s rezervou podle měření; ve factory běhu nespouštět celou sadu. Rozsah writes zahrnuje backend, frontend, jejich testy a generovaný frontend v aifactory/.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-10 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/212 · náklady $7.25
