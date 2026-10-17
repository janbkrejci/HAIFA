# Spec: Trvalé smazání vlákna AI průvodce

## Cíl

V seznamu starších vláken panelu průvodce (GUIDE-S02-T02) jde vlákno kromě otevření také
natrvalo smazat.

## Návrh

- `DELETE /api/assistant/threads/{id}` (`AssistantManager.delete` ve `web/assistant.py`):
  vlákno zmizí z paměti a celý adresář `$HAIFA_HOME/assistant/threads/<id>/` z disku
  (`thread.json`, `sessions/`, `work/`, `turns/`). Odpověď `{deleted: id}`.
- Neznámé nebo neplatné id vrací 404 `unknown_thread` (stejně jako `GET`).
- Vlákno s běžící odpovědí (`busy`) se nesmaže: 409 `busy`. Kontrola i mazání běží pod
  zámkem manažera, takže běžící odpověď nemůže `thread.json` zapsat zpět.
- Selhání mazání adresáře vrací 500 `delete_failed` a vlákno zůstane v paměti.
- Route je zápisová, prochází tedy `WriteGuardMiddleware` (Origin, Sec-Fetch-Site, JSON).
- Panel: každá položka seznamu má ikonu koše. Klik otevře `ConfirmDialog` (tón `danger`)
  s názvem vlákna; teprve potvrzení pošle `DELETE` (`deleteThread` v `lib/assistant.ts`).
  Vlákno zmizí ze seznamu; bylo-li otevřené, panel zavře jeho stream, zapomene ho
  v `sessionStorage` a ukáže prázdné nové vlákno. 404 (smazáno jinde) se bere jako
  smazané. Jiná chyba (např. 409) se ukáže nad seznamem a vlákno v něm zůstane.

## Testy

- `tests/web/test_web_assistant.py`: smazání (adresář pryč, seznam, 404 po smazání
  i v novém dashboardu nad stejným `HAIFA_HOME`, write guard 403, neznámé id 404) a 409
  pro vlákno, které odpovídá.
- Vitest: `lib/assistant.test.ts` (`deleteThread`: DELETE, odebrání ze seznamu
  a z otevřeného vlákna, odmítnutí nechá vlákno), `AssistantPanel.test.ts` (Zrušit
  nesmaže, potvrzení smaže, smazání otevřeného vlákna, zobrazení 409).
