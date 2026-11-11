# Backlog a tasky

Backlog: markdown strom `<docs_root>/backlog/`: **projekt**, **step**, **task** dle `levels`; výchozí hodnoty kontejnerů v `index.md`, id tasku `<step>-<kód>` (např. `WEB-S01-T01`).

## Strom a kanban

Filtr projektu sdílí strom i kanban; prohlížeč jej pamatuje podle repozitáře.

Archivaci (`archived: true/false`) ukládá **Archivovat**/**Obnovit** do front matter; commituje se. Chybějící hodnota: `cancelled`=archivovaný, ostatní=nearchivovaný. Archiv ukáže přepínač sloupce.

**Strom**: projekty, stepy, počty tasků, graf závislostí a **Nastavení** (posuvníky): klíče `index.md`.

**Kanban** seskupuje stavy; **Připraveno** řadí auto-continue shora dolů přetažením či šipkami. **Odloženo** (přetažením nebo **Vyloučit z auto continue**) vyřadí task z fronty; ručně spustit jde. Pořadí a odložení se necommitují.

## Stavy tasku

**Bez workflow**, **Připraveno**, **Pro člověka** (udělá člověk, `assignee: human`), **Blokováno** (závislost není hotová; čeká-li na task pro člověka, **Čeká na člověka**), **Selhalo**, **Běží**, **Čeká na review**, **Schváleno, čeká na CI**, **Čeká na automerge PR**, **Hotovo** a **Zrušeno**.

V souboru je jen `status` (`todo`, `done`, `cancelled`). Hotovo nastavuje schválení PR; task pro člověka označíš tlačítkem **Hotovo** v detailu. Založíš ho přes `factory task add STEP TITLE --assignee human`.

## Detail a formulář

Detail tasku: **Spustit**, **Upravit**, **Zrušit**, **Vylepšit agentem** (a **Hotovo** u tasku pro člověka) a karty **Zadání** (zadání a dokumenty jen ke čtení), **Běhy**, **PR**, **Nastavení** (workflow, writes) a **Vazby**.

Hotový task nespustíš: **Navázat follow-upem** (`factory task follow-up ID --body TEXT --run`) založí ve stepu task s `follows: ID`, vlastními writes a workflow původního; **Commitnout a spustit** ho spustí. Detail ukáže předchůdce i navazující tasky.

Formulář: **Titulek**, **Kód**, **Zadání** (cíl, kontext, kdy je hotovo), **Workflow** a **Navrhnout workflow**. **Další nastavení**: **Status**, **Writes** (povolené cesty), **Závisí na**, **Související** a časový limit testů. **Vylepšit agentem** doplní zadání, writes, vazby a workflow. Oba dodržují [pravidla pomocných agentů](#/guide/prvni-beh/harnessy-tohoto-pocitace).

**Nový záměr** navrhne backlog k upřesnění a použití. Používá stejné místní pravidlo pomocných agentů.

## Dědičnost

Prázdná hodnota se dědí od stepu, pak projektu: `workflow`, `writes`, `test_timeout`, `auto_heal`, `assignee`. Explicitní `null` dědění zastaví. Projekt a step upravíš panelem **Nastavení** nebo `factory backlog edit`.

`depends_on` odkazuje na task, step nebo projekt (splněný, když jsou hotové všechny nezrušené tasky).

## Commit backlogu

Úpravy se zapisují do pracovního stromu, ale **běhy čtou backlog z base**. Commitni ho ikonou s tooltipem **Necommitnutý backlog** nebo `factory backlog commit`. Po ruční úpravě souborů spusť `factory backlog check`.

Staré `auto_continue`, `auto_merge` a `harness/model/thinking` zůstávají čitelná metadata. Běžná editace je zachová; nové tasky je nepotřebují. Nová Factory řídí automatizace a výchozí harness místními volbami repozitáře na Přehledu.
