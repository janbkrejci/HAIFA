# Běhy a review

Běh provede workflow ve worktree a větvi `factory/<id-tasku>-<n>`.

## Spuštění a sledování

**Spustit** (`factory task run ID`) otevře workflow, zápisy, varování na necommitnuté změny, **Harness pro tento běh** a poznámku. Automatické pokračování řídí nastavení repozitáře na [Přehledu](#/overview). Běžící task ani task s otevřeným PR nespustíš. Nesplněné závislosti nelze obejít; stacked start je se `stacked_prs` povolený, čekají-li všechny v otevřených PR.

Záložka **Běhy** má **Aktivní** a **Archivované** běhy, panel **Náklady** a **Řetěz**. Fáze v detailu otevře prompty, výstup a živé události. **Pauza** dokončí fázi a čeká, **Pokračovat** pustí další, **Zastavit** běh ukončí (worktree zůstane).

## Navázání

Karta selhání ukazuje druh, důvod a podrobnosti. **Pokračovat** (v detailu **Navázat**,
`factory task retry ID`) obnoví stejnou větev: hotové fáze neopakuje, nejdřív aktualizuje
base a přebázuje. **Spustit** začne znovu; **Zrušit task** task zruší.

**Povolit tyto cesty a pokračovat** (`factory task retry ID --allow-writes`) rozšíří writes
v base. Cesty chráněné `protected_files`, backlog a hlavní checkout nepovolí.
**Hotovo** při `nothing_to_do` zapíše důvod a stav done bez PR; totéž platí pro doložené
`already_done`. **Pokračovat s jiným harnessem** (`factory task retry ID --harness NAME`)
obnoví běh na povoleném harnessu. Automaticky má přednost projektový `quota_switch`,
pak `fallback` z `.factory/local.yaml` či `.factory/agents.yaml`; `quota_switch_back`
vrací nové běhy výš v řetězu. Přepnutí ukazuje detail a PR.

Úklid běží automaticky, ručně `factory task clean --json`. Odstraní nepotřebné worktrees
a větve i na remote; zachová běžící běhy, otevřené PR, používané větve, poslední
selhaný/zastavený todo běh a necommitnuté worktrees. Chyby hlásí jako varování.

## Follow-upy

Práci mimo rozsah agent ohlásí jako task do **TODO**, s writes a workflow; lidskou práci
jako **Pro člověka**. Nutná podmínka přidá `depends_on` a ukončí běh jako `blocked`.

## Místní automatizace

Auto continue a auto merge jsou vypnuté. Zapneš je na Přehledu nebo
`factory config local set --auto-continue on --repo PATH` či `--auto-merge on`.
Platí ihned pro místní HAIFA_HOME, bez commitu. Zapnutí práci nespouští.
Vypnutí continue nechá přijaté běhy doběhnout, zabrání dalším startům i retry;
`--auto` ho neobejde. Převzetí starých voleb popisuje kapitola aktualizace.

## Schválení a CI

Úspěšný běh otevře PR; task je **Čeká na review**. Detail PR na záložce **Review** ukazuje popis, testy, verdikt revieweru a diff.

**Schválit** (`factory task approve ID`) commitne `status: done`, počká na CI a mergne PR.
Červenou CI opraví nejvýš dva běhy `ci-fix`; po neúspěchu či 30 minutách zůstane PR otevřený.
**Schváleno, čeká na CI** ukazuje čekání, **Čeká na review** neúspěch, **Hotovo** merge.
Schválení lze zopakovat. Azure dostane approve hlas, GitHub review jen s `github_approver`.

**Vrátit s poznámkou** (`factory task return ID --note "…"`) spustí nový běh na stejné větvi. **Vyřešit konflikt s base**, nebo **Dorovnat s base** (`factory task resolve ID`) přebázuje PR workflow `resolve`.

## Auto-merge

Místní auto merge schválí a mergne PR po schváleném review a zelené CI. Konflikt zkusí
jednou `resolve-reviewed`, jinak ukáže **Čeká na review**.

Řetěz zastavený na `not_merged` naváže jednou i po ručním merge přes **Schválit** nebo
hosting (po obnově dashboardu). Sloučený task se znovu nespustí; stav todo dorovnej
`factory backlog sync` a sloučením sync PR.

## Souběh a stacked PR

`max_parallel_runs` je počet slotů repa; slot drží běh i otevřený PR. Souběžně běží jen tasky s nepřekrývajícími se writes. Se `stacked_prs: true` task čekající na PR závislosti začne z jeho větve a mergne se až po něm.
