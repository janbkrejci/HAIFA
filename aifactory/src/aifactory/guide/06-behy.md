# Běhy

Běh (run) je jedno provedení workflow nad taskem. HAIFA pro něj vytvoří worktree `<worktrees_dir>/<id-běhu>` (výchozí `.factory/worktrees/`) a větev `factory/<id-tasku>-<n>`, kde `n` je pořadí běhu tasku. Agenti pracují jen v tomto worktree.

## Spuštění

Z detailu tasku tlačítkem **Spustit**, nebo `factory task run ID`. Dialog **Spustit task** ukáže:

- workflow, povolené zápisy a commit base, ze kterého běh vychází, a sbalitelné zadání,
- varování: necommitnutou konfiguraci (odkaz **Commitnout konfiguraci**), task, který ještě není v base (**Commitnout backlog do base**), nesplněné závislosti,
- **Harness pro tento běh:** harness, model a přemýšlení pro všechny agenty jen pro tento běh. Prázdné znamená podle tasku, projektu a nastavení počítače; přepisy na krocích workflow platí dál. Tabulka pod tím ukáže roster agentů.
- **Po úspěchu pokračovat dalšími tasky (auto continue)**,
- **Poznámka (volitelná)** pro agenty, připojí se k zadání.

**Spustit přesto (ignorovat nesplněné závislosti)** spustí blokovaný task (v CLI `--force`). Task, který už běží, znovu spustit nejde.

Běh spuštěný z dashboardu je samostatný proces; jeho výstup se ukládá do `$HAIFA_HOME/logs/` a běh přežije i restart dashboardu.

## Seznam běhů

Záložka **Běhy** přepíná **Aktivní** a **Archivované** běhy. Sloupce: task, workflow, stav, začátek, kdo běh spustil (ručně, auto-continue, auto-resolve, auto-ci-fix: oprava červené CI při schválení), doba, tokeny, náklady, pull request a tečky fází.

**Archivovat dokončené** přesune dokončené běhy do archivu; **Vymazat všechny** v archivu je nevratně smaže z databáze. Jednotlivé běhy archivuješ, vrátíš z archivu nebo smažeš v řádku.

Panel **Náklady** sčítá cenu, tokeny a počet běhů za celý backlog i po tascích.

## Stavy běhu

| Stav | Význam |
| --- | --- |
| běží | Běh pracuje na některé fázi. |
| pozastavuje se | Po dokončení aktuální fáze se běh zastaví. |
| pozastaveno | Běh čeká na pokračování. |
| čeká | Fáze čeká ve frontě, například na volný slot testů. |
| úspěch | Workflow prošlo a pull request je otevřený. |
| chyba | Některá fáze selhala. |
| zastaveno | Běh zastavil uživatel. |
| přerušeno | Proces běhu nečekaně skončil. |

## Detail běhu

Kliknutím na běh otevřeš detail: workflow, větev, commit knihovny (nebo „seed“), začátek a konec, kdo běh spustil a odkaz na pull request. Pod tím čipy s dobou, tokeny, cenou a objemem čtení a zápisu.

**Fáze** jsou vodopád: řádek pro každého agenta s modelem a zaplněním kontextu, pruhy fází v čase. Kliknutím na fázi otevřeš její detail:

- **Požadavek** a **Konfigurace agenta** (harness, model, thinking, nástroje, session),
- **Sestavené prompty**, které agent skutečně dostal,
- **Gates** s výsledky kontrol (prošel, neprošel),
- **Náklady** a **Výstupy** (strukturovaná odpověď agenta a zda je platná),
- **Události:** volání nástrojů s argumenty a výsledky, živě během fáze.

## Pauza, pokračování a zastavení

- **Pauza** dokončí aktuální fázi a běh pak čeká. Proces žije dál a drží si task i slot.
- **Pokračovat** spustí další fázi.
- **Zastavit** ukončí agenty i proces běhu. Běh je **zastaveno**, worktree a větev zůstanou.

Z CLI: `factory task pause ID`, `factory task resume ID`, `factory task stop ID`.

## Úspěch a pull request

