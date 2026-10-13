# Knihovna

Knihovna je Git repo v domovském adresáři HAIFA (`$HAIFA_HOME/library`, výchozí `~/.config/haifa/library`, jiná cesta přes `HAIFA_LIBRARY`). Má soubor `library.yaml` (jméno, id, `min_factory_version`, verze semínka) a adresáře `agents/`, `workflows/`, `skills/` a `extensions/`. Obsahuje položky, které repa dědí, takže je nemusíš kopírovat do každého repa:

- **agent:** složka s `agent.yaml` (výchozí harness, model, thinking, povolené cesty) a prompty `system.md` a `user.md`,
- **workflow:** YAML soubor s kroky běhu,
- **skill:** složka skillu, kterou běh nakopíruje do worktree,
- **extension:** rozšíření harnessu pi.

Jméno položky je z malých písmen, číslic a pomlček (nejvýš 48 znaků); položka má nejvýš 200 souborů a 2 MB. Každá změna obsahu je nová verze (otisk obsahu); `factory library show TYP JMÉNO` ukáže soubory a historii verzí.

## Dědičnost

Repo hledá agenty, workflow, skilly a rozšíření nejdřív ve své `.factory/`, potom v knihovně, a bez knihovny v semínku dodaném s HAIFA. Kopie v repu má přednost. Mezi knihovnou a repem se nic nesynchronizuje: co repo nemá, zdědí z knihovny při každém běhu, a běh si do trace zapíše commit knihovny, ze kterého četl.

- **Přesunout do knihovny** (`factory config move TYP JMÉNO`) přesune kopii z repa do knihovny; repo ji pak dědí.
- **Odebrat z repa** (`factory config remove TYP JMÉNO`) smaže kopii z repa; platí pak verze z knihovny.

Obojí umí i záložka **Factory** repa v dashboardu, včetně náhledu změn před potvrzením.

## Založení a sdílení

