# Uložené thinking v API vláken průvodce

`Thread.summary()` vrací pole `thinking` přímo z vlákna, stejně jako `harness` a `model`. Pole je tím dostupné v seznamu vláken (`GET /api/assistant/threads`), detailu (`GET /api/assistant/threads/{id}`) i odpovědi při vytvoření (`POST /api/assistant/threads`), protože detail používá společné summary.

Vrací se uložená hodnota, nikoli nově vyhodnocené nastavení počítače nebo kontextu. Serializace na disk ani výběr harnessu se nemění. Frontend T73 již volitelné pole podporuje.

Regrese ověří hodnoty `high` ze zděděného kontextu a `medium` z fallbacku ve všech třech API odpovědích. Po změně nastavení a restartu správce zůstane původní uložené `thinking` dostupné v detailu i seznamu.
