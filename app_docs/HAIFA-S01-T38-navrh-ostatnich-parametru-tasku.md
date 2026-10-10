# Návrh parametrů tasku agentem

Při založení nebo úpravě tasku vyplň titulek a zadání. V části „Provider a model
pro návrh“ vyber nakonfigurovaného agenta. Nabídka uvádí jeho providera i model;
naposledy použitá volba se příště nabídne pro stejné repo ve stejném prohlížeči.

Klikni na „Navrhnout parametry tasku“. Agent vrátí návrh zadání, titulku, writes,
závislostí, souvisejících tasků, workflow a dalších zděditelných parametrů spolu
s vysvětlením. Návrh lze spouštět opakovaně nad aktuálním obsahem formuláře.

„Použít návrh do formuláře“ přenese hodnoty k další úpravě. Další parametry jsou
v rozbalovací části; prázdná hodnota znamená dědění. Test je seznam argumentů
příkazu, jeden argument na řádek. Task uložíš tlačítkem „Založit“ nebo „Uložit“.
Historie běhů se při změně zadání zachová. Během aktivního běhu, review nebo po
ukončení tasku není návrh dostupný.

U každého návrhu vidíš vykázanou cenu v USD a tokeny. Cena pochází z údajů providera;
pokud cenu neposkytuje, dashboard to výslovně oznámí. Předplatné a jeho skutečná
fakturace se mohou od vykázané hodnoty lišit. Záznamy jednotlivých návrhů zůstávají
viditelné po dobu otevření formuláře. Samotný náhled task ani konfiguraci neukládá.

Pro nově navržené workflow s vlastním YAML použij samostatné „Navrhnout workflow“.
Návrh parametrů vybírá z existujících validních workflow.
