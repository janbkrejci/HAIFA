# HAIFA-REFINEMENT-T30: Ovládání továrny a souhrn tasků na Přehledu

Na Přehledu (`#/overview`) má každý repozitář ovládání továrny a souhrn stavů tasků.
Ovládání je na kartě repozitáře pod hlavičkou a u repozitáře „v klidu“ přímo v jeho řádku,
protože i klidné repo může mít připravené tasky.

## Spustit továrnu

Zelené tlačítko **Spustit továrnu** (ikona Play) je vidět, jen když zároveň:

- repo má aspoň jeden připravený task (stav kanbanu `ready`, tj. s efektivním workflow
  a splněnými závislostmi) a ten není v kanbanu vyloučený z auto-continue,
- je volný aspoň jeden paralelní slot: `max_parallel_runs` z `.factory/config.yaml` minus
  běžící běhy repa,
- konfigurace je v pořádku (stav `ok`, nebo jen necommitnutá: běh čte konfiguraci z base).

Po kliknutí továrna spustí nejvýš tolik běhů, kolik je volných slotů, a nejvýš tolik, kolik je
spustitelných připravených tasků. Tasky vybírá stejný výběr jako auto-continue
(`run.queue.select_ready`): nejdřív ruční fronta kanbanu, potom zbytek backlogu v pořadí
backlogu, jen `status: todo`. Vyloučené tasky, tasky bez workflow, s nesplněnými závislostmi,
s otevřeným PR nebo už běžící se nespouští. Task, jehož `writes` se překrývají s běžícím
během, s otevřeným PR nebo s taskem spuštěným v tomtéž kliknutí, se přeskočí
(`writes_overlap`). Task se širokými `writes` běží sám (`exclusive`). Proto se může spustit
méně běhů, než je volných slotů. Když se nespustí nic, UI napíše proč (první důvody
přeskočení).

Každý task se spustí stejně jako tlačítkem Spustit u tasku (`factory task run ID` jako
samostatný proces). Jeho běh pak pokračuje dalšími tasky jen podle zděděného
`auto_continue`, tak jako dřív. Žádný nový paralelní mechanismus nevzniká.

Paralelní řetěz auto-continue teď počítá do limitu `max_parallel_runs` všechny běžící běhy
repa, nejen své vlastní. Několik řetězů vedle sebe tak limit nepřekročí.

Během požadavku tlačítko ukazuje spinner.

## Pauza, Pokračovat a Stop

- **Pauza** (je vidět, když běží běh bez pauzy) požádá o pauzu všechny běžící běhy repa
  (`pause_run`). Pauza platí na hranici fáze, takže UI ukazuje „Pozastavuje se – dobíhá
  N běh(y/ů)“, dokud běhy nedokončí rozběhnutou fázi, a pak „Pozastaveno“.
- **Pokračovat** (je vidět, když je některý běh pozastavený nebo se pozastavuje) zruší
  pauzu všech běhů. Bez něj by se pozastavená továrna dala obnovit jen běh po běhu.
- **Stop** (je vidět, když něco běží) se nejdřív zeptá a pak zastaví všechny běžící běhy
  repa (`stop_run`). Zastavování běží na pozadí serveru. UI ukazuje „Zastavuje se – dobíhají
  N běhy“, dokud všechny dotčené procesy neskončí, a potom „Zastaveno“ (ještě 60 s). Běhy,
  které řetěz stihl spustit těsně předtím, se po doběhnutí zastaví také (nejvýš třikrát).
  Zastavený člen řetězu řetěz ukončí, takže z něj nic nového nevznikne. Běh, který nejde
  zastavit (např. běží na jiném stroji), se vypíše jako „Nepodařilo se: TASK – důvod“.

Přehled se obnovuje každé 2 s, takže přechod „dobíhá“ → „zastaveno/pozastaveno“ je vidět
bez ručního obnovení. Repo, ve kterém zastavování ještě probíhá, se nesloží do řádku
„v klidu“.

## Souhrn stavů tasků

U každého repa jsou čipy s počtem tasků v jednotlivých stavech kanbanu (Bez workflow,
Připraveno, Blokováno, Běží, V review, Hotovo, Zrušeno). Stavy bez tasku se nezobrazují.
Vedle čipů je obsazenost slotů („Sloty: běžící/max“). Stav tasku počítá stejná funkce jako
kanban (`web.backlog.board_state`): task s běžícím během, jehož proces žije, je `running`,
task s otevřeným PR je `in review`.

## API

- `POST /api/repos/{id}/control/start`: spustí připravené tasky do volných slotů. Vrací
  `{max_parallel_runs, running, free_slots, started: [{task_id, run_id}], skipped: [...]}`
  (HTTP 200 i tehdy, když se nespustilo nic). `run_id` je `null`, když spuštěný proces
  nestihl běh zapsat.
- `POST /api/repos/{id}/control/pause` a `.../resume`: `{action, run_ids, errors}`.
- `POST /api/repos/{id}/control/stop`: HTTP 202 s `{action, run_ids, pending}`. Průběh je
  v přehledu.
- Tělo požadavku je prázdné nebo `{}`. Jiná pole vrátí `usage_error`. Chyby konfigurace mají
  stejné kódy a stavy jako ostatní akce běhů (`invalid_config` → 500).
- Jednorepový dashboard (`create_app`) má tytéž cesty pod `/api/control/...`.

`GET /api/overview` má u každého repa nové klíče (u chybějícího, negitového, pomalého nebo
rozbitého repa jsou `null`):

- `tasks`: počty tasků podle stavů kanbanu, vždy všech sedm stavů.
- `factory`: `max_parallel_runs` (`null` při neplatné konfiguraci), `running`, `free_slots`,
  `ready` (připravené a nevyloučené), `can_start`, `paused`, `pausing` a `control` (průběh
  zastavení nebo pauzy, kterou spustil dashboard: `{action, run_ids, pending, errors,
  started_at, finished_at}`, jinak `null`).
- každý běh v `running` má `pause` (`null`, `pausing`, `paused`).

Přehled dál jen čte: trace DB otevírá jen pro čtení a vyloučené tasky čte přímo z tabulky
`task_queue`.

## Ověření

- `just pytest tests/run/test_factory_start.py tests/run/test_parallel_chain.py tests/web/test_web_overview.py tests/web/test_web_control.py`
- `just web-test` (`RepoControls.test.ts`, `lib/overview.test.ts`, `OverviewView.test.ts`)
- Ručně: v repu s `max_parallel_runs: 2` a třemi připravenými tasky klik na Spustit továrnu
  spustí dva běhy, tlačítko zmizí (žádný volný slot). Pauza ukáže „Pozastavuje se…“ a po
  dokončení fází „Pozastaveno“. Stop ukáže „Zastavuje se – dobíhají 2 běhy“ a potom
  „Zastaveno“.
