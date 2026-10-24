# První běh

`factory obs` otevře dashboard na `http://127.0.0.1:4700` (jiný port `--port N`). Terminál nech otevřený; běhy přežijí zastavení serveru.

## Horní lišta

- **HAIFA:** návrat na Přehled.
- **Necommitnutý backlog**, **Necommitnutá konfigurace:** červené chipy při necommitnutých změnách; klik otevře soubory a commit.
- **Chip aktualizací:** **Systém je aktuální**, nebo **Je k dispozici aktualizace**.
- **Chip kontroly:** **Systém v pořádku**, nebo **Nalezeny problémy** (stránka **Problémy a řešení**).
- **Chip knihovny:** **Knihovna OK**, nebo **Založit knihovnu** (stránka **Knihovna**).
- **Harnessy:** limity předplatného; klik otevře dialog **Harnessy tohoto počítače**.
- **AI průvodce**: otázky k repům, taskům a běhům; přiloží obrazovku. Z topbaru vždy otevře nové vlákno; historii otevře **Starší vlákna**. Změny (založení, úprava, spuštění či zrušení tasku, opakování běhu, schválení PR, follow-up hotového tasku) navrhne kartou; provede je až **Provést**.
- Příručka, motiv a přepínač rep.

## Problémy a řešení

Tlačítka nálezů a zbývajících kroků: **Zkontrolovat počítač**, **Připravit knihovnu** a **Zkontrolovat harnessy** vedou na Knihovnu; **Přidat repozitář**; **Nainstalovat factory** nebo **Commitnout konfiguraci** a **Zkontrolovat agenty** vedou na záložku Factory; **Založit projekt** na Backlog.

## Harnessy tohoto počítače

Harness zapni, vyber **Výchozí model** a **Výchozí thinking level** a spusť **Test**. Jeden označ jako **Výchozí harness** a **Uložit nastavení**. Výchozí harness musí projít testem. Jen v dashboardu.

Pomocníci (workflow, parametry tasku, Nový záměr, triáž follow-upů, lekce, průvodce) přebírají efektivní harness, model a thinking objektu: task, step, projekt, jinak repo. Repo a Přehled používají výchozí nastavení počítače z topbaru.

## Přidání repa

**Přidat repozitář**: cesta (nebo **Procházet…**), **Zkontrolovat**, **Přidat**. Zapíše `.factory/config.yaml`, doplní `.gitignore` a commitne to do base; agenty a workflow repo dědí z knihovny. Repo s factory v base jen připojí. Pro base přijímající jen PR zaškrtni **Změny base přes pull request**. Z CLI: `factory obs --repo CESTA` nebo `factory init`.

## Přehled a záložky repa

Přehled všech rep: **Běží**, **Čeká na review**, **Schváleno, čeká na CI**, **Čeká na automerge PR**, **Selhalo** a **Problémy** filtrují repa. Ikony karty: **Spustit továrnu** (připravené tasky), **Pauza** / **Pokračovat** a **Stop** (všechny běhy repa). **Odebrat repozitář** v menu ⋮ jen odpojí repo; soubory zůstanou.

Záložky repa: [**Backlog**](#/guide/backlog), [**Běhy** a **Review**](#/guide/behy-a-review), [**Factory**](#/guide/konfigurace).

## Od tasku k merge

1. Na Backlogu založ projekt, step a task se zadáním a workflow.
2. Commitni backlog chipem **Necommitnutý backlog**.
3. V detailu tasku **Spustit**.
4. Úspěšný task je **Čeká na review**: na záložce Review **Schválit**, nebo **Vrátit s poznámkou**.
5. Schválení: **Schváleno, čeká na CI**, po merge **Hotovo**.
