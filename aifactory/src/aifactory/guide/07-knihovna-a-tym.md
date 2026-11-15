# Knihovna a tým

Sdílí se jen git: konfigurace a backlog v repech a knihovna ve vlastním repu. Nastavení počítače, trace DB a klíče zůstávají lokální.

## Knihovna

Knihovna je Git repo v `$GIRO_HOME/library` s adresáři `agents/`, `workflows/`, `skills/` a `extensions/`. Repo hledá položku ve své `.factory/`, pak v knihovně, pak v semínku GIRO.

Stránka **Knihovna** (chip knihovny) má sekce **Obsah knihovny**, **Kontrola počítače** a **Dashboard** (port). Obsah knihovny nabízí **Synchronizace** (**Stáhnout**, **Odeslat jako PR**, otevřené PR), **Obnovit výchozí agenty a workflows**, **Import…** a prohlížeč položek s historií verzí a sekcí **Repa s vlastní kopií**: **Diff**, **Přesunout kopii repa do knihovny** a **Smazat kopii z repa**. Přesun a smazání kopie jsou jen tady (v CLI `giro config move`, `giro config remove`).

## Změny jen přes pull request

Do `main` knihovny se nic nepushuje přímo. Každý zápis (`giro library push`, `giro library seed`, import, přesun kopie) GIRO commitne lokálně a pošle jako PR: správce z větve v repu knihovny, ostatní ze svého forku. GIRO PR knihovny nikdy nemerguje ani neschvaluje. Lokálně změna platí hned; po mergi ji stáhni (`giro library pull`). Stav ukáže `giro library status --fetch`.

Správce nastaví na `main` ruleset: povinný PR se schválením Code Owners, zákaz force push.

## Semínko

Semínko obsahuje výchozí agenty, rozšíření pi a skill `factory` generovaný přes `giro --skill`. Instalace i aktualizace používají nedestruktivní `giro library seed`: týmové úpravy zůstanou jako `kept`, dirty knihovna se zachová s diagnostikou. Plán zobrazí `giro library seed --dry-run`; výslovné `--take` nahradí vybranou položku. `min_factory_version` v `library.yaml` určuje nejnižší verzi GIRO.

## Nový člen týmu

1. Nainstaluj GIRO; instalátor naklonuje výchozí knihovnu (jinou přes `giro library clone <URL>`).
2. Naklonuj repa týmu a spusť v nich `giro check`. Stav `installed` stačí, `giro init` nespouštěj.
3. Repa přidej v dashboardu.

První v týmu založí knihovnu: `giro library init --name "Knihovna týmu" --remote <URL-prázdného-repa>`. Repo bez GIRO nainstaluje `giro init --dry-run` a pak `giro init --commit --expect <digest>`.

## Souběžná práce

Stav běhu zná jen počítač, kde běží; otevřený PR vidí všichni. Společný přehled dá sdílený databázový server (`just shared-db`, adresa v `GIRO_DATABASE_URL`), bez přihlášení, jen v důvěryhodné síti.
