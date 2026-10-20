# Schváleno, čeká na CI

Dashboard rozlišuje ručně schválený PR čekající na CI od PR čekajícího na review a od automatického merge. Stav má vlastní chip, barvu v grafu závislostí, sekci Přehledu a Review a počet v přepínači repozitářů. Sloupec kanbanu a filtr stavu se zobrazí pouze s taskem v tomto stavu.

Schválené PR nezvyšuje urgenci repozitáře jako práce čekající na uživatele. Přehled zachovává jeho zařazení do projektu. Review ukazuje čas schválení, dovoluje schválení opakovat a schválené PR přeskakuje při nabídce dalšího PR. Task během review a čekání na merge nelze upravit ani znovu spustit.

Sdílené ochrany považují approved za otevřené PR: brání spuštění i z již otevřeného RunDialog a dovolují stacked start závislého tasku. Stejně se vyhodnocují přímé závislosti i nedokončené tasky kontejneru.

Starší odpovědi API bez seznamu schválených PR se zobrazí s prázdným seznamem. Přechody po merge nebo neúspěšném CI řídí existující backend; tato změna backend neupravuje.

Ověření: cílené frontendové testy Backlogu, Přehledu, Review a přepínače repozitářů; testy příručky a jejího souladu s UI; produkční sestavení statického frontendu. Živý hosting s CI nebyl při implementaci použit.
