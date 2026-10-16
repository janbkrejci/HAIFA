# První běh

Spusť dashboard příkazem `factory obs`. Otevře se `http://127.0.0.1:4700` (jiný port `--port N`); terminál nech otevřený. Běhy jsou samostatné procesy a zastavení serveru přežijí.

## Horní lišta

Zleva doprava:

- **HAIFA:** návrat na Přehled.
- **Necommitnutý backlog**, **Necommitnutá konfigurace:** červené chipy na stránce repa s necommitnutými změnami; klik otevře soubory a commit.
- **Chip aktualizací:** **Systém je aktuální**, nebo **Je k dispozici aktualizace**.
- **Chip kontroly:** **Systém v pořádku**, nebo **Nalezeny problémy** (stránka **Problémy a řešení**).
- **Chip knihovny:** **Knihovna OK**, nebo **Založit knihovnu** (stránka **Knihovna**).
- **Harnessy:** limity předplatného; klik otevře dialog **Harnessy tohoto počítače**.
- Příručka, motiv a přepínač rep.

## Problémy a řešení

Stránka vypíše zbývající kroky a nálezy kontroly s tlačítky: **Zkontrolovat počítač**, **Připravit knihovnu** a **Zkontrolovat harnessy** vedou na stránku Knihovna; **Přidat repozitář**; **Nainstalovat factory** nebo **Commitnout konfiguraci** a **Zkontrolovat agenty** vedou na záložku Factory; **Založit projekt** na Backlog.

## Harnessy tohoto počítače

Pro každý harness: zapni ho, vyber **Výchozí model** a **Výchozí thinking level** a spusť **Test**. Jeden označ jako **Výchozí harness** a **Uložit nastavení**. Harness s neúspěšným testem nejde použít jako výchozí. Tohle nastavení má jen dashboard, CLI ho nemá.

## Přidání repa

**Přidat repozitář**: zadej cestu (nebo **Procházet…**) a **Zkontrolovat**. **Přidat** zapíše `.factory/config.yaml`, doplní `.gitignore` a commitne to do base; agenty a workflow repo dědí z knihovny. Repo, které factory v base má, se jen připojí. Přijímá-li base změny jen přes PR, zaškrtni **Změny base přes pull request**. Z CLI: `factory obs --repo CESTA` nebo `factory init`.

## Přehled a záložky repa

Přehled ukazuje všechna repa; **Běží**, **Čeká na review**, **Čeká na automerge PR**, **Selhalo** a **Problémy** je filtrují. Karta repa má ikony **Spustit továrnu** (připravené tasky do volných slotů), **Pauza** / **Pokračovat** a **Stop** (všechny běhy repa). **Odebrat repozitář** v menu ⋮ repo jen odpojí; `.factory/` a backlog zůstanou.

Repo má záložky **Backlog** ([Backlog a tasky](#/guide/backlog)), **Běhy** a **Review** ([Běhy a review](#/guide/behy-a-review)) a **Factory** ([Konfigurace](#/guide/konfigurace)).

## Od tasku k merge

1. Na Backlogu založ projekt, step a task se zadáním a workflow.
2. Commitni backlog chipem **Necommitnutý backlog**.
3. V detailu tasku **Spustit**.
4. Úspěšný task je **Čeká na review**: na záložce Review **Schválit**, nebo **Vrátit s poznámkou**.
