---
id: HAIFA-REFINEMENT-T113
title: "Kontrola počítače jen při startu factory a na vyžádání, ne při otevření nového tabu"
status: done
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/web/machine.py, aifactory/tests/web/test_web_machine.py, aifactory/web/src/lib/readiness.ts, aifactory/web/src/lib/api.ts, aifactory/web/src/components/OverviewReadiness.vue, aifactory/web/src/components/OverviewReadiness.test.ts, aifactory/web/src/views/SetupView.vue, aifactory/web/src/views/SetupView.test.ts, aifactory/tests/e2e/test_machine_check_browser.py, aifactory/tests/e2e/test_overview_loading_browser.py, aifactory/src/aifactory/web/static/]
---

## Zadání
## Zadání
Kontrola počítače (`GET /api/machine/check`) se teď pustí znovu pokaždé, když se dashboard otevře v novém tabu. Příčina je v `check_view` v `aifactory/src/aifactory/web/machine.py`. Čtení bez `fresh` při chybějící cache (`entry is None`) spustí nový `CheckJob`. Cache chybí po neúspěšné nebo vypršené kontrole při startu (timeout se nikdy necachuje) a po `GlobalState.invalidate()` (zápis do knihovny, uložení nebo test harnessu, apply factory). Každé načtení stránky přitom posílá čtení bez `fresh` přes `useReadiness()` v `aifactory/web/src/lib/readiness.ts` (`onMounted -> refresh()`). Stejně čte i `SetupView.vue`, `FactoryView.vue` a `RosterEditor.vue`.

Změnit pravidlo: plnou kontrolu (sondy harnessů, přihlášení, hosting) spustí jen start dashboardu (`lifespan` v `app.py` volá `check_view(fresh=True)`, to zůstává) nebo výslovné vyžádání (`fresh=1`: tlačítko kontroly, uložení či test harnessu z `MachineHarnessesDialog` v `App.vue`). Čtení bez `fresh`:
- se připojí k právě běžícímu jobu stejného režimu (např. ke kontrole při startu), pokud existuje a nevypršel,
- jinak vrátí poslední známý výsledek. Po `invalidate()` ho vrátí označený jako zastaralý (např. `stale: true`); pravidla knihovny se dál vyhodnotí znovu přes `_current_library`,
- a když výsledek nikdy nebyl, vrátí prázdný pohled s jasným příznakem „zatím nezkontrolováno“ (např. `checked: false`), `ok` není true a nový job nespustí.
Zachovat sdílení jednoho jobu mezi souběžnými požadavky, pravidlo, že výsledek jobu zahájeného před `invalidate()` se necachuje, a chování timeoutu (`timed_out`, `progress`). Popis modulu v docstringu upravit podle nového pravidla.

Na frontendu (`lib/readiness.ts`, `components/OverviewReadiness.vue`, `views/SetupView.vue`, typ `MachineCheck` v `lib/api.ts`) zobrazit stav „zatím nezkontrolováno“ nebo „zastaralý výsledek“ jako upozornění s akcí pro ruční kontrolu. Nesmí se tvářit jako úspěch ani jako běžící kontrola. Načtení stránky nikdy nepošle `fresh=1`. Ruční kontrola a refresh po uložení nebo testu harnessu dál posílají `fresh=1`.

Před změnou dohledat přímé volající `check_view`, `fetchMachineCheck` a `useReadiness` v celém `aifactory/tests/` a ve webových testech a upravit očekávání, která počítají se spuštěním kontroly při čtení bez cache (např. `test_first_check_timeout_has_no_result_and_is_not_ok`, `test_check_started_before_a_library_write_is_not_cached` v `tests/web/test_web_machine.py`). Testy bez živých modelů a služeb, souběh deterministicky přes bariéry nebo události.

Mimo rozsah: plánované periodické kontroly, změny CLI `factory check`, změna obsahu kontrol, zrychlení kontroly a timeout kroku roster (HAIFA-REFINEMENT-T116).

Hotovo znamená:
- Test v `tests/web/test_web_machine.py`: čtení bez `fresh` bez cache a bez běžícího jobu nespustí kontrolu (falešný `Machine` nezaznamená žádnou sondu) a vrátí příznak „nezkontrolováno“ s `ok` false.
- Test: po `invalidate()` vrátí čtení bez `fresh` poslední výsledek označený jako zastaralý a nespustí job. `fresh=1` kontrolu spustí a výsledek uloží do cache.
- Test: čtení bez `fresh` během kontroly při startu se k ní připojí a vrátí její výsledek.
- Webový test (`OverviewReadiness.test.ts` nebo `SetupView.test.ts`): připojení stránky volá `/api/machine/check` bez `fresh`, stav „nezkontrolováno“ ukáže upozornění s tlačítkem ruční kontroly a tlačítko pošle `fresh=1`.
- Browser test `tests/e2e/test_machine_check_browser.py` ověří, že otevření Přehledu v novém tabu nevyvolá požadavek s `fresh=1` ani novou kontrolu na serveru.
- Projdou `just lint`, `just typecheck`, `just web-test`, cílené `just pytest` pro `tests/web/test_web_machine.py` a všechny editované testovací soubory, browser testy přes `just pytest tests/e2e/<soubor> -n0`.
- Proběhne `just web-build` a aktualizuje se distribuovaný statický frontend.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-11 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/217 · náklady $0.00
