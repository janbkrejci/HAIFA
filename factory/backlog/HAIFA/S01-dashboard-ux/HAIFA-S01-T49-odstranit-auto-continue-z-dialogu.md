---
id: HAIFA-S01-T49
title: Odstranit nefunkční auto continue z dialogu spuštění tasku
status: todo
depends_on: []
related: [HAIFA-S11-T02, HAIFA-S11-T06]
writes: [aifactory/web/, aifactory/src/aifactory/web/static/, aifactory/src/aifactory/guide/, aifactory/tests/]
---

## Zadání
V dialogu Spustit task odstranit přepínač „Po úspěchu pokračovat dalšími tasky (auto continue)“. Výchozí off pokračování nezakazuje: RunDialog.vue pouze posílá legacy parametr auto/--auto bez účinku na runtime politiku. Rozhoduje živé místní nastavení repozitáře na Přehledu (run/policy.py, run/queue.py).

Rozsah a akceptace:
1. Odstranit checkbox, jeho lokální stav, odesílání input.auto a jen tím osiřelý kód/styly. Běžný ani vynucený start z dialogu neposílá auto.
2. Nápovědu nahradit textem „Automatické pokračování řídí nastavení repozitáře na Přehledu.“ s odkazem na existující Přehled. Nevytvářet další přepínač ani kopii stavu. Text nesmí slibovat zastavení běžícího tasku vypnutím auto continue.
3. Poznámka, harness/model/thinking, kontroly a blokace startu fungují stejně jako dosud.
4. Opravit související komentáře a guide/05-behy-a-review.md. Opravit i zprávu po merge v ReviewView.vue, která stále připisuje auto continue kroku místo místním volbám repozitáře.
5. Zachovat kompatibilitu legacy CLI/API auto i současnou runtime politiku. Jejich odstranění ani změna automatizace nejsou součástí tasku.
6. Sestavit distribuovaný statický frontend.

Ověření:
- Upravit RunDialog.test.ts: absence přepínače, start bez auto, zachování ostatních parametrů a odkaz na Přehled. Upravit přímo dotčené testy zprávy po merge.
- Vyhledat přímé volající a související testy v celém aifactory/tests/; vybrat jen dotčené chování a spustit každý upravený testovací soubor.
- just lint, just typecheck, just web-test, just web-build a příslušný browser test dialogu v Backlogu podle AGENTS.md. Bez živých modelů a služeb; při nezměněném backendu nepřidávat duplicitní testy runtime politiky.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
