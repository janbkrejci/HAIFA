---
id: HAIFA-S02-T03
title: Waterfall běhu podle sssf
status: done
workflow: simple-sdlc
depends_on: [HAIFA-S02-T02]
---

## Zadání
Převezmi z visualizeru sssf waterfall (gantt) běhu a nahraď jím tabulku fází v detailu běhu.

Where: `aifactory/web/src/` (`components/runs/RunDetail.vue`, `components/runs/StatChip.vue`, `views/RunsView.vue`, `lib/runs.ts`, `lib/events.ts`, `lib/format.ts` a testy), `aifactory/tests/e2e/test_f3_browser.py`, build v `aifactory/src/aifactory/web/static/`. Zdroj: `vendor/sssf/apps/visualizer/src/components/SessionTrace.vue`.

Done means:
- Dráhy: engineer, kód (všechny kódové fáze) a jedna dráha na agenta v pořadí prvního výskytu. Dráha agenta ukazuje model s ikonou poskytovatele, zaplnění kontextu, když je známé, a barvu agenta. Prázdná barva z konfigurace dostane barvu z palety.
- Časová osa se značkami a vyhrazeným úsekem pro požadavek. Bloky leží podle začátku a konce, mají minimální šířku a nikdy se nepřekrývají. Blok ukazuje stav, název, dobu a popis. Neúspěšný blok má červený okraj, fáze ve frontě jsou čárkované.
- Značky tool calls v bloku, chybné červeně. U kódových fází (např. `quality:test`) rozhoduje výsledek příkazu.
- Tooltip bloku ukazuje i harness a model, protože krok workflow je může přepsat.
- Klik na blok vybere fázi a otevře panel fáze, druhý klik výběr zruší. Adresa je `#/runs/<běh>/<fáze>`.
- Během běhu běžící bloky a doby rostou každou sekundu bez načítání.
- Hlavička běhu (task, stav, Zastavit, údaje a statistiky) zůstává.
- Unit testy (vitest) rozložení (pořadí drah, agent ve dvou fázích má jednu dráhu, bloky se nepřekrývají, minimální šířka, záložní barva) a komponenty (dráhy, bloky, chybná značka, klik vybírá a ruší výběr, růst s falešnými časovači). Prohlížečový test vidí dráhy a bloky běhu a vybere fázi klikem na blok.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: seznam běhů ve stylu karet sssf, archiv běhů.

Pevná omezení:
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/27 · náklady $4.48