Po úspěšném workflow HAIFA odešle větev a otevře pull request; task je **V review**. Selže-li publikace (například síť), běh zůstane úspěšný s chybou publikace a v detailu běhu je tlačítko **Publikovat** (v CLI `factory task publish ID`).

## Nedodělky a blokace

Agenti nenechávají nedodělky v repu (žádné TODO soubory, seznamy otevřených bodů ani komentáře „dodělat později“). Práci, která se do tasku nevejde, ohlásí ve své odpovědi (`follow_ups`) a HAIFA ji založí jako nový task ve stepu **TODO** projektu (step založí, když chybí). Task uvádí, z jakého běhu a tasku vznikl a proč. Změny backlogu HAIFA commitne do base.

Když agent ohlásí, že task nejde dokončit, dokud není hotová jiná práce (nový TODO task s `blocks_task` nebo existující task v `blocked_by`), dostane task `depends_on` na blokující task a běh skončí jako **chyba** s důvodem `blocked: …`. Pull request se neotevře, task se neoznačí za hotový a nemerguje se. Až bude blokující task hotový, spusť task znovu.

## Selhání a nový pokus

Selhaný běh nechá worktree i větev pro rozbor a task se vrátí do předchozího stavu (obvykle **Připraveno**). Nový pokus spustíš znovu tlačítkem **Spustit**: vznikne nová větev a nový worktree. Před ním zvaž, zda neupravit zadání, workflow nebo poznámku pro agenty.

Staré worktree mergnutých či zavřených PR a překonaných běhů uklidí `factory task clean`.

## Auto-continue

Řetěz auto-continue po úspěšném běhu sám spustí další připravený task:

- Se zapnutým **Po úspěchu pokračovat dalšími tasky** (v CLI `--auto`) pokračuje řetěz po každém úspěšném běhu bez ohledu na nastavení tasků.
- Bez něj pokračuje jen po tasku se zapnutým `auto_continue` (vlastním nebo zděděným) a spouští jen tasky, které ho mají také.
- Pořadí: nejdřív pořadí sloupce Připraveno v kanbanu, pak tasky stejného stepu, pak stejného projektu.
- Přeskakuje tasky odložené v kanbanu, bez workflow a tasky, jejichž writes se překrývají s běžícími běhy nebo otevřenými PR.
- Řetěz nikdy nespustí task z jiného projektu, ani když je zařazený v kanbanu.
- Běh, který skončí jako blokovaný (`blocked: …`, viz Nedodělky a blokace), řetěz nezastaví: jako další se přednostně spustí blokující TODO tasky, které při tom běhu vznikly, pokud jsou spustitelné; jinak řetěz pokračuje běžným pořadím. Blokovaný task zůstane nehotový a bez PR.
- Jiné selhání řetěz zastaví. Se zapnutým auto-merge pokračuje až po merge předchozího PR.

Panel **Řetěz** na záložce Běhy ukazuje stav řetězu, obsazené sloty, přeskočené tasky s důvodem (překryv writes, čeká na PR, blokováno, bez workflow, odloženo v kanbanu…) a důvod konce (není co spustit, běh selhal, auto-continue vypnuto, PR nesloučen).

## Souběžné běhy

`max_parallel_runs` v konfiguraci repa (v dashboardu **Souběžné běhy auto-continue**, výchozí 1) určuje, kolik běhů řetězu může běžet zároveň. Task se spustí souběžně, jen když se jeho writes nepřekrývají s běžícími běhy ani se soubory otevřených PR; task s širokými writes (celé repo nebo balíček) běží sám. Kroky testů se navíc střídají v `test_slots` slotech na počítač (výchozí 1).

## Bezpečnost běhu

- Zápis mimo worktree nebo mimo povolené cesty tasku HAIFA vrátí a fáze selže. Povolené jsou `writes` tasku a jeho soubory specifikace a dokumentace (`<docs_root>/specs/…`, `<docs_root>/docs/…`).
- Necommitnutá práce v hlavním checkoutu se před každým voláním agenta uloží a po něm obnoví.
- Chráněné soubory (`protected_files`, výchozí `.factory/`) agent měnit nesmí.
- Běh čte konfiguraci i backlog z commitu v base, ne z pracovního stromu.
