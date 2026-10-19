# Follow-up úlohy bez nesledovaných souborů v hlavním checkoutu

Follow-up úlohy z běhu se připravují v dočasné kopii backlogu. Factory publikuje
pouze soubory změněné při jejich založení a propojení závislostí; commit sestaví
nad base pomocí existujícího mechanismu publikování bez checkoutu.

V režimu `base_changes: direct` se commit nejprve pushne a při posunu lokální base
se jeho změny promítnou do checkoutu. V režimu `pr` čekají změny v PR větvi.
Při automatickém merge se do checkoutu promítnou až při posunu lokální base;
pokud jej aktivní běh odloží, následný pull přinese soubory běžným způsobem.
Čekající PR ani neúspěšné publikování nezanechá v hlavním checkoutu nové soubory.
Nesouvisející lokální změny a obsah indexu se do follow-up commitu nepřibírají.

Regresní testy spouštějí běh s follow-up úlohou proti lokálnímu bare remotu pro
`direct`, ruční PR a automatický merge PR. Kontrolují čistý backlog v checkoutu,
úspěšný `git pull --ff-only` a přítomnost nové úlohy po pullu. Samostatně ověřují
odmítnuté publikování a zachování nesouvisejících lokálních i staged změn.
