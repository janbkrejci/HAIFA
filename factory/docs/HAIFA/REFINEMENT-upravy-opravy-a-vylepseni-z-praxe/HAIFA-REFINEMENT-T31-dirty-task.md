# HAIFA-REFINEMENT-T31: Varování při opuštění rozepsaného tasku

Formulář tasku (nový i úprava) hlídá neuložené změny. Když je rozepsaný a uživatel
odchází, dashboard se zeptá „Zahodit neuložené změny?“ (Zahodit změny / Zůstat).

- Odchod v rámci dashboardu: jakákoli změna hashe – Příručka, jiná obrazovka, jiný task,
  přepnutí repozitáře, tlačítko Zpět. URL se vrátí na otevřenou obrazovku a navigace
  proběhne až po potvrzení.
- Obnovení nebo zavření stránky a odkaz mimo dashboard: nativní dotaz prohlížeče
  (`beforeunload`).
- Tlačítko Zrušit ve formuláři se s rozepsanými změnami také nejdřív zeptá.
- Po odeslání formuláře se už neptá; když zápis selže, formulář je zase „dirty“.

Implementace: `aifactory/web/src/lib/leaveGuard.ts` (registr dirty kontrol, jediný
`ConfirmDialog` v `App.vue`), router volá `allowHashChange()` před každou změnou
obrazovky. Jiný formulář se připojí voláním `useUnsavedGuard(() => dirty)`.
