# Knihovna a tým

Sdílí se jen git: konfigurace a backlog v repech a knihovna ve vlastním repu. Nastavení počítače, trace DB a klíče zůstávají lokální.

## Knihovna

Knihovna je Git repo v `$HAIFA_HOME/library` s adresáři `agents/`, `workflows/`, `skills/` a `extensions/`. Repo hledá položku ve své `.factory/`, pak v knihovně, pak v semínku HAIFA.

Stránka **Knihovna** (chip knihovny) má sekce **Obsah knihovny**, **Kontrola počítače** a **Dashboard** (port). Obsah knihovny nabízí **Synchronizace** (**Stáhnout**, **Odeslat jako PR**, otevřené PR), **Obnovit výchozí agenty a workflows**, **Import…** a prohlížeč položek s historií verzí a sekcí **Repa s vlastní kopií**: **Diff**, **Přesunout kopii repa do knihovny** a **Smazat kopii z repa**. Přesun a smazání kopie jsou jen tady (v CLI `factory config move`, `factory config remove`).

## Změny jen přes pull request

Do `main` knihovny se nic nepushuje přímo. Každý zápis (`factory library push`, `factory library seed`, import, přesun kopie) HAIFA commitne lokálně a pošle jako PR: správce z větve v repu knihovny, ostatní ze svého forku. HAIFA PR knihovny nikdy nemerguje ani neschvaluje. Lokálně změna platí hned; po mergi ji stáhni (`factory library pull`). Stav ukáže `factory library status --fetch`.

Správce nastaví na `main` ruleset: povinný PR se schválením Code Owners, zákaz force push.

## Semínko

Semínko jsou výchozí agenti, rozšíření pi a skill `factory`. Instalace i aktualizace spustí `factory library seed --all`, které položky semínka v knihovně přepíše; vlastní úpravy proto patří do `.factory/` repa. Ruční `factory library seed` upravené položky ponechá (přepíše je `--take`). Novější HAIFA vynutíš `min_factory_version` v `library.yaml`.

## Nový člen týmu

1. Nainstaluj HAIFA; instalátor naklonuje výchozí knihovnu (jinou přes `factory library clone <URL>`).
2. Naklonuj repa týmu a spusť v nich `factory check`. Stav `installed` stačí, `factory init` nespouštěj.
3. Repa přidej v dashboardu.

První v týmu založí knihovnu: `factory library init --name "Knihovna týmu" --remote <URL-prázdného-repa>`. Repo bez HAIFA nainstaluje `factory init --dry-run` a pak `factory init --commit --expect <digest>`.

## Souběžná práce

Stav běhu zná jen počítač, kde běží; otevřený PR vidí všichni. Společný přehled dá sdílený databázový server (`just shared-db`, adresa v `HAIFA_DATABASE_URL`), bez přihlášení, jen v důvěryhodné síti.