Výchozí týmová knihovna je [HAIFA-LIBRARY](https://github.com/janbkrejci/HAIFA-LIBRARY) (větev `main`); instalátor ji naklonuje sám (kapitola [Instalace](#/guide/instalace)). Firemní instalace ji přepíše proměnnou `HAIFA_LIBRARY_URL`. Na stránce **Tento počítač** dashboardu má pole **URL týmové knihovny** výchozí adresu předvyplněnou; knihovnu tam také založíš ze semínka. Z příkazové řádky:

```bash
factory library clone
factory library clone <URL-jiné-knihovny>
factory library clone --seed-fallback
factory library init --name "Knihovna týmu" --remote <URL-prázdného-repa>
```

`factory library clone` bez URL naklonuje výchozí knihovnu. S `--seed-fallback` založí při neúspěšném klonu lokální knihovnu ze semínka a vypíše varování.

## Změny knihovny jen přes pull request

Má-li knihovna remote, žádná změna nejde přímo do jeho větve `main`. Každý zápis, který by šel na remote (`factory library push`, `factory library seed`, import, **Přesunout do knihovny**), HAIFA commitne do lokální knihovny a pošle jako pull request do `main` knihovny:

- **kdo do repa knihovny smí zapisovat** (správce), pošle PR z nové větve `haifa-library/…` přímo v repu knihovny,
- **kdo zápis nemá**, pošle PR ze svého forku: HAIFA ho vytvoří (`gh repo fork`), větev nahraje do forku a `gh pr create` otevře PR proti knihovně.

Potřebuješ `gh` přihlášený k GitHubu (`gh auth login`, `gh auth setup-git`). U remote mimo GitHub HAIFA nahraje jen větev `haifa-library/…` a PR otevřeš ručně.

Lokální knihovna platí hned, i když PR ještě není mergnutý: repa na tvém počítači dědí novou verzi okamžitě. Mergování je jen na správci knihovny; HAIFA PR nikdy nemerguje sama (žádné `--admin`, žádný auto-merge) a neposílá ani vlastní schválení. Po mergi stáhni změny (`factory library pull`, v dashboardu **Stáhnout**): pull převede tvoje lokální commity na nový `main` a ty, které už v něm jsou, vypustí. Když se nedají převést bez konfliktu, pull nic nezmění a skončí `library_diverged`.

```bash
factory library status --fetch
factory library pull
factory library push
```

`factory library status` ukáže stav synchronizace (`sync_state`) a otevřené PR, které jsi z knihovny poslal (`--fetch` se GitHubu zeptá, které jsou stále otevřené):

| Stav | Význam |
|---|---|
| **Lokální změny** (`local`) | knihovna má commity, které nejsou v žádném otevřeném PR, nebo necommitnuté změny; pošli je přes `factory library push` |
| **Čeká v PR** (`pending`) | všechny lokální změny čekají v otevřených PR na správce knihovny |
| **Srovnáno s remote** (`synced`) | lokální knihovna je stejná jako `main` knihovny |
| **Pozadu** (`behind`) | remote má změny, které nemáš; stáhni je |

Když správce PR zavře bez mergnutí, změna se po kontrole remote vrátí do stavu **Lokální změny**. Zápis do knihovny, která je za remote pozadu, HAIFA odmítne (`library_behind`); stáhni změny a zkus to znovu.

Chip v horní liště ukazuje **Knihovna OK** (odkaz na stránku Knihovna), nebo **Založit knihovnu**, když knihovna chybí. Na stránce **Knihovna** je panel **Synchronizace** se stavem, odkazy na otevřené pull requesty a tlačítky **Zkontrolovat remote**, **Stáhnout** a **Odeslat jako PR**; knihovnu bez remote propojíš s prázdným repem tlačítkem **Propojit a odeslat**.

## Nastavení repa knihovny pro správce

HAIFA nikdy nepushuje do `main` knihovny, ale git to technicky nezakáže. Správce knihovny proto na GitHubu (**Settings → Rules → Rulesets**) nastaví na větev `main` ruleset:

- **Require a pull request before merging** s alespoň jedním schválením a s **Require review from Code Owners**, kde vlastníkem (`CODEOWNERS`) je správce,
- **Restrict deletions** a **Block force pushes**,
- žádný bypass kromě správce (nebo ani pro něj).

Ostatní do repa zápis nepotřebují: posílají PR ze svých forků. Mergovat smí jen správce.

## Prohlížení a import

```bash
factory library list
factory library list --type workflow
factory library show agent builder
factory library import ~/moje/agenti/reviewer --type agent
factory library import ~/moje/workflow/rychly.yaml --type workflow --dry-run
```

Stránka **Knihovna** v dashboardu má záložky **Agenti**, **Workflow**, **Skilly** a **Rozšíření pi**. Detail položky ukáže **Soubory · jen čtení**, **Historii verzí** a **Repa s vlastní kopií** s tlačítky **Diff** a **Přesunout kopii repa do knihovny**. Tlačítko **Import…** importuje složku z domovského adresáře.

Import přijme jen cesty pod tvým domovským adresářem. Položka se před zápisem ověří; stejný obsah nic nezmění, jiný obsah pod existujícím jménem je nová verze.

## Semínko a aktualizace

Semínko je výchozí sada agentů (planner, scout, builder, tester, test-reviewer, reviewer, documenter) a rozšíření pi `subagents` dodaná s HAIFA; vestavěná workflow jsou přímo v balíčku. Po aktualizaci HAIFA převezmeš nové verze přes `factory library seed` (kapitola [Aktualizace a vydání](#/guide/aktualizace)), v dashboardu tlačítkem **Obnovit výchozí agenty a workflows** na stránce Knihovna. Položky upravené týmem seed nepřepíše, jen ukáže rozdíl; přepsat je můžeš zaškrtnutím **Přepsat … výchozí verzí** (v CLI `--take`).

## Minimální verze HAIFA

Vyžaduje-li obsah knihovny novější HAIFA, nastav v `library.yaml` knihovny `min_factory_version`, změnu commitni a odešli (`factory library push` pošle PR). Kdo má starší HAIFA, uvidí v `factory check` chybu `factory_outdated`.
