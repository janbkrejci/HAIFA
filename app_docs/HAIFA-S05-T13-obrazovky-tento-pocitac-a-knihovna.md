# HAIFA-S05-T13: Tento počítač a Knihovna

V menu přepínače repozitářů jsou nové položky **Tento počítač** a **Knihovna**. Kolega s prázdným registrem začne na Tento počítač, pokud stroj hlásí chybu nebo nemá knihovnu. Se zdravým strojem a knihovnou se otevře prázdný přehled.

Na **Tento počítač** jsou nálezy ve skupinách HAIFA, Nástroje, Harnessy, Hosting, Knihovna a Prostředí. **Kopírovat** zkopíruje doporučenou opravu; **Znovu zkontrolovat** obnoví kontrolu. U harnessů je počet rep, která je používají. Dashboard nástroje neinstaluje ani nepřihlašuje účty.

Sekce knihovny ukazuje cestu, remote, náskok a zpoždění vůči známému remote. **Pull** stáhne změny, **Push** odešle lokální commity; bez remote jsou vypnuté. Chybějící knihovnu lze **Založit ze semínka** nebo **Naklonovat týmovou knihovnu…** zadáním URL. Před zápisem se ukáže plán s položkami, soubory a blokátory a čeká na potvrzení v modálu.

Na **Knihovna** přepínáš Agenty, Workflow, Skilly a Rozšíření pi. Řádek ukazuje účel nebo popis, verzi `vN · hash`, datum, autora a stav použití v repech. Kliknutím na jméno otevřeš soubory pouze pro čtení, historii a tabulku použití. Historická verze mění zobrazené soubory; operace pro repa používají aktuální knihovnu.

**Přidat do repozitářů…** nabídne výběr registrovaných rep. **Aktualizovat vybraná repa…** použije zaškrtnutá repa v tabulce použití. Cíl lze přepnout mezi commitem do base a pull requestem. Nejdříve se zobrazí plán každého repa a potom potvrzení. Repa se provedou po jednom; blokátor nebo selhání jednoho repa nebrání ostatním. Výsledek obsahuje commit, odkaz na PR nebo konkrétní důvod odmítnutí. **Diff** ukáže plán porovnání položky s knihovnou, včetně místních konfliktů.

**Import…** vezme cestu ke složce pod domovem uživatele a typ položky. Náhled zobrazí změny a potvrzení je zapíše do knihovny. Při změně zdroje nebo knihovny se zápis odmítne a je potřeba vytvořit nový náhled. Formuláře posílají pouze volby plánu a digest; obsah ani seznam zapisovaných souborů do API zápisu neposílají.

Ověřeno cílenými Vitest, backendovými pytest a prohlížečovými scénáři nad statickým buildem. Nový browser test zakládá knihovnu v dočasném HAIFA_HOME, kontroluje jediný commit a zobrazení položek, historie a workflow bez modelu a s blokovanými externími požadavky.
