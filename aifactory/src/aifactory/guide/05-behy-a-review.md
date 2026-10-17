# Běhy a review

Běh provede workflow tasku ve vlastním worktree a větvi `factory/<id-tasku>-<n>`.

## Spuštění a sledování

**Spustit** v detailu tasku (`factory task run ID`) otevře dialog s workflow, zápisy, varováním na necommitnutý backlog či konfiguraci, volbou **Harness pro tento běh**, **Po úspěchu pokračovat dalšími tasky (auto continue)** a poznámkou pro agenty. Blokovaný task spustí **Spustit přesto (ignorovat nesplněné závislosti)**.

Záložka **Běhy** má **Aktivní** a **Archivované** běhy, panel **Náklady** a **Řetěz**. Detail běhu ukazuje fáze; klik na fázi otevře prompty, výstup a živé události. **Pauza** dokončí fázi a čeká, **Pokračovat** pustí další, **Zastavit** běh ukončí (worktree zůstane).

## Navázání

Detail selhaného, zastaveného nebo přerušeného běhu začíná kartou selhání: druh selhání, věta z dat běhu a podrobnosti (výtky review, cesty mimo writes, harness a model u vyčerpané kvóty). Přehled a Běhy ukazují u selhaného běhu jeho druh. Z karty běh nech pokračovat tlačítkem **Pokračovat** (v detailu tasku **Navázat**, obojí s volitelnou poznámkou), v CLI `factory task retry ID`, nebo task **Zrušit task**. Pokračuje ve stejné větvi: hotové fáze se neopakují, base se nejdřív stáhne a větev přebázuje. **Spustit** naopak začne nový běh od začátku. U zápisu mimo writes karta nabídne **Povolit tyto cesty a pokračovat** (v CLI `factory task retry ID --allow-writes`): přidá cesty do writes tasku, commitne backlog do base a běh pokračuje. Cesty v `protected_files`, v backlogu a v hlavním checkoutu nepřidá a karta řekne proč. Když agent neměl co dělat (`nothing_to_do`, zadání žádá jen změnu backlogu), karta nabídne **Hotovo**: task dostane `done` v base se záznamem „bez změn“ a důvodem agenta. U vyčerpané kvóty karta nabídne **Pokračovat s jiným harnessem** (v CLI `factory task retry ID --harness NAME`): vybereš jen z harnessů povolených a otestovaných na tomto počítači a běh pokračuje se všemi agenty na nich. Se zálohou factory přepne sama: přednost má řetěz projektu (`quota_switch`, `factory backlog edit ID --quota-switch codex pi`), jinak jednou `fallback` z `.factory/local.yaml` či `.factory/agents.yaml`. S `quota_switch_back` začne nový běh o krok výš, až má harness limit. Přepnutí je v detailu běhu a v popisu PR. Builder, který zjistí, že práce už je hotová vrátí `already_done` s důkazem; běh skončí bez PR a task dostane `done` se záznamem „bez změn“. Staré worktree uklidí `factory task clean`.

## Follow-upy

Agenti nenechávají v repu TODO. Práci mimo rozsah ohlásí a HAIFA ji založí jako task ve stepu **TODO** projektu; writes a workflow mu zvolí agent. Práci jen pro člověka založí jako task **Pro člověka**. Když task nejde dokončit před jinou prací, dostane na ni `depends_on` a běh skončí chybou `blocked: …` bez PR.

## Schválení a CI

Úspěšný běh otevře PR a task je **Čeká na review**. Detail PR na záložce **Review** ukazuje popis, testy, verdikt revieweru a diff.

**Schválit** (`factory task approve ID`) přidá commit se `status: done`, počká na CI tohoto commitu a mergne PR. Červenou CI opraví nejvýš dvěma běhy workflow `ci-fix` do téhož PR; zůstane-li červená nebo nedoběhne do 30 minut, PR zůstane otevřený s důvodem. Azure DevOps dostane hlas approve, GitHub approve review jen s `github_approver`.

**Vrátit s poznámkou** (`factory task return ID --note "…"`) spustí nový běh na stejné větvi. **Vyřešit konflikt s base**, nebo **Dorovnat s base** (`factory task resolve ID`) přebázuje PR workflow `resolve`.

## Auto-merge

S `auto_merge` se PR mergne sám, když review schválilo, PR jde mergovat a CI je zelená (s opravami `ci-fix`). Konflikt zkusí jednou `resolve-reviewed`. Když se nepovede, PR přejde do **Čeká na review**. Zapneš ho přepínačem nebo `factory backlog auto-merge ID --on`.

## Souběh a stacked PR

`max_parallel_runs` je počet slotů repa; slot drží běh i otevřený PR. Souběžně se spustí jen task, jehož writes se nepřekrývají. Se `stacked_prs: true` task čekající na PR závislosti začne z jeho větve a mergne se až po něm.
