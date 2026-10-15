# HAIFA-REFINEMENT-T39: Task čekající na review neuvolňuje slot pro paralelní běhy

## Co se změnilo a proč

Volné sloty (`max_parallel_runs`) se dřív počítaly jen ze živých běhů. Když běh skončil a jeho PR čekal na review, slot se hned uvolnil a továrna nebo řetěz spustily další task. Teď slot drží i task, jehož PR je otevřený a nesloučený.

1. **Obsazený slot.** Slot obsazuje task s živým během (také člen jiného řetězu nebo samostatný běh) a task s otevřeným PR. Task, který má zároveň živý běh (resolve, retry) i otevřený PR, zabere jen jeden slot. Počítá to `run.queue.Slots`.
2. **Uvolnění.** Slot se uvolní, až když se PR sloučí nebo zavře, nebo když task skončí bez PR (selhal, je zablokovaný nebo zastavený).
3. **Kde platí.** Platí pro „Spustit továrnu“ (`start_factory`), pro plnění slotů paralelního řetězu a pro `free_slots` v `/api/chains` i v přehledu (`factory`). Sekvenční řetěz (`max_parallel_runs: 1`) zůstal beze změny: pokračuje jako dřív a sloty nepočítá.
4. **Důvod je vidět.** Když volné sloty drží PR čekající na review, další připravený task se přeskočí s novým důvodem `no_slot`. Detail vyjmenuje PR čekající na review a běžící tasky, `waits_on` obsahuje tasky s těmi PR. `start_factory` navíc vrací `in_review` (tasky, které drží slot otevřeným PR), stejně tak `/api/chains` u běžícího řetězu. Přehled vrací v bloku `factory` počet `in_review`. Pokud sloty drží jen živé běhy, chová se vše jako dřív a skip `no_slot` nevzniká.
5. **Beze změny** zůstala pravidla pro kolize `writes` s běhy a otevřenými PR (`Occupancy`, `writes_overlap`) i pro `exclusive`.

## Kde to je

- `aifactory/src/aifactory/run/queue.py`: třída `Slots` (`count`, `of`, `taken`, `free`, `skip`), nový důvod `no_slot` v `SKIP_REASONS`, `start_factory` a `fill` paralelního řetězu počítají sloty přes `Slots`. Docstring modulu popisuje nové počítání.
- `aifactory/src/aifactory/web/chains.py`: `free_slots` běžícího řetězu se počítá ze slotů celého repa, přibyl klíč `in_review`.
- `aifactory/src/aifactory/web/overview.py`: `factory.free_slots` počítá i otevřené PR, přibyl klíč `factory.in_review`.
- `aifactory/src/aifactory/web/control.py`: docstring.
- `aifactory/src/aifactory/guide/06-behy.md`, `aifactory/src/aifactory/skill/skill.md`: popis slotů a důvodu `no_slot`.

## Jak ověřit

- `cd aifactory && uv run pytest tests/run/test_factory_start.py tests/run/test_parallel_chain.py tests/web/test_web_chains.py tests/web/test_web_overview.py -n0`.
  - `test_factory_start.py`: živý běh a otevřený PR jiného tasku při dvou slotech nespustí nic a vrátí skip `no_slot`. Sloučený nebo zavřený PR slot uvolní. Task s během i PR zabere jeden slot.
  - `test_parallel_chain.py`: řetěz neplní slot, který drží PR čekající na review. Sloučený PR slot uvolní. Otevřený PR jiného tasku drží slot řetězu. `FakeRunner` teď ukládá PR jako sloučený, pokud test nechce, aby čekal na review (`review`, `open_prs`).
  - `test_web_chains.py`, `test_web_overview.py`: `free_slots` a `in_review` po započtení PR čekajících na review.
- Ručně v `just dash`: se dvěma sloty, jedním běžícím taskem a jedním otevřeným PR ukáže přehled 0 volných slotů a Spustit továrnu nic nespustí.
- Dashboard zatím pro `no_slot` neukazuje český popisek, jen kód důvodu. Frontend (`aifactory/web/`) nebyl mezi povolenými cestami.
