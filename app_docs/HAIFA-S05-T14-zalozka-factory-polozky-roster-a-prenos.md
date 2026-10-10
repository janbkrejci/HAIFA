# Správa položek na Factory

Na záložce Factory jsou tabulky Agenti, Workflow, Skilly a Rozšíření pi. Stav
položky vyjadřuje její vztah ke knihovně; tooltip nabízí český popis. Purpose a
prompty agenta vlastní knihovna. Harness, model a thinking změň tlačítkem Nastavit
v řádku, potom načti náhled a potvrď Provést. Prázdný model nebo thinking
znamená beze změny; nevyplněné volitelné vazby se neposílají do akce set.

Přidat z knihovny… nabízí položku podle typu. Agent a workflow mohou mít vlastní
slot. Skill a rozšíření mohou být navázány na agenta. Náhled obsahuje uzávěr
závislostí, včetně zachovaných položek, a diff zapisovaných souborů.

Akce Diff porovnává kopii s manifestem a aktuální knihovnou. Aktualizovat obnovuje
položku z knihovny a umožní vybrat převzetí nebo sloučení konfliktních souborů.
Exportovat vytvoří další verzi; agent nebo workflow lze exportovat jako novou
položku zadáním názvu. Vrátit nabízí verzi manifestu nebo aktuální knihovnu.
Odebrat může být blokováno používajícími agenty, workflow nebo tasky backlogu.

Kopírovat do… vybírá jedno registrované repo. U změněné položky potvrď nejprve
export do knihovny a potom samostatný plán přidání do cílového repa. Ukončení po
exportu ponechá exportovanou verzi v knihovně. Skill či rozšíření lze při přidání
navázat na agenta cílového repa.

Zápisy směřují do base nebo do PR. Před každým zápisem se zobrazí plán a vyžaduje
potvrzení. Změna voleb zneplatní náhled. Blokátory vypisují důvod a doporučenou
opravu; například obsazený slot vyžaduje jiné jméno a probíhající běh dokončení.
Po PR počkej na merge a použij Dorovnat base. Necommitované změny konfigurace
nejprve commitni přes existující akci Commitnout konfiguraci.

Ověření: cílený Vitest pro FactoryItems a FactoryView, backendový pytest
`tests/web/test_web_factory_items.py`, prohlížečový pytest
`tests/e2e/test_factory_items_browser.py`, frontendový build, typecheck a lint.
Prohlížečový scénář přidá skill lint builderovi přes náhled a potvrzení, ověří
nový commit, čisté repo a stav synced. Používá lokální repo a tripwire na modely.
