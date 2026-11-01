# LEARN-S02-T04: Dashboard Lekce: hledat ve všech repech, ukázat zdroj a cíl lekce

## Co se změnilo

- Sekce *Lekce* na obrazovce Factory má u tlačítka *Najít lekce* přepínač **Ze všech rep** (výchozí zapnuto). Zapnutý spustí `factory learn scan --all`: projde výtky běhů všech rep v dashboardu a každou lekci uloží do repa, kam pravidlo patří. Vypnutý hledá jen v aktuálním repu jako dřív.
- Lekce (navržená i přijatá) ukazuje chipy s repy, ze kterých její výtky pocházejí (`origin`); tooltip je vypíše větou. Každá výtka ukazuje své repo a odkaz na běh a task výtky z jiného repa vede do toho repa.
- Po dokončeném hledání ze všech rep hláška řekne, kolik lekcí se uložilo do jiných rep, a u každého repa dá odkaz na jeho sekci Lekce (`#/r/<id>/factory/lessons`, přepne repo jako jiné odkazy dashboardu, sekci otevře a posune na ni). Varování scanu (repo, jehož lekce nejdou přečíst) se ukážou pod ní.

## API

- `POST /api/learn/scan` přijímá `{since?, all?}`; `all` musí být bool (jinak HTTP 400), neznámý klíč HTTP 400. Bez `all` (nebo `all: false`) se chování nemění.
- Scan job má `all`. Jeho `result` má u scanu všech rep navíc `repos` (počet rep s výtkami), `elsewhere` (počet lekcí uložených do jiného repa než aktuálního, po id rep) a `warnings`.
- `GET /api/learn` vrací u lekce `origin` a u výtky `repo` (z `learn.view`, beze změny logiky).

## Ověření

- `uv run pytest tests/web/test_web_learn.py tests/e2e/test_learn_browser.py -n0`
- `bunx vitest run src/components/factory/LessonsSection.test.ts` v `aifactory/web`
