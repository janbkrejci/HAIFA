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

Na stránce **Tento počítač** dashboardu knihovnu založíš ze semínka, nebo naklonuješ týmovou z URL. Z příkazové řádky:

```bash
factory library init --name "Knihovna týmu" --remote <URL-prázdného-repa>
factory library clone <URL-týmové-knihovny>
```

Má-li knihovna remote, každý zápis do ní (import, seed, přesun z repa) nový commit rovnou odešle, a to bez force. Když tě tým mezitím předběhl, zápis odmítne (`library_behind`); stáhni změny a zkus to znovu.

```bash
factory library status --fetch
factory library pull
factory library push
```

Chip v horní liště ukazuje **Knihovna OK** (odkaz na stránku Knihovna), nebo **Založit knihovnu**, když knihovna chybí. Na stránce **Knihovna** je panel **Synchronizace** s tlačítky **Zkontrolovat remote**, **Stáhnout** a **Odeslat**; knihovnu bez remote propojíš s prázdným repem tlačítkem **Propojit a odeslat**.

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

Vyžaduje-li obsah knihovny novější HAIFA, nastav v `library.yaml` knihovny `min_factory_version` a změnu commitni a odešli. Kdo má starší HAIFA, uvidí v `factory check` chybu `factory_outdated`.
