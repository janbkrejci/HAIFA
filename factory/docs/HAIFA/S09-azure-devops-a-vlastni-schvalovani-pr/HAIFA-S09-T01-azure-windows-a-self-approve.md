# Azure ve Windows a vlastní schválení PR

Živé ověření provádí operátor po merge pouze v samostatném repozitáři
`HAIFA-Azure-Sandbox`, projekt `NEO_HEF`, organizace
`https://asolcz.visualstudio.com`. Automatické testy používají fake executory
nebo lokální dočasné git repozitáře; nevytvářejí živé PR ani politiky.

## Konfigurace a přihlášení

Nainstalujte Azure CLI MSI, rozšíření a přihlaste se ve svém PowerShellu:

```powershell
az extension add --name azure-devops
az login
az account show
az repos list --org https://asolcz.visualstudio.com --project NEO_HEF --detect false
```

Alternativou přihlášení je `AZURE_DEVOPS_EXT_PAT` s oprávněními pro dané repo;
HAIFA token neukládá do konfigurace. Git push používá vlastní git přihlášení.
V konfiguraci sandboxu nastavte (zachovejte další nastavení projektu):

```yaml
git_provider: azure
remote: origin
base: main
azure:
  organization: https://asolcz.visualstudio.com
  project: NEO_HEF
  repository: HAIFA-Azure-Sandbox
```

MSI typicky poskytuje `C:/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd`.
HAIFA najde wrapper na PATH a pro rozpoznané MSI rozložení spustí přímo
`../python.exe -I -X utf8 -B -m azure.cli` s původním seznamem argumentů.
Rozpoznání podporuje modul `azure/cli/__main__.py` i MSI s pouze `__main__.pyc`.
JSON, uvozovky, čeština a nové řádky neprocházejí cmd shell quotingem.
Volání má limit 120 sekund a skryté Windows okno. Nativní executable lze
určit přes `AIFACTORY_AZ`; tato proměnná má přednost před PATH.
Neznámé `.cmd`/`.bat` shimy nejsou spouštěny: použijte MSI nebo nastavte
`AIFACTORY_AZ` na nativní executor `.exe`, který přijímá stejné argumenty jako az.

## Hlasování a politiky

`factory task approve ID` (stejný flow používá dashboard a auto-merge) nejprve
vytvoří `status: done` commit a pushne finální head. Poté Azure odešle
`az repos pr set-vote --id ID --vote approve` s explicitní organizací a
`--detect false`, teprve pak zkusí merge. Hlas patří přihlášenému Azure uživateli.
To zachová hlas i při politice resetující hlasy po pushi. HAIFA kontroluje SHA
před hlasem, po hlasu a před merge; Azure CLI nemá atomické navázání hlasu či
completion na očekávaný head. Zůstává malé závodní okno při souběžném pushi,
takže během approve nepushujte na stejnou větev. Zjištěná změna SHA zastaví merge.

V branch policy **Require a minimum number of reviewers** dovoluje
**Allow requestors to approve their own changes** (`creatorVoteCounts`) započítat
hlas autora. Bez toho může autor hlasovat, ale jeho hlas nesplní minimum.
Operátor případné nastavení ověří pouze v sandboxu. Další požadavky platí dál:
počet reviewerů, required reviewers a jejich vlastní nastavení, build validation,
komentáře i zákaz schválení posledním pusherem. HAIFA nemění politiky a nepoužívá
bypass ani force merge.

Při chybě hlasování se merge neprovede. Done commit zůstává na větvi a opakované
approve po opravě přístupu či politik nevytvoří duplicitní commit; znovu nastaví
stejný approve hlas. Také odmítnutí merge politikou lze takto opakovat.
JSON CLI/API vrací `reviewed: true` pouze po úspěšném skutečném host hlasu
v tomto volání. GitHub nepovoluje autorův vlastní APPROVE review; GitHub a local
zachovávají dosavadní merge chování s `reviewed: false`. Text CLI výsledek rozlišuje.
Dosavadní test/review gates a SHA guards pro běhy zůstávají v platnosti.

Operátor v novém sandboxu ověří finální SHA a reviewer vote po approve,
reset hlasů při novém pushi a odmítnutí merge při nesplněné další politice.

Reference: [set-vote](https://learn.microsoft.com/en-us/cli/azure/repos/pr?view=azure-cli-latest#az-repos-pr-set-vote)
a [branch policies](https://learn.microsoft.com/en-us/azure/devops/repos/git/branch-policies?view=azure-devops).
Lokální MSI CLI help byl ověřen přes embedded Python bez živých hosting operací.
