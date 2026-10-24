# Backlog a tasky

Backlog je strom markdown souborů pod `<docs_root>/backlog/`: **projekt**, **step**, **task** (jiné názvy nastaví `levels`). Projekt a step mají `index.md` s výchozími hodnotami; id tasku je `<step>-<kód>`, například `WEB-S01-T01`.

## Strom a kanban

Zrušené tasky se archivují rovnou, hotové tlačítkem **Archivovat**; archivované ukáže přepínač Zobrazit archivované v záhlaví sloupce a archivace se necommituje.

**Strom**: projekty, stepy, počty tasků, graf závislostí a **Nastavení** (posuvníky): auto-continue, auto-merge a klíče `index.md`.

**Kanban** seskupuje stavy; **Připraveno** řadí auto-continue shora dolů přetažením či šipkami. **Odloženo** (přetažením nebo **Vyloučit z auto continue**) vyřadí task z fronty; ručně spustit jde. Pořadí a odložení se necommitují.

## Stavy tasku

**Bez workflow** (nejde spustit), **Připraveno**, **Pro člověka** (udělá člověk, `assignee: human`), **Blokováno** (závislost není hotová; čeká-li na task pro člověka, **Čeká na člověka**), **Běží**, **Čeká na review**, **Schváleno, čeká na CI**, **Čeká na automerge PR**, **Hotovo** a **Zrušeno**.

V souboru je jen `status` (`todo`, `done`, `cancelled`). Hotovo nastavuje schválení PR; task pro člověka označíš tlačítkem **Hotovo** v detailu. Založíš ho přes `factory task add STEP TITLE --assignee human`.

## Detail a formulář

Detail tasku má tlačítka **Spustit**, **Upravit**, **Zrušit**, **Vylepšit agentem** (a **Hotovo** u tasku pro člověka) a karty **Zadání** (záložky se zadáním a dokumenty tasku jen ke čtení), **Běhy**, **PR**, **Nastavení** (workflow, auto continue, auto-merge, writes) a **Vazby**.

Hotový task se znovu nespouští: **Navázat follow-upem** (`factory task follow-up ID --body TEXT --run`) založí ve stejném stepu task s `follows: ID`, vlastními writes a workflow původního; **Commitnout a spustit** ho hned spustí. Detail ukáže, na co task navazuje a co navazuje na něj.

Formulář: **Titulek**, **Kód**, **Zadání** (cíl, kontext, kdy je hotovo) a **Workflow** s tlačítkem **Navrhnout workflow**. **Další nastavení** skrývá **Status**, **Auto-merge**, **Writes** (cesty, které smí agent měnit), **Závisí na**, **Související** a harness, model a přemýšlení tasku. **Vylepšit agentem** nechá agenta doplnit zadání, writes, vazby a workflow do formuláře.

## Dědičnost

Prázdná hodnota se dědí od stepu, pak projektu: `workflow`, `writes`, `harness`, `model`, `thinking`, `test_timeout`, `auto_continue`, `auto_merge`, `auto_heal`, `assignee`. Explicitní `null` dědění zastaví. Projekt a step upravíš panelem **Nastavení** nebo `factory backlog edit`.

`depends_on` odkazuje na task, step nebo projekt (splněný, když jsou hotové všechny nezrušené tasky).

## Commit backlogu

Úpravy se zapisují do pracovního stromu, ale **běhy čtou backlog z base**. Commitni ho chipem **Necommitnutý backlog** nebo `factory backlog commit`. Po ruční úpravě souborů spusť `factory backlog check`.
