# Onboarding a převzetí repozitáře

V Přidat repozitář zkontrolujte složku. Pro sssf nebo HAIFA před knihovnou zvolte
Onboarding. Zrušit odebere dočasnou registraci. Totéž lze provést v záložce Factory.

Před zápisem zkontrolujte Knihovnu, Repozitář a Zprávu. Provést otevře potvrzení
commitu knihovny a commitu/push nebo PR repa. Výsledek zobrazí commit knihovny a
commit či odkaz na PR repa. Soubory adws/ zůstanou zachované. Volby jednotlivých
položek jsou dostupné v CLI.

Pokud byl onboarding proveden na remote, použijte Dorovnat base a poté Převzetí.
Čekající onboarding má odkaz na PR (případně Review, když hosting PR neidentifikuje).

Na stroji kolegy přidejte onboardované repo. Factory nabídne panel Převzetí,
nikoli další vytěžení. Chybí-li knihovna, Naklonovat knihovnu použije remote
z manifestu a vyžádá potvrzení. Doplnit knihovnu importuje chybějící položky
podle plánu adopt. Jiná knihovna zobrazí varování. Převzetí repo nemění.

Screenshoty: [onboardované repo](../aifactory/validation/artifacts/HAIFA-S06-T05/onboarded.png)
a [převzetí na druhém stroji](../aifactory/validation/artifacts/HAIFA-S06-T05/adopted.png).
