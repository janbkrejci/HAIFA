# Agent ohlásí chybějící writes strukturovaně (HAIFA-REFINEMENT-T63)

Když agent pozná, že úkol nejde dokončit bez změny cesty mimo `writes` tasku, neohlásí
to už blokujícím follow-upem, ale strukturovaně v envelope. Operátor cesty povolí jedním
příkazem nebo tlačítkem, stejně jako po `writes_violation`.

## Envelope

Každý výstup agenta má pole `needs_writes: [{path, reason}]`. Agent, který bez těch cest
nemůže pokračovat, vrátí `status: fail`, `fail_kind: needs_writes` a vyplněné
`needs_writes`. `fail_kind: needs_writes` bez cesty je neplatný envelope (agent dostane
opravu jako u jiné chyby schématu).

## Druh selhání `writes_needed`

`AgentReportedFail` z takového envelope udělá druh `writes_needed`. `failure_detail` má
`agent`, `summary`, `fail_kind`, `paths` (normalizované cesty, bez `./`, s `/`) a
`needs_writes` (cesty s důvody). Běh nezakládá follow-upy ani `depends_on`.
`factory task runs` druh ukazuje jako ostatní, karta selhání na dashboardu ukazuje cesty
s důvody a tlačítko „Povolit tyto cesty a pokračovat“.

## Povolení cest

`plan_allow_writes` a `allow_writes` (`run/allow_writes.py`) přijímají `writes_violation`
i `writes_needed` a třídí cesty stejně (`protected`, `backlog`, `main_checkout`,
`already_allowed`). `factory task retry --allow-writes` i
`POST /api/runs/{id}/allow-writes` po commitu backlogu do base (s kontrolou
`writes_not_committed`) pokračují od selhané fáze. `## Retry note` obsahuje povolené
cesty, odmítnuté cesty s důvodem a poznámku operátora.

## Ci-fix

Ci-fix běh, který skončí `writes_needed`, zastaví schválení s kódem `writes_needed`;
`auto_merge_error` jmenuje běh, cesty s důvody a příkaz `factory task approve ID
--allow-writes`. `task retry --allow-writes` ci-fix běh odmítne (`run_not_retryable`)
s odkazem na approve. `factory task approve --allow-writes`:

1. povolí cesty nejnovějšího ci-fix běhu tasku v base (stejné třídění a kontroly),
2. sloučí base do větve PR; konflikty v souborech backlogu (dřívější commit
   `status: done` proti novým `writes`) převezmou verzi z base, konflikt v jiném souboru
   merge zruší s kódem `conflict`,
3. schválí PR znovu: nový commit `status: done`, čekání na CI a nové ci-fix běhy už
   s rozšířenými `writes`.

Na dashboardu stejné tlačítko u ci-fix běhu („Povolit tyto cesty a schválit znovu“)
spustí schválení znovu v samostatném procesu. Ruční `approved_at` se při schválení
nastavuje a po neúspěchu maže jako dřív.

## Prompty

Builder, tester a test-reviewer v semínku mají pravidlo: cesta, kterou potřebuje tento
task, jde do `needs_writes`, ne do `follow_ups`. Test-reviewer, který vyžaduje test mimo
`writes`, ho uvede v `blocking` s přesnou cestou. Pokyn ci-fix běhu (`review/ci.py`) říká
totéž.

## Ověření

```sh
cd aifactory
uv run pytest tests/run/test_writes_needed.py tests/run/test_allow_writes.py tests/review/test_ci_gate.py tests/test_failure.py tests/test_skill.py -n0
cd web && bun run test src/components/runs/FailureCard.test.ts
```
