---
id: LEARN-S02-T04
title: "Dashboard Lekce: hledat ve všech repech, ukázat zdroj a cíl lekce"
status: done
archived: true
workflow: build-test-review
depends_on: [LEARN-S02-T03]
writes: [aifactory/src/aifactory/web/learn.py, aifactory/src/aifactory/web/app.py, aifactory/web/src/lib/learn.ts, aifactory/web/src/components/factory/LessonsSection.vue, aifactory/web/src/components/factory/LessonsSection.test.ts, aifactory/tests/web/test_web_learn.py, aifactory/tests/e2e/test_learn_browser.py, aifactory/src/aifactory/web/static/]
---

## Zadání
Sekce *Lekce* na obrazovce Factory umí hledat lekce ze všech rep a ukazuje, odkud výtky jsou a kam lekce míří.

Co udělat:
- API (`aifactory/src/aifactory/web/learn.py`, `aifactory/src/aifactory/web/app.py`): `POST /api/learn/scan` přijme `{since?, all?}` (bool) a předá `all_repos` do `scan`. Výsledek scan jobu vrací i počet rep a počet lekcí uložených do jiných rep (po id rep). `GET /api/learn` vrací u lekce `origin` a u výtky `repo` (z `learn.view`). Uprav docstring modulu `web/app.py` (popis `/api/learn/scan`).
- Frontend (`aifactory/web/src/lib/learn.ts`, `aifactory/web/src/components/factory/LessonsSection.vue`): u tlačítka *Najít lekce* přepínač „Ze všech rep“ (výchozí zapnuto). Lekce ukazuje chip s repy původu. Výtka ukazuje své repo. Po dokončeném scanu se ukáže hláška, kolik lekcí přibylo v jiných repech, a odkaz na sekci Lekce cílového repa (přepnutí repa jako jinde v dashboardu). Použij sdílené prvky UI (vlastní tooltip a dropdown), žádné nativní.
- Testy: `aifactory/tests/web/test_web_learn.py` (tělo `all`, předání do falešného scanneru, odmítnutí neznámého klíče), `aifactory/web/src/components/factory/LessonsSection.test.ts` (přepínač, chipy původu, hláška) a podle potřeby `aifactory/tests/e2e/test_learn_browser.py`.
- Přegeneruj statický build `just web-build` (`aifactory/src/aifactory/web/static/`).

Mimo rozsah: logika scanu a accept (T02, T03).

Hotovo znamená:
- `uv run pytest aifactory/tests/web/test_web_learn.py aifactory/tests/e2e/test_learn_browser.py` a `bun test` (vitest) pro `LessonsSection.test.ts` projdou.
- V dashboardu jde spustit hledání lekcí ze všech rep a lekce ukazuje repa původu i hlášku o lekcích uložených v jiném repu.
- `aifactory/src/aifactory/web/static/` odpovídá zdrojům.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-01 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/194 · náklady $2.45
