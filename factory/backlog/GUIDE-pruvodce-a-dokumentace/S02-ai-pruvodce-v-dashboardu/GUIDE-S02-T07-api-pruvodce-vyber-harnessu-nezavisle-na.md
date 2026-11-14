---
id: GUIDE-S02-T07
title: "API průvodce: výběr harnessu nezávisle na repozitáři"
status: done
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/web/assistant.py, aifactory/src/aifactory/web/app.py, aifactory/tests/web/test_web_assistant.py]
---

## Zadání
Realizuj alternativu záměru, která dovoluje Guide použít jiný harness než repo. V aifactory/src/aifactory/web/assistant.py dnes Manager.create přijímá pouze title a screen; explicitní místní harness pi vede k harness_unavailable, protože GUIDE_HARNESSES obsahuje pouze claude a codex. Samotné přidání pi do tohoto seznamu není řešení: běžný pi adaptér nevynucuje povolené příkazy.

Rozšiř POST /api/assistant/threads o volitelný harness pro právě zakládané vlákno. Explicitní volba má přednost před místním nastavením repa i nastavením počítače. Model a thinking vybraného harnessu převezmi ze stávajícího nastavení počítače prostřednictvím harness.settings.effective_override; nepřenášej model původního harnessu a neměň sdílený resolver. Výběr musí fungovat také tehdy, když výchozí pi repozitáře je vypnutý nebo nemá použitelný model. Zachovej validaci screen a omezení vlákna na jeho původní repo.

Přidej GET /api/assistant/harnesses se seznamem harnessů podporovaných průvodcem a zapnutých na počítači, včetně jejich modelu a thinking. Použij existující pravidla místního nastavení pro platnost volby a vrať srozumitelný důvod u nepoužitelné konfigurace. Seznam neprezentuj jako záruku přihlášení nebo úspěšného běhu. API nesmí kvůli seznamu spouštět model. Bez explicitní volby zachovej dosavadní dědění a fallback. Neznámý, vypnutý nebo průvodcem nepodporovaný explicitní harness odmítni před založením vlákna, bez tichého fallbacku.

Volbu ulož do existujících metadat vlákna. Další zprávy, obnova session a načtení historie používají uloženou volbu; nepřidávej změnu harnessu existující konverzace. Zachovej bezpečný transport Codexu v assistant_codex a omezení příkazů Claude. Zprovoznění pi transportu je mimo rozsah této alternativy a pi zůstává pro přímý běh Guide odmítnutý.

Routy a popis kontraktu uprav v aifactory/src/aifactory/web/app.py. Regrese přidej do aifactory/tests/web/test_web_assistant.py. Před implementací vyhledej přímé volající změněných funkcí ve všech aifactory/tests/ a podle skutečného dopadu doplň výběr kontrol. Testy používají falešné harnessy, žádné živé modely.

Hotovo znamená:
- Repo s místním harnessem pi založí vlákno s explicitně zvoleným claude nebo codex; uložený model a thinking odpovídají vybranému harnessu.
- Totéž funguje, když výchozí pi je vypnutý; neplatný screen se nadále odmítne.
- Seznam voleb nabízí pouze podporované a povolené možnosti; neplatná explicitní volba nevytvoří vlákno ani nespustí adaptér.
- Bez explicitního harnessu zůstává dosavadní chování; další zpráva i načtení uloženého vlákna zachovají jeho harness.
- Pi nelze spustit přes explicitní parametr ani obnovené vlákno a ochrany Claude a Codexu zůstávají účinné.
- Projdou just lint, just typecheck, just pytest tests/web/test_web_assistant.py a relevantní regrese z tests/web/test_web_assistant_codex.py.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-14 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/225 · náklady $0.00
