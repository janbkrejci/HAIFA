# HAIFA-S01-T30: Detail běhu: celé zadání místo výtahu 500 znaků

## Problém
`Tracer.session_request` ukládal do `sessions.request` jen `request[:500]` a detail běhu
zobrazoval právě toto pole — zadání končilo uprostřed slova bez výpustky.

## Řešení
- `aifactory/src/aifactory/engine/tracer.py`: `session_request` ukládá celé zadání.
- `aifactory/src/aifactory/web/runs.py`: `run_detail` vrací `session.request` přes
  `_with_full_request` — když událost `log` fáze request (kind `engineer`) nese delší
  `input` než uložený výtah (starší běhy), použije se ten.
- `aifactory/web/src/lib/runs.ts`: `REQUEST_PREVIEW_CHARS` (1200) a `excerpt(text, max)`,
  který zkracuje na hranici slova a končí „…“.
- `aifactory/web/src/components/runs/PhaseDetail.vue`: dlouhé zadání je v sekci
  „Požadavek“ sbalené na výtah, tlačítko „Zobrazit celé zadání“ / „Sbalit zadání“.
- Build do `aifactory/src/aifactory/web/static/`.

## Testy
- `tests/web/test_web_runs.py`: API vrací celé zadání > 500 znaků (nový zápis i starý
  běh se zkráceným `sessions.request`).
- `web/src/lib/runs.test.ts`: `excerpt`.
- `web/src/components/runs/PhaseDetail.test.ts`: dlouhé zadání sbalené, po rozbalení celé.
