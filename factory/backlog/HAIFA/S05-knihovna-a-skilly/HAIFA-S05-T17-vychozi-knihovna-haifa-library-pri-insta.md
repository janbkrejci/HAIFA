---
id: HAIFA-S05-T17
title: Výchozí knihovna HAIFA-LIBRARY při instalaci a změny knihovny jen přes PR
status: todo
depends_on: []
---

## Zadání
Výchozí týmová knihovna je https://github.com/janbkrejci/HAIFA-LIBRARY (veřejné repo, větev `main`). Instalace HAIFA ji má rovnou naklonovat a lokální změny knihovny se mají do ní dostávat jen pull requestem.

Dnes `install.ps1` / `install.sh` volají `factory library init` (lokální knihovna ze semínka bez remote). `factory library clone URL` existuje, ale URL se musí zadat. Průvodce v dashboardu má pole „URL týmové knihovny“ prázdné. `factory library seed`, import a „Přesunout do knihovny“ pushují přímo do `main` knihovny, když má remote.

Stav repa HAIFA-LIBRARY k 12. 10. 2026: na `main` není ochrana větve ani ruleset, jediný collaborator je `janbkrejci` (admin). Mergovat tedy může jen on. Přímý push do `main` je ale technicky možný a ostatní do repa nemají zápis, takže PR musí posílat z forku.

Zadání:
1. Výchozí URL knihovny je konstanta v kódu, kterou firemní instalace přepíše proměnnou prostředí (podobně jako `HAIFA_UPDATE_REPO`). `factory library clone` bez URL naklonuje výchozí knihovnu. Průvodce v dashboardu ji má předvyplněnou.
2. Instalátor (`install.ps1`, `install.sh`) na stroji bez knihovny naklonuje výchozí knihovnu místo `library init`. Bez sítě nebo při selhání klonu založí lokální knihovnu ze semínka a vypíše varování. Existující knihovnu nemění.
3. Každá změna knihovny, která by šla na remote (`library push`, `library seed`, import, „Přesunout do knihovny“), jde jako pull request do `main` výchozí knihovny, nikdy přímým pushem. Kdo nemá do repa zápis, pošle PR z forku (`gh repo fork`, push do forku, `gh pr create` proti upstreamu). Kdo zápis má, pošle PR z větve v repu. Lokální knihovna dál funguje hned i bez mergnutého PR, a po mergi se srovná pullem.
4. Dashboard u knihovny ukáže otevřené PR, které operátor poslal, a odkáže na ně. Stav knihovny rozliší „lokální změny“, „čeká v PR“ a „srovnáno s remote“.
5. Mergování PR zůstává na správci knihovny. HAIFA ho nikdy nemerguje sama (žádné `--admin`, žádný auto-merge) a vlastní schválení neposílá.
6. Příručka (Instalace, Knihovna, Práce v týmu) popíše výchozí knihovnu, posílání změn PR a doporučené nastavení repa knihovny pro správce: ruleset na `main` s povinným PR, schválením správcem a zákazem přímého pushe i force pushe. Rozhodnutí o změnách knihovny přes PR se zapíše do `docs/decisions.md`.

Hotovo, když:
- čistá instalace na Windows i Linuxu skončí s knihovnou naklonovanou z HAIFA-LIBRARY, a bez sítě s lokální ze semínka,
- přidání položky do knihovny u uživatele bez zápisu do repa vytvoří fork a PR, u správce PR z větve, a nikdy nepushne do `main`,
- testy (bez sítě, s falešným `gh` a lokálním remote) pokryjí klon s výchozí URL, fallback bez sítě, PR z větve i z forku a to, že přímý push do `main` knihovny nikdy neproběhne.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
