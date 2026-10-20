# Ručně schválené PR čekající na CI

Ruční `approve_task` uloží `task_prs.approved_at` a vymaže předchozí `auto_merge_error` ještě před přípravou schválení. Při chybě před merge schválení vymaže a zachová důvod v `auto_merge_error`. Úspěšný merge může čas schválení uchovat. Auto-merge čas ručního schválení nezapisuje.

Nejnovější otevřené PR s časem schválení a bez chyby dává tasku board state `approved`. V přehledu je v seznamu `approved`, jehož položky mají stejný tvar jako `review`, a přispívá do `totals.approved`. Nadále zabírá slot `factory.in_review`. Review API vrací `approved: true`, `approved_at` a `awaiting_review: false`; opakované schválení zůstává povolené. Pořadí seznamu je review, approved, automerge, ostatní. Workflow advice stav `approved` nepřijímá.

Nové databáze obsahují nullable TEXT sloupec `approved_at`; TaskRunStore starší databáze migruje při otevření. Read-only snapshot přehledu používá pro chybějící sloupec NULL.

Frontend, statický build a příručka jsou mimo rozsah. Při ukončení procesu může čas schválení zůstat uložený; nové schválení ho obnoví. Watchdog se nepřidává.
