# Běhy a review

Běh provede workflow ve worktree a větvi `factory/<id-tasku>-<n>`.

## Spuštění a sledování

**Spustit** (`factory task run ID`) otevře workflow, zápisy, varování na necommitnuté změny, **Harness pro tento běh**, **Po úspěchu pokračovat dalšími tasky (auto continue)** a poznámku. Běžící task ani task s otevřeným PR znovu nespustíš. Nesplněné závislosti nelze obejít; stacked start je se `stacked_prs` povolený, čekají-li všechny v otevřených PR.

Záložka **Běhy** má **Aktivní** a **Archivované** běhy, panel **Náklady** a **Řetěz**. Fáze v detailu otevře prompty, výstup a živé události. **Pauza** dokončí fázi a čeká, **Pokračovat** pustí další, **Zastavit** běh ukončí (worktree zůstane).

## Navázání

Karta selhání ukazuje druh (i na Přehledu a v Bězích), důvod a podrobnosti. Z karty běh nech pokračovat tlačítkem **Pokračovat** (v detailu tasku **Navázat**, obojí s volitelnou poznámkou), v CLI `factory task retry ID`, nebo task **Zrušit task**. Pokračuje ve stejné větvi: hotové fáze se neopakují, base se nejdřív stáhne a větev přebázuje. **Spustit** naopak začne nový běh od začátku. U zápisu mimo writes karta nabídne **Povolit tyto cesty a pokračovat** (v CLI `factory task retry ID --allow-writes`): přidá cesty do writes tasku, commitne backlog do base a běh pokračuje. Cesty v `protected_files`, v backlogu a v hlavním checkoutu nepřidá a karta řekne proč. Když agent neměl co dělat (`nothing_to_do`, zadání žádá jen změnu backlogu), karta nabídne **Hotovo**: task dostane `done` v base se záznamem „bez změn“ a důvodem agenta. U vyčerpané kvóty karta nabídne **Pokračovat s jiným harnessem** (v CLI `factory task retry ID --harness NAME`): vybereš jen z harnessů povolených a otestovaných na tomto počítači a běh pokračuje se všemi agenty na nich. Se zálohou factory přepne sama: přednost má řetěz projektu (`quota_switch`, `factory backlog edit ID --quota-switch codex pi`), jinak jednou `fallback` z `.factory/local.yaml` či `.factory/agents.yaml`. S `quota_switch_back` začne nový běh o krok výš, až má harness limit. Přepnutí je v detailu běhu a v popisu PR. Je-li práce hotová, builder vrátí `already_done` s důkazem; běh skončí bez PR, task dostane `done` a záznam „bez změn“. Úklid běží před i po běhu (včetně retry, selhání a stopu); ručně `factory task clean --json`. Maže worktree hotových/zrušených tasků, uzavřených/mergnutých PR, starších běhů bez PR, osiřelé adresáře; provede `git worktree prune`. Nepotřebné větve zrušených tasků a uzavřených/mergnutých PR maže lokálně i vzdáleně. Zachová běžící běhy, otevřená PR, poslední selhaný/zastavený běh `todo`, větve checkoutů/otevřených stacked PR a necommitnuté worktree neukončených tasků (ohlásí je). Chyby hlásí jako varování; JSON: `removed[].reason`, `branch_reasons`.

## Follow-upy

Agenti nenechávají v repu TODO. Práci mimo rozsah ohlásí a HAIFA ji založí jako task ve stepu **TODO** projektu; writes a workflow mu zvolí agent. Práci jen pro člověka založí jako task **Pro člověka**. Když task nejde dokončit před jinou prací, dostane na ni `depends_on` a běh skončí chybou `blocked: …` bez PR.

## Schválení a CI

Úspěšný běh otevře PR; task je **Čeká na review**. Detail PR na záložce **Review** ukazuje popis, testy, verdikt revieweru a diff.

**Schválit** (`factory task approve ID`) přidá commit se `status: done`, počká na CI tohoto commitu a mergne PR. Červenou CI opraví nejvýš dvěma běhy workflow `ci-fix` do téhož PR; zůstane-li červená nebo nedoběhne do 30 minut, PR zůstane otevřený s důvodem. Backlog, Přehled i Review ukazují **Schváleno, čeká na CI**; detail čas schválení. **Schválit** pokus zopakuje. Merge znamená **Hotovo**, neúspěšná CI **Čeká na review**. Azure DevOps dostane hlas approve, GitHub approve review jen s `github_approver`.

**Vrátit s poznámkou** (`factory task return ID --note "…"`) spustí nový běh na stejné větvi. **Vyřešit konflikt s base**, nebo **Dorovnat s base** (`factory task resolve ID`) přebázuje PR workflow `resolve`.

## Auto-merge

S `auto_merge` se PR mergne sám, když review schválilo, PR jde mergovat a CI je zelená (s opravami `ci-fix`). Konflikt zkusí jednou `resolve-reviewed`. Když se nepovede, PR přejde do **Čeká na review**. Zapneš ho přepínačem nebo `factory backlog auto-merge ID --on`.

Řetěz auto-continue zastavený na `not_merged` naváže jednou po ručním sloučení přes **Schválit** (`factory task approve ID`) nebo v hostingu (až ho zjistí obnova PR v dashboardu), se stejnými pravidly výběru jako po auto-merge. Task se sloučeným PR a stavem `todo` v base se znovu nespustí; dorovnej ho přes `factory backlog sync` a sloučení jeho změn do base.

## Souběh a stacked PR

`max_parallel_runs` je počet slotů repa; slot drží běh i otevřený PR. Souběžně běží jen tasky s nepřekrývajícími se writes. Se `stacked_prs: true` task čekající na PR závislosti začne z jeho větve a mergne se až po něm.
