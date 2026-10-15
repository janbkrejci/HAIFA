# HAIFA-REFINEMENT-T26: Lepší popisy pull requestů a tvrdé zacházení s nedodělky

## Rozhodnutí: co je v kódu, co v promptech, co ve workflows

| Co | Kde | Proč |
|---|---|---|
| Agent hlásí shrnutí PR, novou práci a blokaci | Pole obálky `EnvelopeBase` (`engine/data_types.py`): `pr_summary`, `follow_ups`, `blocked_by` | Typovaná obálka je jediný kanál od agenta k factory. Na společném základu ji může vyplnit každá role (build, fix, revise, review, plan, document, test) bez zvláštního napojení. Všechna pole mají výchozí hodnotu, takže staré journaly i obálky platí dál. |
| Pravidla „žádné skryté nedodělky, novou práci a blokaci ohlas, napiš shrnutí PR“ | Prompty seed agentů (`seed/agents/{builder,planner,reviewer,documenter,tester}/`) | Jen agent ví, kdy práce přesahuje task. Chování agenta určuje jeho prompt. Verze seed položek jsou hashe obsahu, takže `library reseed` změnu doručí. |
| Založení stepu TODO a tasku, `depends_on`, neúspěch běhu, odmítnutí schválení | Kód factory (`run/followups.py`, `run/task.py`, `review/flow.py`) | Musí platit pro každé workflow včetně vlastních workflow repa a nesmí záviset na tom, že agent sám zapíše backlog. Backlog a `.factory/` jsou mimo rozsah zápisu běhu. |
| Podoba popisu PR | Kód factory (`review/prbody.py`) | Deterministické sestavení. Text shrnutí pochází z obálek agentů. |
| Workflows | Beze změny | Workflow jsou data repa. Pravidlo ve workflow by vlastní workflow mohlo obejít. Pole obálky fungují ve všech stávajících workflow beze změny. |

## Popis pull requestu

`pr_body` už necituje zadání tasku. Popis má tuto podobu:

```
<!-- factory: task=<id> branch=<větev> -->

## Cíl
## Co bylo uděláno
## Co uděláno nebylo          (vynechané věci, odchylky, nové tasky v backlogu s ID, jinak „- nic“)
## Důležité pro schválení      (jen když agent uvedl rizika, změny chování nebo ruční ověření)

<!-- factory: summary-end -->

## Technické podrobnosti
### Poznámky k běhům            (jen když běh měl poznámku)
### Agenti                      (souhrn každého agenta zkrácený na jeden řádek)
### Gates a testy
### Review
### Náklady
```

- Skrytá značka `<!-- factory: task=... branch=... -->` zůstává na prvním řádku.
- Shrnutí pochází z nejnovější neprázdné obálky `pr_summary` běhu (`latest_summary`). Prompty žádají shrnutí od buildera, revieweru a documenteru. Pozdější agent tak opraví dřívější shrnutí.
- Když žádný agent shrnutí nedodal, cíl nahradí název tasku s poznámkou „_Agenti běhu shrnutí nedodali._“ a „uděláno“ nahradí souhrn posledního build kroku. Zadání se nekopíruje nikdy.
- Běh `resolve` / `resolve-reviewed` a běh bez shrnutí převezmou shrnutí z dosavadního popisu PR větve (text mezi značkou a `summary-end`, `previous_summary`).
- Nové tasky založené během běhu se přidají do „Co uděláno nebylo“ s ID a důvodem.

## Nedodělky a nová práce

Obálka agenta má nová pole:

- `follow_ups`: seznam `{title, reason, details, blocks_task}`. Práce, která se do tasku nevejde.
- `blocked_by`: ID existujících tasků v backlogu, které task blokují.
- `pr_summary`: `{goal, done, not_done, notes}`.

Prompty buildera, planneru, revieweru, documenteru a testera mají sekci **Unfinished work**: v repu nesmí vzniknout TODO soubory, seznamy otevřených bodů, sekce „později“ ani komentáře `TODO`/`FIXME`. Nová práce se hlásí v `follow_ups`, blokace přes `blocks_task` nebo `blocked_by`. Builder pokrývá i role fix, revise a resolve.

Po workflow (ne u běhů resolve) `run/followups.py::record`:

1. Posbírá hlášení ze všech obálek běhu. Follow-upy se slučují podle názvu, `blocks_task` platí, když ho nastavilo kterékoli hlášení.
2. Najde step TODO projektu tasku (ID `<projekt>-TODO` nebo název „TODO“). Když chybí, založí ho přes `backlog.edit.add_container`.
3. Každý follow-up založí jako task ve stepu TODO (`add_task`) s `related` na původní task. Tělo tasku obsahuje, co je potřeba udělat, sekci `### Původ` (běh, task, krok, agent, důvod) a značku `<!-- factory: follow-up-of=<task> -->`. Podle značky a názvu se task při opakovaném běhu nebo přehrání journalu znovu nezakládá.
4. Blokující follow-upy a ID z `blocked_by`, které existují a nejsou hotové, přidá do `depends_on` tasku (`link_task`). Neznámé ID je varování. Odkaz, který by vytvořil cyklus, se nezapíše, ale blokace platí dál.
5. Změny backlogu commitne do base (`commit_backlog`, zpráva `<task>: TODO tasky z běhu <běh>`). Když commit nejde (main checkout není na base, push selhal…), je to varování a změny zůstanou zapsané.

Výsledek je v `TaskRunResult.follow_ups` a v JSON výstupu běhu (`follow_ups`).

## Blokace

- Když agent ohlásí blokaci, běh skončí jako `failed` s chybou začínající `blocked: task <id> waits for <ID>`. Neotevře se PR, neproběhne auto-merge a task se neoznačí za hotový. Blokaci nezakryje ani chyba při zápisu backlogu.
- Task má v base `depends_on` na blokující task, takže je v backlogu `blocked` a řetěz ho nespustí, dokud blokující task není hotový. Práce zůstává na větvi a ve worktree běhu. Nový pokus po dokončení blokujícího tasku najde existující TODO task a už neblokuje.
- `factory task approve` (i auto-merge, který přes approve jde) odmítne task s nesplněnými `depends_on` v backlogu hlavního checkoutu chybou `task_blocked` (exit 2). Týká se to i staršího otevřeného PR stejného tasku.

## Ověření

- `aifactory/tests/review/test_prbody_summary.py`: pořadí sekcí, žádná citace zadání, nejnovější shrnutí, „- nic“, follow-upy, náhradní shrnutí, převzetí shrnutí u resolve.
- `aifactory/tests/run/test_followups.py`: založení stepu TODO a tasku, převzetí existujícího stepu, idempotence, `depends_on` a stav `blocked`, `blocked_by` (nehotové, hotové, neznámé, cyklus), commit do base, blokovaný běh bez PR, follow-up v popisu PR, odmítnutí schválení `task_blocked`.
- Upravené testy: `tests/run/test_task_pr_flow.py`, `tests/run/test_task_publish.py`, `tests/web/test_web_review.py`. Pole obálky jsou i v seznamech polí kroků `rebase` a `rebuild` (`engine/role_registry.py`).
