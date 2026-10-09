---
id: HAIFA-S09-T01
title: Azure ve Windows a skutečný self-approve hlas před merge
status: done
depends_on: [HAIFA-S08-T01]
writes: [aifactory/, app_docs/]
auto_merge: false
---

## Zadání
Zprovoznit existující Azure DevOps provider na Windows a doplnit skutečný schvalovací hlas při factory task approve. Operátor poté ověří živě v samostatném novém repo HAIFA-Azure-Sandbox, organizace https://asolcz.visualstudio.com, projekt NEO_HEF. Agenti/testy žádné živé PR ani politiky nevytvářejí.

Zjištění: Azure CLI MSI je C:/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd. Bare subprocess.run([az,...]) zde vyhodí WinError2; wrapper volá ../python.exe -IBm azure.cli. CLI + azure-devops 1.0.4 + přihlášení fungují, az repos list i az account show uspěly. V review/flow.py a cli.py je TODO(D11): approve žádný hlas do hostingu neodesílá, ApproveResult.reviewed je vždy false.

Acceptance:
- AzCli.run podporuje Windows MSI az.cmd/az.bat bezpečným přímým spuštěním embedded Python azure.cli s argv zachovaným beze ztráty JSON/uvozovek/newlines, bez string-built cmd shell command. Zachovat AIFACTORY_AZ explicitní executable/fake tests a běžné non-Windows chování. Bounded timeout a hidden Windows child pokud praktické; srozumitelné instalační chyby. Pro jiné neznámé shim instalace preferovat explicitní AIFACTORY_AZ/native executor před nebezpečným shell quoting. Přidej významné fake-launch regresní testy.
- Přidej schválení do rozhraní GitProvider kompatibilně se stávajícími local/GitHub providery. Azure odešle az repos pr set-vote --id ID --vote approve s explicitní org/detect false. Pokud hosting nepodporuje/nevytváří review, výsledek musí zůstat poctivě reviewed:false. GitHub vlastní APPROVE vote nelze; zachovej nynější GitHub/local merge chování.
- factory task approve (dashboard používá stejný flow) odešle Azure vote až PO status-done commitu a pushi finálního head, protože branch policy může hlasy resetovat po každém pushi, a PŘED merge. Ověř aktuální head tak, aby se schválení nepřilepilo k jinému headu. reviewed:true jen pro úspěšné skutečné host review. Při chybě hlasování nemergovat, chyba musí být jasná a retry idempotentní; zachovat test/review gates, head SHA guards a stávající recovery/auto-merge chování.
- CLI/API nesmí stále tvrdit no approve review sent, pokud Azure review skutečně odešlo; přizpůsobit poznámku výsledku. Neměň GitHub/global branch policies, nepřidávej bypass policies nebo force merge. Azure politiky se normálně respektují; dokumentace vysvětlí creatorVoteCounts/Allow requestors to approve their own changes a že další požadavky stále platí.
- Backend/providery/approvalflow + relevantní mypy/Ruff testy green, web assets rebuild pouze pokud web upraven. Testy žádná síť/modely/živé hosting operace. Krátký app_docs návod konfigurace Azure, login, Windows a self-approve v samostatném test repo. Neměnit .factory/, CLAUDE.md, product brief, vendor/prototype/adws.

Primární reference: https://learn.microsoft.com/en-us/cli/azure/repos/pr?view=azure-cli-latest#az-repos-pr-set-vote ; https://learn.microsoft.com/en-us/azure/devops/repos/git/branch-policies?view=azure-devops . Přečti aktuální help/schema lokální CLI, pokud potřeba.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-06 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/64 · náklady $0.00
