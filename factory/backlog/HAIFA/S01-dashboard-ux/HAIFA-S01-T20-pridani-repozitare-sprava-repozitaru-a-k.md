---
id: HAIFA-S01-T20
title: "Přidání repozitáře, správa repozitářů a kontrola factory v UI"
status: done
workflow: simple-sdlc
depends_on: [HAIFA-S01-T15, HAIFA-S01-T17, HAIFA-S01-T19, HAIFA-S06-T02, HAIFA-S01-T01, HAIFA-S01-T02, HAIFA-S01-T03]
---

## Zadání
Doplň do dashboardu přidání repozitáře výběrem složky, stránku Repozitáře s odebráním a portem dashboardu a záložku Factory, která ukáže výsledek `factory check` a stav onboardingu repa.

Where: `aifactory/src/aifactory/cli.py` (`factory obs --repo`), `aifactory/web/src/` (`App.vue`, `lib/router.ts`, `lib/api.ts`, `components/EmptyScreen.vue`, `views/`, `components/` a testy), `aifactory/tests/e2e/`, build v `aifactory/src/aifactory/web/static/`.

Done means:
- Krok Složka na `#/repos/add`: pole cesty předvyplněné `~/` s našeptáváním podsložek z `/api/fs/dirs` (štítky git a factory), Procházet… (prohlížeč složek od domova) a Vybrat ve Finderu…, jen když `/api/fs/pick` hlásí dostupnost. Zkontrolovat zavolá inspect.
- Karta repa ukáže kořen repa (u podsložky „Použije se kořen repozitáře …“), větev, remote, stav factory z inspect (`none`, `working_tree`, `sssf`, `pre_library`, `onboarded`) a trace DB. Odmítnutí má důvod a žádné tlačítko Přidat: složka neexistuje, není git („HAIFA nespouští git init“), propojený worktree (s nabídkou hlavního checkoutu), worktree běhu, holé repo, repo bez commitu, sdílená trace DB. Registrované repo nabídne Otevřít.
- `pre_library`, `working_tree` a `onboarded`: Přidat zaregistruje repo a otevře `#/r/<id>/factory`, kde se kontrola spustí sama. U `onboarded` karta ukáže, kdo, kdy a z čeho repo onboardoval. `none`: karta ukáže `factory init --dry-run` a `factory init --commit` a repo nepřidá. `sssf`: karta ukáže, že konfigurace sssf se vytěží jednou příkazem `factory onboard --repo <cesta> --dry-run`, a repo nepřidá.
- Záložka Factory: formát a `written_by` z manifestu (nebo „bez manifestu“), verze balíčku, nálezy ve skupinách „Repozitář: opravit a commitnout“ a „Tento počítač: opravit lokálně“ a Znovu zkontrolovat. `factory obs --repo` otevře záložku Factory místo Backlogu, když repo není ve stavu `ok`.
- `#/repos`: tabulka repozitářů (název, cesta, stav, přidáno), Otevřít a Odebrat z dashboardu s potvrzením ve vlastním modálu: „Odebrat <name> z dashboardu? Ve složce <path> se nic nezmění: .factory/, backlog, trace DB, worktree a větve zůstanou. Běžící běhy doběhnou.“ Odebrání otevřeného repa vede na přehled. Prázdný stav nabídne Přidat repozitář a karta s chybějící složkou Odebrat.
- `#/repos` nese i port dashboardu (platí po restartu) a cestu k registru.
- Unit testy (vitest): stavy a chyby průvodce včetně `sssf`, `pre_library` a `onboarded`, našeptávání, viditelnost tlačítka dialogu, odebrání s modálem, port a záložka Factory. Prohlížečový test přidá repo s factory napsáním cesty a odebere ho.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: instalace, aktualizace a commit konfigurace z UI (M14), onboarding a převzetí v UI (O5), přejmenování repa, Windows.

Pevná omezení:
- Přidání ani odebrání repa nic nezapíše do repa.
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-07 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/78 · náklady $7.92
