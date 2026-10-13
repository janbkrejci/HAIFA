# HAIFA-S02-T05: Pokračování selhaného nebo zastaveného běhu

## Co se změnilo

Selhaný, zastavený nebo přerušený běh jde dokončit příkazem `factory task retry ID`
nebo tlačítkem „Navázat“ v detailu běhu a tasku. Pokračování je další pokus téhož běhu:
stejný `run_id`, worktree, větev i trace. Tokeny a náklady se sčítají.

```
factory task retry HAIFA-S02-T05 --note "Chybějící testy jsou mimo rozsah." --json
factory task retry HAIFA-S02-T05 --run d4f262d7 --from review
```

## Chování

- Hotové fáze se neopakují. Jejich výsledky se přehrají z deníku fází běhu
  (`.factory/data/sessions/<run>/workflow_journal.json`).
- Běh pokračuje od fáze, která selhala nebo byla zastavená. Po `accept not met` začne
  znovu krok, jehož výsledek `accept` nesplnil (review dostane nové kolo). `--from`
  určí fázi ručně.
- Agenti navážou na své sessions, pokud se jim nezměnil model. Prompt navíc obsahuje přehled
  hotových fází, cestu ke `context_handoff/` a poznámku operátora.
  Session id se ukládá už před spuštěním agenta, takže zůstane i po zastavené první fázi.
  Pokud harness ohlásí nenalezenou session, agent dostane nový kontext se stejným předáním;
  kompletní výstupy minulého pokusu jsou v `context_handoff/retry_attempt_<pokus>.json`.
- Před pokračováním se base stáhne z remote. Když se base posunula, větev se rebasuje;
  konflikt řeší stejný postup jako `factory task resolve`. Když to selže, větev zůstane,
  jak byla. Po rebase proběhne `test` znovu před review.
  Dříve pushnutá větev se po rebase publikuje přes `force-with-lease` vůči známému
  předchozímu tipu, který je předkem původní větve běhu.
- Konfigurace, backlog a workflow se čtou z aktuální base. Chybí-li krok selhané fáze ve
  workflow, začne se od první fáze s varováním.
- Odmítnuto: task s mergnutým PR nebo `done` (`task_done`), běžící task (`already_running`),
  úspěšný nebo resolve běh (`run_not_retryable`).

## Dashboard

Detail běhu ukazuje číslo pokusu a u každého navázání fázi, počet převzatých fází, rebase a
poznámku. Tlačítko „Navázat“ je u selhaného, zastaveného nebo přerušeného běhu v detailu
běhu a u nejnovějšího takového běhu v detailu tasku.

## Ověření

`tests/run/test_task_retry.py` s falešnými harnessy a skutečným gitem pokrývá pokračování
po neprošlém review, po zastavení, s posunutou base bez konfliktu i s konfliktem, selhaný
resolve, který vrátí větev, a odmítnutí u mergnutého a běžícího tasku.
Pokrývá také odmítnutí rozcházející se base a další pokus po selhaném resolve,
navázání sessions pro Claude, Codex i pi, pokračování z explicitní fáze a odmítnutí
tasku schváleného v backlogu bez mergnutého PR. Zastavení na hranici fází uchová
čekající fázi v deníku, takže při pokračování neopakuje dokončené testy.
Rebase a publikace jsou ověřené také pro dříve pushnutou větev běhu.
`tests/engine/test_envelope_retry.py` ověřuje sessions po selhání, náhradní session
a součet tokenů a nákladů napříč pokusy. Testovací příkazy používají Python, aby fungovaly
i na Windows bez unixových `true` a `echo`.
`tests/web/test_web_runs.py` pokrývá API, `RunDetail.test.ts` a `TaskDetail.test.ts`
tlačítko a zobrazení pokusů.

`tests/web/test_web_launcher.py` ověřuje argumenty `--run`, `--note`, `--from`,
převzetí až po zvýšení pokusu stejného běhu, čekání na převzetí a zachování předchozího
pokusu při chybě procesu. `tests/e2e/test_retry_browser.py` přes skutečný dashboard
a procesy s falešným harnesssem pokračuje po odmítnutém review z detailu běhu i tasku:
odesílá poznámku, kontroluje stejné run_id, větev, worktree a session reviewera, zvýšení
pokusu a historii v detailu. Dokončený planner se neopakuje.
Integrační test v `tests/run/test_task_retry.py` mění na lokálním remote konfiguraci,
backlog tasku i workflow: retry stáhne base, použije nové zadání, harness, model a cesty,
varuje před odstraněnou čekající fází review a dokončí nové workflow od první fáze.
