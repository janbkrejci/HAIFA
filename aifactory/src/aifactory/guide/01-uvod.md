# Úvod

HAIFA (Helios AI Factory) je lokální dashboard a nástroj příkazové řádky `factory`, který pouští kódovací agenty (Claude Code, Codex, pi) na úkoly z backlogu v tvých Git repozitářích. Každý úkol běží ve vlastním worktree a větvi, projde workflow agentů a kontrol (plán, implementace, testy, review) a skončí pull requestem, který schválíš, vrátíš k přepracování, nebo se mergne sám.

Tahle příručka je pro dva typy čtenářů:

- **Uživatel** zakládá tasky, spouští a sleduje běhy a schvaluje výsledky. Stačí mu kapitoly [První spuštění](#/guide/prvni-spusteni), [Dashboard](#/guide/dashboard), [Backlog a tasky](#/guide/backlog), [Běhy](#/guide/behy) a [Review a merge](#/guide/review).
- **Správce** instaluje HAIFA, připravuje repozitáře, agenty a workflow, spravuje sdílenou knihovnu a aktualizace. Pro něj jsou navíc kapitoly [Instalace](#/guide/instalace), [Konfigurace repa](#/guide/konfigurace-repa), [Agenti a workflow](#/guide/agenti-a-workflow), [Knihovna](#/guide/knihovna), [Počítač a harnessy](#/guide/pocitac), [Práce v týmu](#/guide/tym), [Aktualizace a vydání](#/guide/aktualizace) a [Příkazová řádka](#/guide/cli).

Příručku otevřeš kdykoli ikonou knihy v horní liště dashboardu. Pole **Hledat v příručce** hledá ve všech kapitolách, bez ohledu na diakritiku.

## Jak HAIFA funguje

1. **Backlog** je strom markdown souborů v repu (`factory/backlog/<projekt>/<step>/<task>.md`). Projekt se dělí na stepy, step na tasky. Každý task má zadání a parametry ve front matter (workflow, závislosti, auto-continue).
2. **Běh** (run) vezme task, vytvoří pro něj worktree a větev a provede jeho workflow. Fáze běhu jsou role agentů (planner, builder, tester, reviewer…) a deterministické kroky (test, commit, rebase…).
3. **Výsledek** běhu je pull request (na GitHubu, v Azure DevOps nebo lokálně). Na obrazovce **Review** ho schválíš a mergneš, nebo vrátíš s připomínkami k přepracování. Workflow může PR po úspěšném review mergnout samo.
4. **Konfigurace** repa je v adresáři `.factory/` a běhy ji čtou z commitu ve větvi `base`. Agenti, workflow a skilly, které repo nemá, se dědí ze sdílené **knihovny**.

## Pojmy

- **Repo:** Git repozitář, ve kterém HAIFA pracuje. Jeden dashboard obsluhuje více rep.
- **Base:** hlavní větev repa (typicky `main`), do které míří pull requesty a ze které běhy čtou konfiguraci.
- **Projekt, step, task:** úrovně backlogu. Projekt a step mají `index.md` s výchozími hodnotami, které tasky dědí.
- **Workflow:** posloupnost kroků běhu v YAML (`.factory/workflows/` nebo knihovna). Může obsahovat smyčky (`repeat`/`until`) a podmínky (`when`).
- **Agent a role:** agent je konkrétní nastavení (harness, model, úroveň thinking); role je úloha ve workflow (plánuje, staví, testuje, kontroluje), kterou agent vykonává.
- **Harness:** CLI, přes které HAIFA spouští model: `claude` (Claude Code), `codex` nebo `pi`. Harness je u agenta vždy zapsaný.
- **Roster:** přiřazení agentů k harnessům a modelům v repu (`.factory/agents.yaml`).
- **Knihovna:** Git repo s agenty, workflow, skilly a rozšířeními v domovském adresáři HAIFA, sdílené týmem.
- **Domovský adresář HAIFA:** `~/.config/haifa`, jinde podle proměnné `HAIFA_HOME`. Obsahuje nastavení počítače, registr rep dashboardu a knihovnu.
- **Worktree:** samostatná pracovní kopie repa pro jeden běh. Agent pracuje jen v ní; zápisy mimo ni HAIFA vrátí a fázi označí jako selhanou.

## Bezpečnost a hranice

- Dashboard naslouchá jen na `127.0.0.1` a zapisovací požadavky přijímá jen ze své vlastní stránky.
- Agent smí měnit jen povolené cesty tasku; konfiguraci `.factory/` běh měnit nesmí (`protected_files`).
- Přístupové klíče patří do `$HAIFA_HOME/env` nebo do lokálního `.env`, nikdy do gitu.
- Osobní a globální konfigurace harnessů (tvoje `~/.claude`, `~/.codex`…) se do běhu nedostane tam, kde to harness umožní; jinak na to upozorní `factory check`.
