---
id: HAIFA-REFINEMENT-T54
title: "Přehled: dlaždice repa po projektech (přepínač, výchozí zapnuto)"
status: todo
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T53]
writes: [aifactory/web/src/components/overview/, aifactory/web/src/lib/overview.ts, aifactory/web/src/lib/overview.test.ts, aifactory/web/src/lib/api.ts, aifactory/web/src/views/OverviewView.vue, aifactory/web/src/views/OverviewView.test.ts, aifactory/web/src/test/overviewFixtures.ts, aifactory/src/aifactory/web/static/]
---

## Zadání
## Zadání
Když má repo víc projektů, ukáže dlaždice repa na Přehledu buď souhrnný stav (jako dnes), nebo stav po projektech: u každého projektu jeho běhy, PR a selhání a chipy stavů tasků. O tom rozhoduje přepínač „Po projektech“, který je ve výchozím stavu zapnutý.

## Současný stav
- `aifactory/web/src/views/OverviewView.vue` vykresluje karty (`components/overview/RepoCard.vue`) a klidná repa (řádek `calm` přímo ve view). Chipy stavů tasků a sloty ukazuje `components/overview/RepoControls.vue` z `taskSummary()` v `lib/overview.ts`.
- API (task T53) vrací u položek `running`/`review`/`automerge`/`failed`/`merged_outside`/`auto_actions` pole `project` a u repa `projects: [{id, title, tasks}]`.
- Přepínače zapamatované v prohlížeči jsou vzorem v `lib/backlog.ts` (`HIDE_DONE_KEY`, localStorage). Přepínač jako `input type="checkbox" class="switch" role="switch"` je vzorem v `components/backlog/RunDialog.vue`.

## Požadavek
- Typy v `lib/api.ts`: `project?: string | null` u položek a `projects?: OverviewProject[]` u `OverviewRepo` (starší server je nemá, `fetchOverview` doplní `[]`).
- V hlavičce Přehledu je přepínač „Po projektech“. Je ve výchozím stavu zapnutý a prohlížeč si volbu pamatuje (localStorage, vlastní klíč). Ukazuje se jen tehdy, když má aspoň jedno repo víc než jeden projekt.
- Při zapnutém přepínači a repu s víc než jedním projektem ukáže karta repa (i řádek klidného repa) sekce po projektech. Sekce má název projektu s id v tooltipu, chipy stavů tasků projektu (stejné barvy přes `stateClass`/`.state-chip`) a seznamy Běží, Čeká na review, Čeká na automerge PR a Selhalo jen s položkami projektu. Položky s `project: null` jdou do sekce „Bez projektu“, která se ukáže jen tehdy, když nějaké má. Hlavička karty, tlačítka továrny, sloty, problémy konfigurace, sloučené mimo factory a poslední aktivita zůstanou jednou za repo.
- Při vypnutém přepínači nebo repu s nejvýš jedním projektem vypadá karta jako dnes.
- Řazení karet, součty nahoře a filtr se nemění. Čisté pomocné funkce (rozdělení položek po projektech, čtení a zápis přepínače) patří do `lib/overview.ts`.
- Po změně frontendu přegenerovat statický build: `just web-build` do `aifactory/src/aifactory/web/static/`.

## Mimo rozsah
Backend API, Backlog a ostatní obrazovky.

Hotovo znamená:
- Unit testy v `lib/overview.test.ts` pro rozdělení po projektech (včetně „Bez projektu“) a pro výchozí hodnotu přepínače (zapnuto) a její zapamatování.
- Test komponenty: repo se dvěma projekty ukáže při zapnutém přepínači dvě sekce projektu se správnými řádky a chipy. Po vypnutí ukáže dnešní souhrn. Repo s jedním projektem přepínač nemění.
- `OverviewView.test.ts`: přepínač chybí, když žádné repo nemá víc projektů.
- Stávající testy Přehledu projdou a statický build je aktuální.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
