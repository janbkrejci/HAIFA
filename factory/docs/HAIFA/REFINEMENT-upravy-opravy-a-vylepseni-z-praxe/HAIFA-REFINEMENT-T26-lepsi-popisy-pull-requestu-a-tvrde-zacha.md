# HAIFA-REFINEMENT-T26: Lepší popisy pull requestů a tvrdé zacházení s nedodělky

## Co se změnilo

1. **Popis PR** už necituje zadání tasku. Začíná shrnutím, které napsali agenti běhu (cíl, co bylo uděláno, co ne, co je důležité pro schválení). Technické podrobnosti následují až za ním.
2. **Nedodělky** se nesmí nechávat v repu. Agent je ohlásí ve své obálce a factory z nich založí tasky ve stepu `TODO` projektu. Když agent ohlásí blokaci, běh skončí neúspěchem, task dostane `depends_on` na blokující task a nedá se schválit ani sloučit.

## Rozdělení mezi kód, prompty a workflows

| Co | Kde | Proč |
|---|---|---|
| Kanál od agenta k factory | Nová pole `EnvelopeBase` (`engine/data_types.py`): `pr_summary`, `follow_ups`, `blocked_by` | Typovaná obálka je jediná cesta od agenta k factory a má ji každá role. Všechna pole mají výchozí hodnoty, takže starší obálky a journaly zůstávají platné. |
| Pravidlo „žádné skryté nedodělky“ a jak hlásit práci, blokaci a shrnutí | Prompty seed agentů `builder`, `planner`, `reviewer`, `documenter`, `tester` (`system.md` + `user.md`) | Jen agent pozná, kdy práce přesahuje task. |
| Založení TODO stepu a tasku, `depends_on`, neúspěch běhu, odmítnutí schválení | `run/followups.py`, `run/task.py`, `review/flow.py` | Musí platit v každém workflow a nesmí záviset na tom, že agent sám zapíše do backlogu. |
| Sestavení popisu PR | `review/prbody.py`, `review/publish.py` | Deterministické. Factory jen sestaví text, který napsali agenti. |
| Workflows | beze změny | Pole obálky fungují ve všech stávajících workflows. Pravidlo ve workflow by vlastní workflow repa mohlo obejít. |

`docs/decisions.md` tato změna neupravuje. Rozhodnutí je zdůvodněné jen v této tabulce.

## Popis pull requestu (`review/prbody.py`)

```
<!-- factory: task=<id> branch=<větev> -->
## Cíl
## Co bylo uděláno
## Co uděláno nebylo          (vynechané věci, odchylky, nové tasky s ID; jinak „- nic“)
## Důležité pro schválení      (jen když agent uvedl poznámky)
<!-- factory: summary-end -->
## Technické podrobnosti
### Poznámky k běhům / ### Agenti / ### Gates a testy / ### Review / ### Náklady
```

- Skrytá značka na prvním řádku zůstala beze změny.
- `latest_summary` použije nejnovější neprázdnou obálku `pr_summary` z běhu. `pr_summary` vyžadují prompty buildera, revieweru a documenteru, takže pozdější agent může opravit dřívější shrnutí.
- Když žádný agent shrnutí nedodal, jako cíl se použije název tasku s poznámkou „_Agenti běhu shrnutí nedodali._“ a jako „uděláno“ souhrn posledního kroku s `changed_files`. Text zadání se nekopíruje nikdy.
- Běh z `INTERNAL_WORKFLOWS` (resolve) a běh bez shrnutí převezmou shrnutí z dosavadního popisu PR větve. `previous_summary` vezme text mezi značkou na prvním řádku a `summary-end`.
- Tasky z `follow_ups`, které běh založil, se přidají do „Co uděláno nebylo“ s ID, názvem a důvodem.
- Souhrny agentů, review a poznámky k běhům se zkracují na jeden řádek (`_short`).

## Nedodělky a blokace

Obálka agenta má tato nová pole:

- `follow_ups: [{title, reason, details, blocks_task}]`
- `blocked_by: [<id existujícího tasku>]`
- `pr_summary: {goal, done, not_done, notes}`

Dotčené prompty mají sekci **Unfinished work**. Zakazuje TODO soubory, seznamy otevřených bodů, sekce „později“ a komentáře `TODO`/`FIXME`, a popisuje, jak hlásit novou práci a blokaci.

Po workflow (kromě běhů resolve) volá `run/task.py::_execute` funkci `followups.record`. Ta:

1. Posbírá hlášení ze všech obálek běhu. Follow-upy se stejným názvem sloučí (bez ohledu na velikost písmen a mezery). Sloučený follow-up blokuje task, když blokaci nahlásilo kterékoli z hlášení.
2. Najde step TODO projektu (ID `<projekt>-TODO` nebo název „TODO“). Když chybí, založí ho přes `add_container`.
3. Každý follow-up založí jako task (`add_task`, `related` = původní task). Tělo tasku obsahuje, co se má udělat, sekci `### Původ` (běh, task, krok, agent, důvod) a značku `<!-- factory: follow-up-of=<task> -->`. Podle značky a názvu se při opakovaném běhu nic nezakládá znovu.
4. Do `depends_on` tasku zapíše (`link_task`) blokující follow-upy a existující nehotová ID z `blocked_by`. Neznámé ID a odkaz, který by vytvořil cyklus, skončí varováním. Nezapsaná blokace ale dál platí.
5. Změny backlogu commitne do base zprávou `<task>: TODO tasky z běhu <běh>`. Když commit selže, skončí to varováním.

Když existuje aspoň jeden otevřený blocker, běh skončí jako `failed` s chybou `blocked: task <id> waits for <ID…>`. PR se neotevře, auto-merge neproběhne a task se neoznačí za hotový. Blokaci nezakryje ani výjimka při zápisu backlogu (`_record_follow_ups`).

`approve_task` (přes něj jde i auto-merge) nově volá `_refuse_blocked`. Task s nesplněnými `depends_on` v backlogu hlavního checkoutu odmítne chybou `task_blocked` (exit 2, `skill/codes.py`).

Výstup: `TaskRunResult.follow_ups`, klíč `follow_ups` v JSON výstupu `factory task run` a výstupu řetězu (`run/queue.py`) a řádky `follow-up (…): <id> <název>` v textovém výstupu CLI. Uživatelský návod popisuje novou podobu PR a blokaci v `guide/06-behy.md` a `guide/07-review.md`.

Pole obálky přibyla i do seznamů polí kroků `rebase` a `rebuild` (`engine/role_registry.py`).

## Ověření

```
cd aifactory && uv run pytest tests/review/test_prbody_summary.py tests/run/test_followups.py \
  tests/run/test_task_pr_flow.py tests/run/test_task_publish.py tests/web/test_web_review.py -n0
```

- `test_prbody_summary.py`: pořadí sekcí, žádná citace zadání, nejnovější shrnutí vyhrává, „- nic“, výpis follow-upů, náhradní shrnutí, převzetí shrnutí u resolve.
- `test_followups.py`: založení i převzetí TODO stepu, task s původem, idempotence, `depends_on` a stav `blocked`, `blocked_by` (nehotový, hotový, neznámý task, cyklus), commit do base, blokovaný běh bez PR, follow-up v popisu PR, `task_blocked` při schválení.
- Ručně: spusť task, jehož agent vrátí `follow_ups` s `blocks_task: true`. Běh skončí `blocked: …`, v backlogu přibude `<projekt>-TODO-T01` a task je `blocked`.
