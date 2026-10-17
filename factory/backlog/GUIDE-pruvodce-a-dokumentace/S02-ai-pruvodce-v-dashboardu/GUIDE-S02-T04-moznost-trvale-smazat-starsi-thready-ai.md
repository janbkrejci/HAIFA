---
id: GUIDE-S02-T04
title: Možnost trvale smazat starší thready AI asistenta
status: todo
workflow: build-test-review
depends_on: [GUIDE-S02-T02]
related: [GUIDE-S02-T01]
writes: [aifactory/src/aifactory/web/assistant.py, aifactory/src/aifactory/web/app.py, aifactory/web/src/lib/assistant.ts, aifactory/web/src/lib/assistant.test.ts, aifactory/web/src/components/assistant/, aifactory/tests/web/test_web_assistant.py, aifactory/tests/e2e/test_assistant_browser.py, aifactory/src/aifactory/web/static/]
---

## Zadání
Dnes jde v panelu AI průvodce mezi staršími vlákny jen přepínat. Uživatel má mít možnost vlákno také **trvale smazat**.

## Co udělat

**Backend** (`aifactory/src/aifactory/web/assistant.py`, `aifactory/src/aifactory/web/app.py`)
- Přidat `DELETE /assistant/threads/{thread_id}`. Vlákno zmizí z paměti a z disku, tedy celý adresář `$HAIFA_HOME/assistant/threads/<id>/`.
- Neznámé nebo neplatné id vrátí stávající chybu `unknown_thread` (404).
- Vlákno, ve kterém průvodce právě odpovídá (`busy`), se nesmaže. Vrátí se `busy` (409), aby běžící odpověď nezapsala `thread.json` zpět.
- Zápisový požadavek musí projít stávající ochranou API (Origin, Sec-Fetch-Site, JSON) stejně jako ostatní zápisové routy.

**Frontend** (`aifactory/web/src/lib/assistant.ts`, `aifactory/web/src/components/assistant/AssistantPanel.vue`)
- Každá položka v seznamu vláken dostane akci Smazat (ikona nebo tlačítko).
- Před smazáním se zobrazí potvrzení ve vlastním modálním dialogu, ne systémovém, protože jde o nevratnou akci.
- Po smazání vlákno zmizí ze seznamu. Pokud bylo právě otevřené, panel přejde do prázdného stavu nebo na nové vlákno a nezůstane na smazaném.
- Chybu (např. 409 busy) panel zobrazí uživateli.

## Akceptační kritéria
- Smazané vlákno se už nevrátí v `GET /assistant/threads`, ani po restartu dashboardu (soubor je pryč z disku).
- `GET /assistant/threads/{id}` po smazání vrátí 404.
- Mazání vlákna, které právě odpovídá, vrátí 409 a vlákno zůstane.
- Testy backendu (`aifactory/tests/web/test_web_assistant.py`) a frontendu (`assistant.test.ts`, `AssistantPanel.test.ts`) pokrývají smazání, potvrzení i smazání právě otevřeného vlákna.
- Statický build dashboardu (`aifactory/src/aifactory/web/static`) je přegenerovaný přes `just web-build`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
