# HAIFA-S05-T14: Položky repa na Factory

Factory zobrazuje čtyři tabulky položek se serverem vypočtenými stavy `local`,
`missing`, `synced`, `unknown`, `outdated`, `modified` a `diverged`. Roster ukazuje
purpose a vlastnictví promptů knihovnou, harness, model, thinking, skilly, rozšíření
pi a writes. Workflow ukazuje počet tasků s efektivním workflow v backlogu base.

Harness, model a thinking se upravují přímo v řádku a zapisují akcí `set`. Přidání
z knihovny nabízí typ, položku, slot a vazbu skillu nebo rozšíření na agenta.
Náhled ukazuje přidávané i zachované závislosti a souborové diffy.

Každá operace používá `/factory/plan`, poté samostatné potvrzení a `/factory/apply`
s digestem. Volby mají whitelist; UI neposílá vrácené soubory ani jejich obsah.
Změna voleb ruší platnost náhledu. Akce update podporuje volby převzetí/sloučení
konfliktů přes existující UpdateChoices. Diff je samostatná čtecí operace proti
manifestu a HEAD knihovny. Blokátor zobrazí důvod a opravu a zakáže Provést.

Kopírování synchronizované položky připraví add v jednom cílovém registrovaném
repu. Lokální nebo změněná položka nejprve vyžaduje potvrzený export do knihovny
na base zdrojového repa a poté nový náhled a nové potvrzení add v cílovém repu.
Cílové vazby se vybírají z rosteru cílového repa. Nejde o hromadnou operaci.

Čtecí endpointy `/factory/roster` a `/factory/item-diff?type=…&name=…` používají
existující CLI jádro. API položek a stavový algoritmus zůstávají kompatibilní.
Editory promptů a workflow, onboarding a distribuce do více rep zůstávají mimo rozsah.
