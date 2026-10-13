---
id: HAIFA-REFINEMENT-T14
title: Rychlý stav konfigurace a seznamu rep v dashboardu na Windows
status: todo
depends_on: []
---

## Zadání
Dashboard je na Windows s velkým repem velmi pomalý. Naměřeno na repu s 61 558 soubory v indexu (git 2.55.0.vfs, Windows 11):
- `GET /api/repos` trvá 12–19 s a frontend ho volá při každé změně stránky nebo repa (`App.vue`, `watch([page, repoId], reloadRepos)`),
- `GET /api/overview` trvá 10 s a polluje se každé 2 s (`OVERVIEW_POLL_MS`).

Příčina: `working_tree_changes` v `aifactory/src/aifactory/config/status.py` volá `git diff-index --raw -z --no-renames <sha> -- .factory .claude/skills .agents/skills`. Samotná pathspec `.agents/skills` trvá 5–15 s (čas jde do `unpack_trees`, `nr_unpack_entries:0`), ostatní kolem 0,4 s. Ve stejném repu `git diff-index ... -- ".agents/skills/*"` trvá 0,36 s a `git ls-files -z -m -d -- .agents/skills` 0,29 s. `/api/repos` (`repo_status` ve `web/repos.py`) stav konfigurace vůbec necachuje, overview ho drží jen 15 s (`CONFIG_TTL`).

Zadání:
1. Zrychlit `working_tree_changes` tak, aby se nedotýkala pomalé cesty gitu (např. pathspec `<dir>/*` místo adresáře, nebo `ls-files -m -d` + `diff-index --cached`). Výsledek musí zůstat stejný: modified/added/deleted/untracked, žádný zápis indexu ani `index.lock` (viz docstring), stejné chování pro soubory se zastaralými stat daty.
2. `GET /api/repos` použije pro stav repa krátkodobou cache (jako overview), aby navigace mezi stránkami nespouštěla git znovu. Změna konfigurace přes dashboard nebo `factory config` cache zneplatní, aby UI neukazovalo starý stav.

Hotovo znamená:
- Testy pokrývají shodu nového a původního výsledku `working_tree_changes` (změněný, přidaný, smazaný, nesledovaný soubor, zastaralá stat data, soubor mimo pathspecs) a cache `/api/repos` včetně zneplatnění.
- Na repu s desítkami tisíc souborů neroste počet volání gitu na jednu navigaci; v popisu PR je měření před a po.
- `just check` a `just e2e` projdou (kromě testů, které na Windows padají už na base).

Mimo rozsah: výjimky Defenderu, změny intervalů pollingu ve frontendu, ostatní git volání v overview.

Tvrdá omezení: žádný zápis do indexu cílového repa, chování na POSIXu se nezhorší.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
