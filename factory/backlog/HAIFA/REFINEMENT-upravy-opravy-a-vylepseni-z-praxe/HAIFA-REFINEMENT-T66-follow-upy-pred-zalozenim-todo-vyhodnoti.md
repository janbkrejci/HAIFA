---
id: HAIFA-REFINEMENT-T66
title: "Follow-upy: před založením TODO vyhodnotit backlog, nezužovat zadání bez člověka"
status: done
archived: true
workflow: plan-build-test
depends_on: [HAIFA-REFINEMENT-T64, HAIFA-REFINEMENT-T65]
writes: [aifactory/src/aifactory/run/followups.py, aifactory/src/aifactory/run/task.py, aifactory/tests/run/test_followups.py, aifactory/tests/run/test_followups_queue.py, aifactory/tests/run/test_followups_triage.py, docs/decisions.md]
---

## Zadání
Zapojit triáž z HAIFA-REFINEMENT-T65 do zakládání follow-upů, aby se TODO zakládalo jen tehdy, když práci nekryje ani nemůže pokrýt zbytek neudělaného backlogu.

## Současný stav

`aifactory/src/aifactory/run/followups.py` (`record`, `_record`) dnes porovnává follow-up jen podle titulku s otevřenými závislostmi tasku (`open_dependencies`) a jinak zakládá task v TODO stepu projektu. `aifactory/src/aifactory/run/task.py` (`_record_follow_ups`) volá `record` pod `store.serialized()`.

## Co udělat

1. Volání agenta `triager` (`run/triage.ask_triager`) proběhne mimo `store.serialized()`, aby dlouhé volání nedrželo zámek ostatních běhů. Rozhodnutí se pak předají do `record`/`_record` a použijí se pod zámkem nad čerstvě načteným backlogem. Rozhodnutí, které už neplatí (cílový task mezitím není `todo` nebo běží), se zpracuje jako `new`.
2. Použití rozhodnutí v `_record`:
   - `covered`: nic se nezakládá. Do `outcome.created` jde existující task s `existed=True`. Při `blocks_task` se stane blokátorem (`depends_on`).
   - `extend`: do těla cílového tasku se přidá oddíl `### Doplnění z běhu <run_id> tasku <task_id>` s textem doplnění a markerem (např. `<!-- factory: extended-by=<task id> -->`). Retry ani přehraný žurnál nic nezdvojí. Front matter (`writes`, `workflow`, `depends_on`, titulek) ani původní text se nemění. Do `outcome.created` jde s `existed=True`, při `blocks_task` je blokátorem. Zápis jde přes `aifactory.backlog.edit`, stejně jako ostatní úpravy.
   - `decide`: v TODO stepu se založí task s `assignee: human`, který popíše navrhovanou změnu existujícího tasku a důvod, odkáže na oba tasky (`related`) a nese marker follow-upu. Existující task se nemění. Při `blocks_task` blokuje tento human task.
   - `new`: chová se jako dnes (nový TODO task, který podle T64 jde na začátek fronty).
3. Když triáž selže nebo agent chybí (`TriageUnavailable`), běh nespadne: všechny follow-upy se zpracují jako dnes (rozhodnutí `new`) a do `outcome.warnings` přibude varování.
4. `FollowUpOutcome.to_json` / `CreatedFollowUp.to_json` doplnit o druh rozhodnutí (`decision`: covered, extend, decide, new), aby výsledek běhu ukazoval, co se s follow-upem stalo. Na začátek fronty (T64) jdou jen nově založené agentní tasky. Doplněné, krytý ani human task tam nejdou.
5. `docs/decisions.md`, bod **Follow-upy**: popsat triáž, pravidlo „zadání existujícího tasku se bez člověka nezužuje ani zásadně nemění“ a záložní chování.

## Mimo rozsah

- Prompt a typy agenta (T65).
- Úpravy UI.
- `.factory/`, backlog repa.

Hotovo znamená:
- Nový test `aifactory/tests/run/test_followups_triage.py` s namockovaným `ask_triager` ověří pro každý ze čtyř druhů výsledný backlog: covered nic nezaloží, extend přidá oddíl do těla `todo` tasku beze změny front matter a druhý pokus ho nezdvojí, decide založí `assignee: human` task a cílový task nezmění, new založí TODO task. Ověří i blokování (`depends_on`) u covered, extend a decide.
- Test ověří záložní chování: chyba triáže znamená stejné follow-upy jako dnes plus varování.
- Test ověří, že volání triáže neběží pod `store.serialized()`.
- Stávající `aifactory/tests/run/test_followups.py` a `aifactory/tests/run/test_followups_queue.py` jsou zelené (upravené jen tam, kde se mění tvar výstupu).
- `docs/decisions.md` popisuje triáž follow-upů.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-21 · workflow plan-build-test · PR https://github.com/janbkrejci/HAIFA/pull/142 · náklady $0.00
