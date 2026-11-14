---
id: HAIFA-S01-T52
title: "Intent: znepřístupnit AI průvodce a neposílat intent jako ID tasku"
status: todo
depends_on: []
writes: [aifactory/web/, aifactory/src/aifactory/web/static/, aifactory/tests/]
---

## Zadání
Na obrazovce Nový záměr / Intent znepřístupnit AI průvodce. Návrh zatím není běžný task, který by průvodce mohl načíst. Konkrétní chyba je v lib/assistant.ts: describeScreen vyhodnotí route backlog/intent jako task s ID intent, protože NEW_INTENT není mezi netaskovými routami.

Akceptace:
- Pro backlog/intent i backlog/intent/<container> je tlačítko průvodce disabled a má dostupné stručné vysvětlení „Průvodce není při návrhu záměru dostupný.“ Samotná nápověda musí být dostupná i klávesnicí.
- Intent nikdy nevytvoří kontext {task: "intent"}. Použít skutečnou routu/konstantu, ne text nadpisu.
- Při přechodu s otevřeným panelem nebo po obnovení stránky s uloženým otevřeným průvodcem nesmí být možné odeslat zprávu či spustit akci průvodce na Intentu. Ošetřit i odeslání Enterem a případné jiné vstupní cesty; samotné zakázání topbar tlačítka nestačí.
- Zachovat rozepsanou zprávu a historii vlákna. Již odeslaný požadavek nerušit jen kvůli navigaci. Po opuštění Intentu je průvodce opět dostupný se správným aktuálním kontextem.
- Běžné tasky, běhy, Review a Přehled fungují jako dosud. Neměnit generování návrhu Intentu ani mu nepřidávat podporu kontextu průvodce.

Regrese: describeScreen pro obě Intent routy, přímý vstup, přechod s otevřeným panelem, reload s uloženým panelem, blokovaný submit bez HTTP požadavku a návrat na skutečný task s funkčním odesláním. Kandidáti: lib/assistant.test.ts, App.test.ts, AssistantPanel.test.ts, tests/e2e/test_assistant_browser.py a test_intent_browser.py podle dotčených scénářů.

Ověření: vyhledat přímé volající v celém aifactory/tests/ a zvolit jen testy dotčeného chování. Spustit každý změněný testovací soubor, just lint, just typecheck, just web-test, just web-build a příslušné browser testy změněných obrazovek podle AGENTS.md. Testy bez živých modelů a služeb, s izolovaným HAIFA_HOME; nespouštět celou sadu v tasku.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
