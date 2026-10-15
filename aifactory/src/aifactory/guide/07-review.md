# Review a merge

Výsledkem úspěšného běhu je pull request z větve běhu do base. Na záložce **Review** ho schválíš, vrátíš k přepracování, nebo necháš vyřešit konflikt.

## Seznam

**Čeká na review** jsou PR tasků, které čekají na tebe; **Čeká na automerge PR** jsou PR tasků se zapnutým auto-merge, které factory mergne sama (skupina se ukáže, jen když nějaký takový PR je); **Ostatní otevřené PR** jsou další PR repa (například s běžícím během). **Zobrazit hotové** přidá sloučené a zavřené. Sloupce: task, projekt, mergeabilita (lze mergovat, konflikt, neznámé), běh, náklady, tokeny a odkaz na PR.

## Detail pull requestu

- hlavička: větev → base, mergeabilita, stav PR, náklady a odkaz do hostingu,
- **Popis PR**,
- **Běhy** tasku,
- **Gates a testy:** výsledky kontrol a testů z běhu,
- **Verdikt revieweru:** schváleno nebo neschváleno, blokující nálezy a požadavky,
- **Diff** změn.

Popis PR začíná shrnutím od agentů běhu: **Cíl**, **Co bylo uděláno**, **Co uděláno nebylo** (včetně nových tasků v backlogu, nebo „nic“) a případně **Důležité pro schválení**. Zadání tasku se do popisu nekopíruje. Technické podrobnosti (agenti, gates a testy, review, náklady) následují až za shrnutím. Běh, který jen řešil konflikt s base, shrnutí z předchozího popisu ponechá.

Sloučený nebo zavřený PR je jen pro čtení. Dokud na PR běží běh (například vrácení nebo řešení konfliktu), akce počkají.

## Schválení

**Schválit** se zeptá „Schválit a mergovat PR … do base?“ a pak:

1. přidá do větve commit se `status: done` a řádkem v `## Běhy` tasku a odešle ho,
2. počká na CI kontroly v hostingu, a to na kontroly právě odeslaného commitu (viz oddíl CI před merge),
3. v Azure DevOps odešle hlas „approve“ za přihlášeného uživatele (GitHub vlastní schválení autora nepovoluje, lokální provider review nemá),
4. mergne PR podle `merge_strategy` repa (výchozí squash),
5. srovná lokální base s remote a smaže worktree větve.

Task s nesplněnými závislostmi (`depends_on`) schválit nejde (chyba `task_blocked`); nejdřív dokonči tasky, které ho blokují.

Po merge nabídne **Další PR ke schválení**. Z CLI: `factory task approve ID`.

Na GitHubu může čekání na CI trvat dlouho, proto dashboard schvaluje na pozadí: ukáže „Schvalování běží na pozadí…“ a výsledek (merge, nebo důvod, proč PR zůstal otevřený) uvidíš v detailu PR a v **Bězích**. U lokálního provideru a Azure DevOps (HAIFA z nich CI kontroly nečte) proběhne merge hned jako dřív.

### CI před merge

Ruční schválení i auto-merge mergují jen PR, jehož CI je zelená:

- PR bez kontrol (lokální provider, Azure DevOps, repo bez CI) se merguje hned. Na GitHubu HAIFA nejdřív chvíli (90 s) počká, než se kontroly nového commitu objeví.
- Běžící kontroly HAIFA čeká nejvýš 30 minut. Když do té doby nedoběhnou, PR zůstane otevřený s důvodem `checks_pending`.
- Když je některá kontrola červená, HAIFA spustí opravný běh workflow `ci-fix` na větvi téhož PR (žádný nový PR). Agent dostane názvy červených kontrol a jejich log (na GitHubu výstup selhaných kroků). Opravu otestuje, nechá zkontrolovat review, commitne a odešle do téhož PR; pak HAIFA znovu čeká na CI. Opravný běh je vidět v **Bězích** se spouštěčem `auto-ci-fix`.
- Opravné běhy jsou nejvýš 2. Když je CI i potom červená, PR zůstane otevřený s důvodem `checks_failing`; když opravný běh selže, s důvodem `ci_fix_failed`.

Důvod, proč PR zůstal otevřený, se zapíše stejně jako chyby auto-merge: detail PR ho ukáže a CLI ho vypíše. Opravený PR schválíš znovu.

## Vrácení s poznámkou

**Vrátit s poznámkou** otevře pole „Co má agent změnit…“. **Vrátit** spustí nový běh na stejné větvi; poznámka se připojí k zadání a pull request se aktualizuje. Piš konkrétně, co je špatně a jak poznáš, že je to správně. Z CLI: `factory task return ID --note "…"`.

## Konflikty s base

Když se base mezitím změnila a PR nejde mergovat, nabídne detail **Vyřešit konflikt s base**; bez konfliktu **Dorovnat s base**. Obojí spustí workflow `resolve`: rebase na aktuální base, při konfliktu agent, který smí měnit jen konfliktní soubory, přegenerování generovaných souborů (`generated` v konfiguraci), testy a odeslání. Selhaný pokus nechá větev, jak byla. Z CLI: `factory task resolve ID`.

## Auto-merge

Se zapnutým `auto_merge` (na tasku, stepu nebo projektu) se PR mergne sám, když:

1. běh skončil úspěšně a otevřel PR,
2. workflow má krok review a poslední review schválilo bez blokujících nálezů,
3. PR je otevřený a jde mergovat,
4. CI je zelená nebo PR žádné kontroly nemá. Auto-merge schvaluje stejně jako ruční schválení, takže čeká na kontroly commitu se `status: done` a červenou CI opravuje nejvýš dvěma běhy `ci-fix` do téhož PR (viz oddíl CI před merge). Když CI zůstane červená nebo nedoběhne do 30 minut, PR zůstane otevřený s důvodem `checks_failing`, `checks_pending` nebo `ci_fix_failed`.

Při konfliktu zkusí jednou automaticky `resolve-reviewed`. Když se merge nepovede, PR čeká na ruční schválení a detail ukáže „Auto-merge nesloučil: … – schval ručně.“ Workflow bez review se nikdy nemerguje automaticky.

Dokud auto-merge PR nemergne, je PR na Přehledu, v Review i na Backlogu ve stavu **Čeká na automerge PR**: nemusíš nic dělat. Když se auto-merge nepovede, přejde PR do **Čeká na review** a čeká na tebe.

Auto-merge zapneš přepínačem **Auto-merge** ve stromu backlogu, ve formuláři tasku, nebo `factory backlog auto-merge ID --on` (task: `factory task edit ID --auto-merge on`). Změnu backlogu nezapomeň commitnout.

## Git hosting

Provider nastavuje `git_provider` v konfiguraci repa:

| Provider | Pull request | Potřebuješ |
| --- | --- | --- |
| `local` | Větev; merge je lokální merge do base (a push, má-li repo remote). | nic |
| `github` | PR na GitHubu. | `gh` přihlášené k účtu s právem zápisu |
| `azure` | PR v Azure DevOps; schválení posílá hlas. | `az` s rozšířením `azure-devops`, `az login` nebo `AZURE_DEVOPS_EXT_PAT`, sekce `azure` v konfiguraci |

V Azure DevOps se hlas autora započítá do minima reviewerů jen s politikou **Allow requestors to approve their own changes**. HAIFA politiky větví nemění a merge nevynucuje.

## PR mergnuté mimo HAIFA

Když někdo mergne PR přímo v hostingu, task zůstane v backlogu nehotový. `factory backlog sync` otevře jeden PR, který takové tasky označí jako hotové.
