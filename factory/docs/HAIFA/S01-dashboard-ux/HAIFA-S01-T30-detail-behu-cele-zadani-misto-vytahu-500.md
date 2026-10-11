# Detail běhu: celé zadání

Detail běhu (sekce **Požadavek** v detailu fáze) ukazuje celé zadání běhu.

- Trace ukládá do `sessions.request` celé zadání (dřív jen prvních 500 znaků).
- U starších běhů s výtahem vezme API `GET /api/runs/{run_id}` celé zadání z události
  `log` fáze request (`input`), pokud je delší než uložený výtah.
- Zadání delší než 1200 znaků je sbalené na výtah končící „…“ (zkrácený na hranici
  slova); tlačítko **Zobrazit celé zadání** ho rozbalí, **Sbalit zadání** zase sbalí.
- Výtah dělá `excerpt(text, max)` v `aifactory/web/src/lib/runs.ts`; použijte ho všude,
  kde se zadání zkracuje.
