# Zrušení tasku

V detailu tasku na obrazovce Backlog je tlačítko **Zrušit**. Je vidět jen u tasku, který
ještě nezačal (Bez workflow, Připraveno, Blokováno, i odložený). Po potvrzení dostane task
status `cancelled`, v kanbanu se přesune do sloupce Zrušeno a už se nespouští.

- Zrušený task jde vrátit úpravou statusu na „K řešení“ ve formuláři Upravit
  nebo `factory task edit <id> --status todo`.
- Sloupec Zrušeno skrývá přepínač „Skrýt hotové“.
- Z CLI totéž: `factory task edit <id> --status cancelled`.
