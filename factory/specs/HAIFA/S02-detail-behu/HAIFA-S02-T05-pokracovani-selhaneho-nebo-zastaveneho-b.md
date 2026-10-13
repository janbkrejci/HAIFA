# HAIFA-S02-T05: Pokračování selhaného nebo zastaveného běhu

## Cíl

Selhaný, zastavený nebo přerušený (`aborted`) běh jde dokončit jako další pokus téhož
běhu: stejný `run_id`, worktree, větev a trace session. Hotové fáze se neopakují a agenti
navážou na své sessions.

## Rozhraní

- CLI: `factory task retry ID [--run RUN_ID] [--note TEXT] [--from FÁZE] [--json]`.
  Bez `--run` se pokračuje v nejnovějším běhu tasku.
- API: `POST /api/runs/{run_id}/retry` s tělem `{note?, from?}`, odpověď 202
  `{task_id, action: "retry", run, pending}`. Proces spouští launcher dashboardu
  (`start_retry`), běh je převzatý, když má řádek vyšší `attempt`.
- Dashboard: tlačítko „Navázat“ s polem pro poznámku v detailu běhu a u nejnovějšího běhu
  v detailu tasku. Detail běhu ukazuje číslo pokusu a u každého navázání fázi, počet
  převzatých fází, rebase a poznámku.

## Deník fází

`run_workflow(journal=...)` zapisuje do `<session>/workflow_journal.json` každou dokončenou
fázi: jméno fáze, klíč kroku, top-level krok, envelope (u testu i report, u commitu výsledek).
Rozběhnutá fáze je `current`. Pokračování deník přehraje: interpreter prochází workflow
normálně, a dokud další fáze odpovídá dalšímu záznamu, vezme uložený výsledek místo volání
agenta nebo kódu. Podmínky, smyčky a vstupy tak vidí totéž co první pokus. U první
nepřehrané fáze se deník zkrátí a běh pokračuje naživo.
Fáze se zaznamená jako `current` už před čekáním na phase gate, takže zastavení
pozastaveného běhu naváže na čekající fázi bez opakování dokončených testů.

## Odkud se pokračuje

1. Selhaná nebo zastavená fáze: `current` z deníku, přehrají se všechny hotové fáze.
2. `accept not met`: top-level krok, jehož výsledek nesplnil `accept` (např. smyčka review),
   začne znovu celý, takže review dostane nové kolo.
3. `--from FÁZE`: jméno fáze (`review_2`) nebo krok (`review`). Neznámá fáze je `unknown_phase`.
4. Krok selhané fáze v aktuálním workflow chybí: workflow začne od první fáze a vypíše se
   varování.
5. Po rebase se přehrávání zastaví u posledního `test` před prvním review kódu, takže testy
   proběhnou znovu na nové base dřív, než review cokoli schválí.

## Pořadí kroků

1. Odmítnutí bez změny: běh není `failed|stopped|aborted` nebo je to resolve běh
   (`run_not_retryable`), PR tasku je mergnutý nebo task je v base `done` (`task_done`),
   běží jiný běh tasku (`already_running`), větev běhu zmizela (`unknown_branch`).
2. Base se stáhne z remote jako `factory config pull` (`pull_base`). Když nejde posunout,
   pokračování skončí s chybou (`base_diverged`, `dirty_base`, `run_in_progress`, ...).
3. Konfigurace, backlog a workflow se čtou z aktuální base, roster i s přepisem z poznámky
   původního běhu.
4. `TaskRunStore.reclaim` vrátí řádek do `running` (stejný zámek tasku jako `claim`) a připíše
   položku do `task_runs.retries`.
5. Když base není předkem větve, necommitnutá práce se commitne jako WIP a větev se rebasuje
   (`rebase_onto`). Konflikt řeší workflow `resolve` ve stejném worktree s
   `ConflictWriteGuard`, jako `factory task resolve`. Při selhání se větev i necommitnutá
   práce vrátí do původního stavu, běh je `failed` a workflow se nespustí. Po úspěchu se
   `base_sha` běhu nastaví na novou base.
6. Workflow běží s deníkem, baseline je baseline prvního pokusu (po rebase nová base).
   Úspěšný běh publikuje PR jako `task run`.
   Po rebase dříve pushnuté větve se použije `force-with-lease` vůči známému
   remote-tracking tipu, pokud je předkem původního tipu větve běhu.

## Kontext agentů

Session dir běhu je stejný, takže `agent_map.json` vrátí agentovi jeho session id, když se
model nezměnil (`claude --resume`, `codex exec resume`, pi `--session-id`). Prompt dostane
sekci `## Continuation` (číslo pokusu, fáze, odkud se pokračuje, souhrny hotových fází,
cesta ke `context_handoff/`, informace o rebase) a poznámku operátora jako `## Retry note`.
Session id se uloží před voláním harnessu i u prvního neúspěšného pokusu. Pokud harness
výslovně oznámí chybějící session, naváže nová session s týmž promptem; jiné chyby se
nezakrývají. Před přehráním deníku se celý jeho předchozí obsah uloží do
`context_handoff/retry_attempt_<pokus>.json` pro agenta bez dostupné historie.

## Trace

Fáze dalšího pokusu pokračují v sekvenci téže session, tokeny a náklady se sčítají.
Fáze `request` pokusu loguje `retry`, `resume_from`, `replayed_phases`, `rebased_onto` a
`retry_note`.
