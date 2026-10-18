# E2E: Azure repo s povinným schválením, auto approve, auto-continue a úklid

Operátor spustí jedním příkazem:

```
just validate-azure-e2e
```

Scénář (`aifactory/validation/azure_e2e.py`) založí v `asolcz.visualstudio.com/NEO_HEF`
dočasné repo `HAIFA-E2E-<datum>-<čas>-<hex>`. Na jeho `main` nastaví politiku „minimálně
1 schvalovatel, autor smí schválit vlastní změny“ a ověří, že přímý push je odmítnutý.
Potom repo projde celou HAIFA bez člověka:

- přidání do HAIFA (`add_repo`, tedy `POST /api/repos`) s `base_changes: pr` a
  `base_pr_merge: auto` přes PR `factory-init/<n>`,
- backlog přes `factory backlog commit` jako PR `factory-backlog/<n>`,
- řetěz dvou závislých tasků `factory task run --auto` s `auto_continue` a `auto_merge`
  přes workflow `build-review` nad falešným harnessem (žádný model se nevolá).

Každý PR se zpětně přečte z Azure: stav `completed`, hlas autora 10 (approve), žádný
`bypassPolicy`, SHA merge commitu. Na konci se porovná lokální `main` s remote a stav
backlogu (`status: done`, PR pod `## Běhy`, `task_prs` merged).

Úklid ve `finally` (i po chybě) odregistruje repo z dashboardu, smaže politiku, smaže repo
a vysype ho z koše projektu, smaže lokální klon a nakonec ověří, že repo ani politika
nezůstaly. Mažou se jen objekty, které běh sám vytvořil (podle id), a jméno musí začínat
`HAIFA-E2E-`. Bez `az`, rozšíření `azure-devops` nebo přihlášení skončí scénář kódem 2
dřív, než na Azure cokoli změní. Do CI nepatří, unit testy (`tests/validation/
test_validation_azure_e2e.py`) používají falešné `az`.

Výsledek se zapíše do `aifactory/validation/results/<datum>/azure-e2e-<čas>/azure-e2e.json`
(kroky s ok/selháním, URL PR, hlasy, SHA, úklid, volání `az` a `factory`). Podrobnosti
jsou v `aifactory/validation/README.md`, oddíl „Azure E2E s povinným schválením“.

## Ověřeno 18. 10. 2026

Běh `azure-e2e-205746` prošel všemi 24 kroky a úklid byl úspěšný. Repo
`HAIFA-E2E-20261018-205746-238e` mělo PR init, backlog a oba tasky (30379–30382).
Všechny factory schválila vlastním hlasem a Azure je dokončil přes politiku bez bypassu.

## Opravy v HAIFA

- Výsledek auto-merge (`auto_merge` v JSON `task run`) nově obsahuje `reviewed`:
  `true`, když hosting přijal vlastní approve hlas factory. Dřív se to z výstupu řetězu
  nedalo poznat.
- `factory backlog commit --json` nově vrací varování (např. že PR zůstal otevřený,
  protože merge selhal). Dřív je zahazoval a `merged: false` nemělo vysvětlení.
