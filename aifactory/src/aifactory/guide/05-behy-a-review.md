# Běhy a review

Běh provede workflow tasku ve vlastním worktree a větvi `factory/<id-tasku>-<n>`.

## Spuštění a sledování

**Spustit** (`factory task run ID`) otevře workflow, zápisy, varování na necommitnuté změny, **Harness pro tento běh**, **Po úspěchu pokračovat dalšími tasky (auto continue)** a poznámku. Běžící task ani task s otevřeným PR znovu nespustíš. Nesplněné závislosti nelze obejít; stacked start je se `stacked_prs` povolený, čekají-li všechny v otevřených PR.

Záložka **Běhy** má **Aktivní** a **Archivované** běhy, panel **Náklady** a **Řetěz**. Detail běhu ukazuje fáze; klik na fázi otevře prompty, výstup a živé události. **Pauza** dokončí fázi a čeká, **Pokračovat** pustí další, **Zastavit** běh ukončí (worktree zůstane).

## Navázání

Karta selhání ukazuje druh, důvod a podrobnosti: výtky review, cesty mimo writes nebo vyčerpanou kvótu. Druh selhání vidíš i na Přehledu a v Bězích. Z karty běh nech pokračovat tlačítkem **Pokračovat** (v detailu tasku **Navázat**, obojí s volitelnou poznámkou), v CLI `factory task retry ID`, nebo task **Zrušit task**. Pokračuje ve stejné větvi: hotové fáze se neopakují, base se nejdřív stáhne a větev přebázuje. **Spustit** naopak začne nový běh od začátku. U zápisu mimo writes karta nabídne **Povolit tyto cesty a pokračovat** (v CLI `factory task retry ID --allow-writes`): přidá cesty do writes tasku, commitne backlog do base a běh pokračuje. Cesty v `protected_files`, v backlogu a v hlavním checkoutu nepřidá a karta řekne proč. Když agent neměl co dělat (`nothing_to_do`, zadání žádá jen změnu backlogu), karta nabídne **Hotovo**: task dostane `done` v base se záznamem „bez změn“ a důvodem agenta. U vyčerpané kvóty karta nabídne **Pokračovat s jiným harnessem** (v CLI `factory task retry ID --harness NAME`): vybereš jen z harnessů povolených a otestovaných na tomto počítači a běh pokračuje se všemi agenty na nich. Se zálohou factory přepne sama: přednost má řetěz projektu (`quota_switch`, `factory backlog edit ID --quota-switch codex pi`), jinak jednou `fallback` z `.factory/local.yaml` či `.factory/agents.yaml`. S `quota_switch_back` začne nový běh o krok výš, až má harness limit. Přepnutí je v detailu běhu a v popisu PR. Builder, který zjistí, že práce už je hotová vrátí `already_done` s důkazem; běh skončí bez PR a task dostane `done` se záznamem „bez změn“. Úklid probíhá automaticky před i po každém běhu (také retry, selhání a stopu); ručně jej spustí `factory task clean --json`. Odstraní worktree tasků `done` a `cancelled`, uzavřených či mergnutých PR a starších běhů bez PR, osiřelé adresáře v nastaveném adresáři worktree a provede `git worktree prune`. U zrušených tasků a uzavřených či mergnutých PR odstraní i nepotřebné větve `factory/` lokálně a na remote. Běžící běh, otevřené PR a poslední selhaný či zastavený běh tasku `todo` zůstávají zachovány pro pokračování. Worktree s necommitnutými změnami se u neukončených tasků pouze nahlásí. Větev používaná checkoutem nebo otevřeným stacked PR zůstane. Chyby úklidu jsou jen varování; JSON uvádí důvody v `removed[].reason` a `branch_reasons`.

## Follow-upy

Agenti nenechávají v repu TODO. Práci mimo rozsah ohlásí a HAIFA ji založí jako task ve stepu **TODO** projektu; writes a workflow mu zvolí agent. Práci jen pro člověka založí jako task **Pro člověka**. Když task nejde dokončit před jinou prací, dostane na ni `depends_on` a běh skončí chybou `blocked: …` bez PR.

## Schválení a CI

Úspěšný běh otevře PR a task je **Čeká na review**. Detail PR na záložce **Review** ukazuje popis, testy, verdikt revieweru a diff.

**Schválit** (`factory task approve ID`) přidá commit se `status: done`, počká na CI tohoto commitu a mergne PR. Červenou CI opraví nejvýš dvěma běhy workflow `ci-fix` do téhož PR; zůstane-li červená nebo nedoběhne do 30 minut, PR zůstane otevřený s důvodem. Backlog, Přehled i Review ukazují **Schváleno, čeká na CI**; detail čas schválení. **Schválit** pokus zopakuje. Merge znamená **Hotovo**, neúspěšná CI **Čeká na review**. Azure DevOps dostane hlas approve, GitHub approve review jen s `github_approver`.

**Vrátit s poznámkou** (`factory task return ID --note "…"`) spustí nový běh na stejné větvi. **Vyřešit konflikt s base**, nebo **Dorovnat s base** (`factory task resolve ID`) přebázuje PR workflow `resolve`.

## Auto-merge

S `auto_merge` se PR mergne sám, když review schválilo, PR jde mergovat a CI je zelená (s opravami `ci-fix`). Konflikt zkusí jednou `resolve-reviewed`. Když se nepovede, PR přejde do **Čeká na review**. Zapneš ho přepínačem nebo `factory backlog auto-merge ID --on`.

## Souběh a stacked PR

`max_parallel_runs` je počet slotů repa; slot drží běh i otevřený PR. Souběžně se spustí jen task, jehož writes se nepřekrývají. Se `stacked_prs: true` task čekající na PR závislosti začne z jeho větve a mergne se až po něm.
