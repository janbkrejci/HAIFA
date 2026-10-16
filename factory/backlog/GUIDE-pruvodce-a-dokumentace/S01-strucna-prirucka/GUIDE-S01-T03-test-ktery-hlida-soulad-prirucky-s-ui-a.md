---
id: GUIDE-S01-T03
title: "Test, který hlídá soulad příručky s UI a CLI"
status: todo
depends_on: [GUIDE-S01-T01]
---

## Zadání
Příručka se rozchází s dashboardem, protože ji nic nekontroluje (audit z 16. 10. 2026 našel 25 nepřesností).

Zadání:
1. Test, který z příručky vytáhne tučně uvedené popisky UI (`**…**`) a ověří, že každý existuje ve zdrojích `aifactory/web/src`. Výjimky, které nejsou popisky UI, jsou v explicitním seznamu v testu.
2. Test, který ověří, že každý příkaz `factory <příkaz> [podpříkaz]` a každý přepínač v příručce existuje ve stromu argparse.
3. Test, který hlídá limit délky příručky (4 000 slov).

Hotovo znamená:
- Testy projdou nad opravenou příručkou a selžou, když se do ní vrátí neexistující popisek nebo příkaz.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
