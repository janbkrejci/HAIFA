---
id: HAIFA-S01-T03
title: "Spinner na akcích, které něco spouštějí"
status: done
workflow: plan-build-test
depends_on: [HAIFA-S01-T02]
---

## Zadání
Ukaž loader na akcích, když se něco rozjíždí: tlačítko, na které uživatel klikl, ukáže spinner, dokud akce na serveru neskončí. Akce, které by s ní kolidovaly, jsou do té doby zakázané.

Where: `aifactory/web/src/` (`views/BacklogView.vue`, `views/RunsView.vue`, `views/ReviewView.vue`, `views/SettingsView.vue`, `components/backlog/`, `components/review/ReviewActions.vue`, `components/review/ReviewList.vue`, `components/runs/RunDetail.vue`, `components/runs/RunsList.vue`, `components/settings/SettingsForm.vue`, `style.css` a testy), build v `aifactory/src/aifactory/web/static/`.

Done means:
- Spinner mají Spustit v detailu tasku (kontrola před startem), Spustit a Spustit přesto, Commitnout backlog do base, Založit, Uložit, Přidat a Odebrat vazbu, Přiřadit, přepínač auto-continue, Schválit, Vrátit, Vyřešit konflikt, Dorovnat s base, Zastavit a Uložit v Nastavení. Spinner je jen v kliknutém tlačítku.
- Ikona tlačítka Obnovit se točí, dokud se data načítají. Seznam se při prvním načtení neukáže jako prázdný („Žádné tasky“, „Žádné běhy“, „Žádné otevřené PR“), dokud data nedorazí.
- Když se běh po Spustit, Vrátit nebo Vyřešit konflikt ještě rozjíždí (odpověď `pending`), spinner zůstane, dokud se běh neobjeví v živých aktualizacích, a pak UI ukáže odkaz na běh. Hláška „obnov stránku za chvíli“ zmizí.
- Po úspěšném spuštění je Spustit zakázané.
- Spinner je sdílená komponenta, stejná ve všech obrazovkách.
- Unit testy (vitest) s odloženou odpovědí API pro Backlog, Běhy, Review a Nastavení: spinner je v kliknutém tlačítku, kolidující tlačítka jsou zakázaná a po odpovědi spinner zmizí. Rozjíždějící se běh drží spinner do živé události.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: průběh běhu v procentech, změny API.

Pevná omezení:
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow plan-build-test · PR https://github.com/janbkrejci/HAIFA/pull/12 · náklady $3.25
