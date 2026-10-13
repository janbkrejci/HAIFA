# Výchozí knihovna HAIFA-LIBRARY a změny knihovny přes pull request

1. Instalace (`install.sh`, `install.bat`) na počítači bez knihovny spustí `factory library clone --seed-fallback`: naklonuje výchozí knihovnu https://github.com/janbkrejci/HAIFA-LIBRARY.git. Když klon selže (bez sítě, bez přístupu), založí lokální knihovnu ze semínka a vypíše varování. Existující knihovnu instalace nemění (už ani nespouští `factory library seed`).
2. Firemní instalace nastaví jinou knihovnu proměnnou `HAIFA_LIBRARY_URL` (celá git URL). `factory library clone` bez URL naklonuje výchozí knihovnu, průvodce na stránce **Tento počítač** ji má předvyplněnou.
3. Každá změna knihovny s remote (`factory library push`, `factory library seed`, import, **Přesunout do knihovny**) se commitne lokálně a odejde jako pull request do větve knihovny (`main`), nikdy přímým pushem:
   - kdo do repa knihovny smí zapisovat (`viewerPermission` ADMIN, MAINTAIN nebo WRITE), pošle PR z větve `haifa-library/<čas>-<sha>` v repu knihovny,
   - ostatní z forku: `gh repo fork`, push větve do forku, `gh pr create --head <login>:<větev>` proti knihovně,
   - u remote mimo GitHub se nahraje jen větev a PR se otevře ručně.
4. Lokální knihovna platí hned. Po mergi `factory library pull` převede lokální commity na nový `main` (rebase) a mergnuté vypustí; konflikt skončí `library_diverged` a nic nemění.
5. `factory library status` vrací `sync_state` (`unshared`, `local` = lokální změny, `pending` = čeká v PR, `behind`, `synced` = srovnáno s remote), `unsent` a `pull_requests` (otevřené PR poslané z knihovny; `--fetch` se zeptá `gh pr list --author @me`, které jsou stále otevřené). Stránka **Knihovna** ukáže stav, odkazy na otevřené PR a tlačítko **Odeslat jako PR**.
6. HAIFA PR knihovny nikdy nemerguje, neschvaluje a nepoužívá `--admin` ani auto-merge.

Odeslané změny si knihovna pamatuje v `.git/haifa-pull-requests.json` podle `git patch-id`, takže je pozná i po rebase. Nový kód chyby: `pr_failed` (selhal `gh`; knihovna se nezměnila).

## Rozhodnutí pro `docs/decisions.md`

`docs/decisions.md` je mimo povolené cesty tohoto tasku; do sekce **Konfigurace a knihovna** patří tento záznam:

> **Změny knihovny jen přes pull request.** Výchozí týmová knihovna je HAIFA-LIBRARY (`HAIFA_LIBRARY_URL` ji přepíše) a instalace ji naklonuje, bez sítě založí lokální ze semínka. Zápis do knihovny s remote (push, seed, import, přesun z repa) se commitne lokálně a pošle jako pull request do `main` knihovny: s právem zápisu z větve v repu, bez něj z forku. HAIFA nikdy nepushuje do `main` knihovny a PR nemerguje ani neschvaluje; merguje správce knihovny. Po mergi `library pull` lokální commity rebasuje na remote. Nahrazuje dřívější přímý push zápisu do větve knihovny.

## Doporučené nastavení repa knihovny

Na `main` ruleset: povinný pull request se schválením správce (CODEOWNERS), zákaz mazání a force push, bez bypassu. Podrobnosti jsou v příručce, kapitola Knihovna.
