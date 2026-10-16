---
id: GUIDE-S01-T01
title: Přepsat příručku na minimum a opravit nepřesnosti
status: todo
depends_on: []
---

## Zadání
Příručka (`aifactory/src/aifactory/guide/`, 15 kapitol, 13 700 slov) je dlouhá, opakuje se a místy nesedí s dashboardem. Audit z 16. 10. 2026 proti kódu a CLI.

Zadání:
1. Přepsat příručku na minimum, cíl do 4 000 slov. Navržená osnova (soubory `<NN>-<id>.md`, kapitola `instalace` zůstává, je zdrojem `INSTALL.md` v bundlu):
   - Co je HAIFA (jak funguje ve 4 krocích, bezpečnost),
   - Instalace (beze změny obsahu, bez části Spuštění dashboardu a Aktualizace),
   - První běh (spojit 03 a mapu obrazovek ze 04: horní lišta, Přehled s tlačítky Spustit továrnu, Pauza, Stop, záložky repa),
   - Backlog a tasky (strom, kanban, stavy včetně „Pro člověka“ a „Čeká na člověka“, formulář, dědičnost, commit backlogu),
   - Běhy a review (spojit 06 a 07: spuštění, stavy, Navázat / `factory task retry`, follow-upy, tasky pro člověka, approve s CI a ci-fix, return, resolve, auto-merge, stacked PR),
   - Konfigurace repa, agenti a workflow (tabulka `config.yaml`, priorita harnessu a modelu, tabulka workflow včetně `ci-fix`, výběr workflow),
   - Knihovna a tým (spojit 10, 11 a 12),
   - Aktualizace a řešení problémů (spojit 13 a 15, bez tabulek kódů, které opakují `fix` z `factory check`),
   - Příloha pro autory workflow (kroky, podmínky, `coverage`, `roles.yaml`).
   Kapitolu CLI nahradit odstavcem o `--json`, `--repo`, `factory --help` a `factory --skill` a seznamem 10 nejčastějších příkazů.
2. Opravit ověřené nepřesnosti:
   - 03: neexistující „Začínáme“ (kroky jsou na stránce Problémy a řešení), krok Harnessy vede na stránku Knihovna, přidání repa instaluje factory z knihovny a commitne.
   - 04: pořadí chipů v horní liště, necommitnutý backlog a konfigurace jsou chipy, ne pruhy.
   - 05: karta Nastavení (ne Spuštění), Zadání a Dokumenty jsou jedna karta se záložkami, tlačítka Vylepšit agentem a Hotovo, „Další nastavení“, kanban drag and drop, task pro člověka (`factory task add --assignee human`).
   - 06: Navázat / `factory task retry` místo „nový pokus tlačítkem Spustit“, workflow follow-upu volí agent.
   - 07: `github_approver` umožní schválení na GitHubu.
   - 08: formulář nastavení obsahuje `base_changes`, `base_pr_merge`, `stacked_prs`, popisek „Lokální necommitované nastavení“, sekce Souhrn kontroly a Co dál.
   - 10: přesun a smazání kopie jsou jen na stránce Knihovna (Repa s vlastní kopií, Smazat kopii z repa), Kontrola počítače je na stránce Knihovna.
   - 13 a 14: zápis do knihovny (seed, `library push`) jde vždy přes pull request, nic se nepushuje přímo. Nastavení harnessů počítače nemá CLI. `task approve` čeká na CI.
3. Každý popisek UI a příkaz v textu ověřit proti `aifactory/web/src` a `factory --help`.

Hotovo znamená:
- Příručka má do 4 000 slov a žádné z výše uvedených nepřesností.
- Dashboard (`#/guide`) a bundle (`INSTALL.md`) fungují. Testy guide, bundlu a GuideView projdou podle AGENTS.md.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
