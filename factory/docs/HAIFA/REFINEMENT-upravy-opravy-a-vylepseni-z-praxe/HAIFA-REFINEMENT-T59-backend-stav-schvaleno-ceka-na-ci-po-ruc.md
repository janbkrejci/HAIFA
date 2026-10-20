# Stav „Schváleno, čeká na CI“ v backendu

Backend rozlišuje otevřená PR čekající na ruční review (`in review`), ručně schválená PR čekající na CI (`approved`) a PR čekající na automatický merge (`awaiting merge`). Záznam ručního schválení vzniká před přípravou a čekáním na CI. Chyba před merge vymaže schválení a uloží důvod; po úspěchu rozhoduje stav `merged`.

- Backlog API přidává `approved` do stavů a jejich počtů.
- Overview API přidává `approved: []` ke každému repozitáři a počet `totals.approved`. Schválená PR nejsou v `review`, nadále však zabírají slot `factory.in_review`.
- Review API přidává `approved` a `approved_at` do seznamu i detailu. Čekající schválené PR má `awaiting_review: false` a lze ho znovu schválit. Řazení upřednostňuje review, pak approved a automerge.
- Databáze se migruje při otevření TaskRunStore; přehled umí číst i starší databázi bez nového sloupce.

Testy kontrolují čas schválení přímo při čtení CI, jeho vymazání po chybách, nezměněné chování auto-merge, výběr nejnovějšího otevřeného PR, API a kompatibilitu databází, včetně původního schématu bez `merged_by`, `auto_merge_error` a `approved_at`. Opakované otevření databáze zachovává uložený čas schválení. Frontend a statické soubory tato změna neupravuje.
