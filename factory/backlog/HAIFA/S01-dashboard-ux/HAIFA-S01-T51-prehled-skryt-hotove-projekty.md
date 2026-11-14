---
id: HAIFA-S01-T51
title: "Přehled Po projektech: skrýt dokončené projekty s možností jejich zobrazení"
status: todo
depends_on: []
writes: [aifactory/web/, aifactory/src/aifactory/web/static/, aifactory/tests/]
---

## Zadání
V režimu Přehledu „Po projektech“ standardně skrýt dokončené projekty a nabídnout přepínač „Zobrazit hotové“. Jde pouze o filtr zobrazení, bez změn backlogu, archivace nebo pravidel fronty.

Akceptace:
- Výchozí je skrytí dokončených projektů; explicitní volba se pamatuje v prohlížeči. Přepínač je dostupný i tehdy, když filtr schoval všechny projekty.
- Dokončený projekt má alespoň jeden task a všechny jeho tasky jsou terminální (Hotovo nebo Zrušeno). Prázdný projekt ani projekt s neznámými/neúplnými daty není automaticky hotový. Archivace sama neurčuje dokončení.
- Projekt s běžící/pozastavenou/spouštěnou prací, čekajícím PR/CI/merge nebo nevyřešeným selháním se neschová, i při nesouladu se stavem backlogu. Neztratit upozornění na nesynchronizované merge. „Bez projektu“ není dokončený projekt.
- Obnovený task vrátí projekt do výchozího pohledu při dalším obnovení dat. Ověřit jeden projekt, více projektů, všechny hotové a kombinaci aktivních/hotových. Současný fallback pro <= 1 projekt nesmí filtr obejít.
- Filtr funguje v RepoCard i v klidných repozitářích. Repozitář, jeho ovládání a indikace konfigurace/backlogu zůstávají dostupné; souhrnné počty práce repozitáře se filtrem nepřepisují. Po přepnutí na zobrazení po repozitářích se filtr projektů neuplatní.

Výchozí místa: OverviewView.vue, RepoWork.vue, lib/overview.ts (projectSections), RepoCard.vue. Použít existující data o stavech a aktivitě; API rozšířit jen pokud pro spolehlivé rozhodnutí něco skutečně chybí. V tom případě nejprve doplnit potřebné writes.

Testy: čistá funkce filtru pro hraniční případy, persistence přepínače, znovuotevření úkolu, uchování důležitých upozornění a browser scénář Po projektech.

Ověření: vyhledat přímé volající v celém aifactory/tests/ a zvolit jen testy dotčeného chování. Spustit každý změněný testovací soubor, just lint, just typecheck, just web-test, just web-build a příslušné browser testy změněných obrazovek podle AGENTS.md. Testy bez živých modelů a služeb, s izolovaným HAIFA_HOME; nespouštět celou sadu v tasku.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
