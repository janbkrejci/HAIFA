# Backlog a tasky

Backlog: markdown strom pod `<docs_root>/backlog/`: **projekt**, **step**, **task** (názvy určuje `levels`). Projekt a step: výchozí hodnoty v `index.md`; id tasku: `<step>-<kód>`, například `WEB-S01-T01`.

## Strom a kanban

Archivaci (`archived: true/false`) ukládá **Archivovat**/**Obnovit** do front matter; commituje se. Chybějící hodnota: `cancelled`=archivovaný, ostatní=nearchivovaný. Archiv ukáže přepínač sloupce.

**Strom**: projekty, stepy, počty tasků, graf závislostí a **Nastavení** (posuvníky): auto-continue, auto-merge a klíče `index.md`.

**Kanban** seskupuje stavy; **Připraveno** řadí auto-continue shora dolů přetažením či šipkami. **Odloženo** (přetažením nebo **Vyloučit z auto continue**) vyřadí task z fronty; ručně spustit jde. Pořadí a odložení se necommitují.

## Stavy tasku

**Bez workflow** (nejde spustit), **Připraveno**, **Pro člověka** (udělá člověk, `assignee: human`), **Blokováno** (závislost není hotová; čeká-li na task pro člověka, **Čeká na člověka**), **Běží**, **Čeká na review**, **Schváleno, čeká na CI**, **Čeká na automerge PR**, **Hotovo** a **Zrušeno**.

V souboru je jen `status` (`todo`, `done`, `cancelled`). Hotovo nastavuje schválení PR; task pro člověka označíš tlačítkem **Hotovo** v detailu. Založíš ho přes `factory task add STEP TITLE --assignee human`.

## Detail a formulář

Detail tasku: **Spustit**, **Upravit**, **Zrušit**, **Vylepšit agentem** (a **Hotovo** u tasku pro člověka) a karty **Zadání** (zadání a dokumenty jen ke čtení), **Běhy**, **PR**, **Nastavení** (workflow, auto continue, auto-merge, writes) a **Vazby**.

Hotový task nespustíš: **Navázat follow-upem** (`factory task follow-up ID --body TEXT --run`) založí ve stepu task s `follows: ID`, vlastními writes a workflow původního; **Commitnout a spustit** ho spustí. Detail ukáže předchůdce i navazující tasky.

Formulář: **Titulek**, **Kód**, **Zadání** (cíl, kontext, kdy je hotovo), **Workflow** a **Navrhnout workflow**. **Další nastavení**: **Status**, **Auto-merge**, **Writes** (povolené cesty), **Závisí na**, **Související**, harness, model a přemýšlení. **Vylepšit agentem** doplní zadání, writes, vazby a workflow. Oba používají nastavení tasku podle [pravidla pomocných agentů](#/guide/prvni-beh/harnessy-tohoto-pocitace).

**Nový záměr** navrhne backlog k upřesnění a použití. Nastavení přebírá ze stepu či projektu, jinak z počítače (stejné pravidlo).

## Dědičnost

Prázdná hodnota se dědí od stepu, pak projektu: `workflow`, `writes`, `harness`, `model`, `thinking`, `test_timeout`, `auto_continue`, `auto_merge`, `auto_heal`, `assignee`. Explicitní `null` dědění zastaví. Projekt a step upravíš panelem **Nastavení** nebo `factory backlog edit`.

`depends_on` odkazuje na task, step nebo projekt (splněný, když jsou hotové všechny nezrušené tasky).

## Commit backlogu

Úpravy se zapisují do pracovního stromu, ale **běhy čtou backlog z base**. Commitni ho chipem **Necommitnutý backlog** nebo `factory backlog commit`. Po ruční úpravě souborů spusť `factory backlog check`.
