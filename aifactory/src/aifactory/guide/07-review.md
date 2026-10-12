# Review a merge

Výsledkem úspěšného běhu je pull request z větve běhu do base. Na záložce **Review** ho schválíš, vrátíš k přepracování, nebo necháš vyřešit konflikt.

## Seznam

**Čeká na review** jsou PR tasků, které čekají na tebe; **Ostatní otevřené PR** jsou další PR repa. **Zobrazit hotové** přidá sloučené a zavřené. Sloupce: task, projekt, mergeabilita (lze mergovat, konflikt, neznámé), běh, náklady, tokeny a odkaz na PR.

## Detail pull requestu

- hlavička: větev → base, mergeabilita, stav PR, náklady a odkaz do hostingu,
- **Popis PR**,
- **Běhy** tasku,
- **Gates a testy:** výsledky kontrol a testů z běhu,
- **Verdikt revieweru:** schváleno nebo neschváleno, blokující nálezy a požadavky,
- **Diff** změn.

Sloučený nebo zavřený PR je jen pro čtení. Dokud na PR běží běh (například vrácení nebo řešení konfliktu), akce počkají.

## Schválení

**Schválit** se zeptá „Schválit a mergovat PR … do base?“ a pak:

1. přidá do větve commit se `status: done` a řádkem v `## Běhy` tasku a odešle ho,
2. v Azure DevOps odešle hlas „approve“ za přihlášeného uživatele (GitHub vlastní schválení autora nepovoluje, lokální provider review nemá),
3. mergne PR podle `merge_strategy` repa (výchozí squash),
4. srovná lokální base s remote a smaže worktree větve.

Po merge nabídne **Další PR ke schválení**. Z CLI: `factory task approve ID`.

## Vrácení s poznámkou

**Vrátit s poznámkou** otevře pole „Co má agent změnit…“. **Vrátit** spustí nový běh na stejné větvi; poznámka se připojí k zadání a pull request se aktualizuje. Piš konkrétně, co je špatně a jak poznáš, že je to správně. Z CLI: `factory task return ID --note "…"`.

## Konflikty s base

Když se base mezitím změnila a PR nejde mergovat, nabídne detail **Vyřešit konflikt s base**; bez konfliktu **Dorovnat s base**. Obojí spustí workflow `resolve`: rebase na aktuální base, při konfliktu agent, který smí měnit jen konfliktní soubory, přegenerování generovaných souborů (`generated` v konfiguraci), testy a odeslání. Selhaný pokus nechá větev, jak byla. Z CLI: `factory task resolve ID`.

## Auto-merge

Se zapnutým `auto_merge` (na tasku, stepu nebo projektu) se PR mergne sám, když:

1. běh skončil úspěšně a otevřel PR,
2. workflow má krok review a poslední review schválilo bez blokujících nálezů,
3. PR je otevřený a jde mergovat,
4. kontroly v hostingu (CI) doběhly a žádná není červená. Na běžící kontroly auto-merge počká nejvýš 30 minut. Když do té doby nedoběhnou, PR zůstane otevřený s důvodem `checks_pending`. Na GitHubu chvíli počká i na to, až se kontroly čerstvého PR objeví. PR bez kontrol (lokální provider, repo bez CI) se merguje hned.

Při konfliktu zkusí jednou automaticky `resolve-reviewed`. Když se merge nepovede, PR čeká na ruční schválení a detail ukáže „Auto-merge nesloučil: … – schval ručně.“ Workflow bez review se nikdy nemerguje automaticky.

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
