# První běh

`factory obs`: dashboard `http://127.0.0.1:4700` (port `--port N`). Terminál nech otevřený; běhy přežijí zastavení serveru.

## Horní lišta

- **HAIFA:** návrat na Přehled.
- **Necommitnutý backlog**, **Necommitnutá konfigurace:** červené ikony s počtem; tooltip popisuje soubory. Klik otevře panel backlogu nebo náhled commitu konfigurace.
- **Chip aktualizací:** ikona; tooltip **Systém je aktuální** / **Je k dispozici aktualizace**.
- **Chip kontroly:** fajfka/varování; tooltip **Systém v pořádku** / **Nalezeny problémy**. Klik zopakuje kontrolu / otevře **Problémy a řešení**.
- **Chip knihovny:** knihovna/varování; tooltip **Knihovna OK** / **Založit knihovnu**. Otevře stránku **Knihovna**.
- **Harnessy:** limity, při načítání spinner, bez harnessů varování s tooltipem; klik otevře **Harnessy tohoto počítače**.
- **AI průvodce**: otázky s kontextem obrazovky; topbar otevře nové vlákno, **Starší vlákna** historii. Změny tasků, běhů, PR a follow-upů navrhuje kartou; provede je až **Provést**.
- Příručka, motiv a přepínač rep.

## Problémy a řešení

Tlačítka nálezů a zbývajících kroků: **Zkontrolovat počítač**, **Připravit knihovnu** a **Zkontrolovat harnessy** vedou na Knihovnu; **Přidat repozitář**; **Nainstalovat factory** nebo **Commitnout konfiguraci** a **Zkontrolovat agenty** vedou na záložku Factory; **Založit projekt** na Backlog.

## Harnessy tohoto počítače

V dashboardu zapni harness, vyber **Výchozí model**, **Výchozí thinking level**, spusť **Test**. Úspěšný označ jako **Výchozí harness**, pak **Uložit nastavení**.

Pomocníci přebírají harness, model a thinking objektu: task, step, projekt, jinak repo. Repo a Přehled používají nastavení počítače z topbaru.

## Přidání repa

**Přidat repozitář**: cesta (**Procházet…**), **Zkontrolovat**, **Přidat**. Vytvoří a commitne `.factory/config.yaml`, doplní `.gitignore`; existující factory připojí. Agenty/workflow dědí z knihovny. Chráněná base: **Změny base přes pull request**. CLI: `factory obs --repo CESTA`, `factory init`.

## Přehled a záložky repa

Filtry Přehledu: **Běží**, **Čeká na review**, **Schváleno, čeká na CI**, **Čeká na automerge PR**, **Selhalo**, **Problémy**. Karta: **Spustit továrnu** (připravené tasky), **Pauza** / **Pokračovat**, **Stop** (všechny běhy). Menu ⋮: **Odebrat repozitář** odpojí repo, soubory zachová.

Záložky: [**Backlog**](#/guide/backlog), [**Běhy** a **Review**](#/guide/behy-a-review), [**Factory**](#/guide/konfigurace).

## Od tasku k merge

1. Backlog: založ projekt, step, task se zadáním a workflow.
2. Commitni backlog ikonou s tooltipem **Necommitnutý backlog**.
3. Detail tasku: **Spustit**.
4. Úspěšný task je **Čeká na review**: na záložce Review **Schválit**, nebo **Vrátit s poznámkou**.
5. Schválení: **Schváleno, čeká na CI**, po merge **Hotovo**.
