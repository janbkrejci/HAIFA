---
id: GUIDE-S02-T08
title: "Panel Guide: zvolit harness před první zprávou"
status: todo
workflow: build-test-review
depends_on: [GUIDE-S02-T07]
writes: [aifactory/web/src/lib/assistant.ts, aifactory/web/src/lib/assistant.test.ts, aifactory/web/src/components/assistant/AssistantPanel.vue, aifactory/web/src/components/assistant/AssistantPanel.test.ts, aifactory/tests/e2e/test_assistant_browser.py, aifactory/src/aifactory/web/static/, aifactory/src/aifactory/guide/03-prvni-beh.md, docs/decisions.md]
---

## Zadání
Napoj API z T07 do aifactory/web/src/lib/assistant.ts a aifactory/web/src/components/assistant/AssistantPanel.vue. V prázdném vlákně nabídni pomocí existujícího UI dropdownu volbu „Podle nastavení“ a podporované harnessy vrácené API. Stačí výběr harnessu; samostatné editory modelu a thinking nejsou součástí zadání. U konkrétní volby ukaž model a thinking, se kterými se vlákno založí.

Vlákno se dnes vytváří až při první zprávě. Explicitní harness proto předej do createThread při prvním odeslání a poté zobrazuj skutečně uloženou volbu. Při založení dalšího prázdného vlákna se výběr vrátí na „Podle nastavení“. U existujícího vlákna výběr nenabízej; změna harnessu vyžaduje nové vlákno. Zachovej kontext obrazovky, historii a průběžné odpovědi.

Výběr musí být dostupný před prvním odesláním a zůstat použitelný po chybě harness_unavailable. U repa nastaveného na pi tak uživatel vybere claude nebo codex a znovu odešle svou zprávu bez změny konfigurace repa. Pi nenabízej jako spustitelnou volbu a krátce vysvětli, že Guide zatím vyžaduje podporovaný harness s omezenými nástroji. Pokud není dostupná žádná podporovaná volba, ukaž srozumitelný stav a odkaž na existující nastavení harnessů počítače.

Doplň testy v lib/assistant.test.ts a AssistantPanel.test.ts a scénář v aifactory/tests/e2e/test_assistant_browser.py s falešným backendem: repo používá pi, člověk vybere jiný harness a úspěšně odešle první zprávu. Aktualizuj stručný popis průvodce v aifactory/src/aifactory/guide/03-prvni-beh.md a příslušné rozhodnutí v docs/decisions.md: jde o volbu pro nové vlákno, nikoli změnu výchozího harnessu repozitáře. Přegeneruj distribuovaný dashboard přes just web-build.

Před implementací vyhledej přímé volající změněných helperů a testy dotčených textů a selektorů. Kontroly prováděj bez živých modelů; nespouštěj celou Python ani browser sadu.

Hotovo znamená:
- V novém vlákně lze ještě před první zprávou vybrat podporovaný harness nezávisle na pi nastaveném u repa.
- První požadavek obsahuje explicitní volbu; „Podle nastavení“ parametr neposílá.
- Po odmítnutí výchozího pi lze vybrat jiný harness a odeslat původní zprávu.
- Historie a další zprávy zachovávají uložený harness; nové prázdné vlákno obnoví výchozí volbu.
- Testy pokrývají načítání voleb, chybu API a stav bez dostupného podporovaného harnessu.
- Dokumentace popisuje volbu pro vlákno a omezení pi; distribuovaný statický frontend odpovídá změně.
- Projdou just lint, just typecheck, just web-test, just web-build, just pytest tests/e2e/test_assistant_browser.py -n0 a relevantní kontroly příručky v tests/test_guide.py a tests/test_guide_consistency.py; všechny editované testovací soubory jsou spuštěny.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
