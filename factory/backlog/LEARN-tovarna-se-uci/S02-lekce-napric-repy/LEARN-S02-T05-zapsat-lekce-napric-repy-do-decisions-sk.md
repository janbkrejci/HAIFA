---
id: LEARN-S02-T05
title: "Zapsat lekce napříč repy do decisions, skillu factory a příručky"
status: done
archived: true
workflow: build-review
depends_on: [LEARN-S02-T04]
writes: [docs/decisions.md, aifactory/src/aifactory/skill/skill.md, aifactory/src/aifactory/guide/]
---

## Zadání
Zdokumentuj, že lekce se sbírají ze všech registrovaných rep a míří do cílového repa.

Co udělat:
- `docs/decisions.md`: krátké rozhodnutí „Lekce napříč repy“. Obsah: zdroje (registr dashboardu), cílové repo lekce, jak se pozná repo factory (`HAIFA_FACTORY_REPO`, jinak detekce podle názvu Python projektu `aifactory`), uložení lekce do trace DB cílového repa, klíče výtek s předponou repa a cíl `seed` jen pro repo factory.
- `aifactory/src/aifactory/skill/skill.md`: oddíl `factory learn` doplň o `scan --all`, pole `repo` a cíl `seed`.
- Příručka (`aifactory/src/aifactory/guide/05-behy-a-review.md`, nebo kapitola, kam lekce patří podle obsahu): stručně, jak v dashboardu najít lekce ze všech rep a kde se objeví lekce pro factory.
- Jestli test souladu příručky s UI a CLI (GUIDE-S01-T03) kontroluje nové texty, uprav ho, aby prošel.

Mimo rozsah: kód.

Hotovo znamená:
- `docs/decisions.md`, `skill.md` a příručka popisují lekce napříč repy v souladu s CLI a UI.
- Testy souladu příručky a skillu (`uv run pytest aifactory/tests -k "guide or skill"`) projdou.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-01 · workflow build-review · PR https://github.com/janbkrejci/HAIFA/pull/195 · náklady $1.76
