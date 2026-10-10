# HAIFA-S03-T06 — Schválení: opakovat merge po přechodné chybě GitHubu

## Co se změnilo
`GitHubProvider.merge` (`aifactory/src/aifactory/providers/github.py`) po chybě `gh pr merge`
zopakuje merge, pokud GitHub odpověděl přechodnou chybou. Za přechodnou se považuje chyba,
jejíž text (bez ohledu na velikost písmen) obsahuje některý z markerů v `TRANSIENT_MERGE_ERRORS`:

- „base branch was modified“
- „head branch was modified“
- „try the merge again“

Typicky jde o `GraphQL: Base branch was modified. Review and try the merge again. (mergePullRequest)`,
který GitHub občas vrátí hned po pushi commitu `status: done`.

## Jak opakování funguje
- Počet pokusů a pauza jsou stejné jako u mergeability `unknown`: `attempts` (výchozí 5) a
  `delay` (výchozí 2 s). Nové parametry nepřibyly.
- Po každé chybě merge se provider nejdřív zeptá na stav PR:
  - `MERGED` → merge přece jen proběhl a vrátí se merge commit,
  - otevřený PR s konfliktem → `conflict` (konflikt má přednost, neopakuje se),
  - `CLOSED` → `merge_failed`.
- Teprve potom se přechodná chyba po pauze zopakuje. Po vyčerpání pokusů skončí
  `merge_failed` se zprávou „… (gave up after N attempts)“.
- Nepřechodná chyba (např. posunutá hlava PR) končí `merge_failed` hned, bez opakování.

## Opakovaný `factory task approve`
Když approve přesto skončí `merge_failed`, další `factory task approve` nepřidá druhý commit
`status: done` (úkol už je `done` a v `## Běhy` je řádek PR) a PR sloučí s
`--match-head-commit` na stejné hlavě větve.

## Testy
- `aifactory/tests/providers/test_providers_github.py`: první merge vrátí „Base branch was
  modified“ a druhý projde; všechny pokusy selžou → `merge_failed`; přechodná chyba s
  konfliktem → `conflict`; chyba, ale PR je sloučený → merge SHA; nepřechodná chyba se neopakuje.
- `aifactory/tests/review/test_approve_merge_retry.py`: approve selže `merge_failed`, druhý
  approve PR sloučí bez druhého commitu `status done` a bez nového pushe.
