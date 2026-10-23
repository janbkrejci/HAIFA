# Sdílený výběr harnessu, modelu a thinking

`backlog.derived.harness_values(node)` vybírá hodnoty pro task, step i projekt stejným algoritmem. Prochází předky od nejvyššího k nejbližšímu a nakonec samotný uzel. Přebírá pouze neprázdné hodnoty `harness`, `model` a `thinking`. Změna harnessu odstraní zděděný model; model uvedený přímo s novým harnessem zůstane. Thinking se při změně harnessu zachová. Funkce nemění vstupní uzly.

Veřejná funkce `run.task.task_harness_values(task)` zůstává tenkým wrapperem. Běh ani retry tasku nemění pořadí aplikace nastavení a ručních přepisů.

`harness.settings.context_binding(values)` doplňuje vazbu přes `effective_override(values, None)`: přednost mají hodnoty objektu, chybějící hodnoty doplní nastavení počítače z `harnesses.json`. Pro repo bez objektu se předá `{}`. Pokud harness neurčí objekt ani počítač (včetně uloženého `default_harness: null`), vrátí `{}` a poradce použije roster plan agenta. Chyby konfigurace, zakázaný harness a neúspěšný test výchozího modelu se nezamlčují. Přísná validace běhu tasku v `effective_override` zůstala zachována.

Návrh workflow a „Vylepšit task“ používají tuto vazbu v `effective` i při výběru skutečného agenta. Existující task dědí ze svého uzlu; draft nového tasku ze zvoleného stepu a jeho předků. Neharnessová pole kontextu se skládají dosavadním způsobem. Výsledek jobu v POST i GET obsahuje advisor včetně thinking, pokud je nastaveno; to platí také pro roster fallback.

Ruční volba v dialogu „Vylepšit task“ má nadále přednost. Samotný harness vezme svůj model z počítače; harness s modelem použije zvolený model. Tato větev nepřebírá model ani thinking objektu. Nabídka options zachovává dosavadní tvar harness/model.

Otisk workflow se počítá před doplněním advisoru, takže návrh lze uložit a změna zděděných hodnot jej zneplatní. Otisk task advice zahrnuje ruční volbu advisoru, aby se různé volby nesloučily do jednoho běžícího jobu.

Frontend, pravidla editace backlogu a ostatní AI pomocníci se nemění. Testy nižších přepnutí harnessu používají strom nebo již uložené hodnoty; nerozšiřují pravidla editace.

## Ověření implementace

- Cílený pytest pěti souborů: `tests/backlog/test_backlog_harness_values.py`, `tests/harness/test_harness_settings.py`, `tests/workflow/test_workflow_advice.py`, `tests/web/test_web_workflow_advice.py` a `tests/web/test_web_task_advice.py`. První běh měl 75 úspěšných případů a tři chybná očekávání v nových testech. Po opravě očekávání a doplnění dvou případů nižšího přepnutí prošlo všech 15 opakovaně spuštěných případů z backlog testu a testů `test_advisor_inherits_task_settings` a `test_advisor_defaults`. Celkem ověřeno 80 jedinečných případů.
- Nezměněné testy `tests/run/test_task_run.py` a `tests/run/test_task_retry.py`: 59 prošlo. Zahrnují dědění při přepnutí harnessu i retry.
- `ruff check` a `ruff format --check` nad deseti změněnými Python soubory prošly. Ověření používá konkrétní soubory podle omezení builder fáze; celý adresář `tests/run/` ani celá sada se zde nespouštěly.
- Testy používají lokální repozitáře, izolované nastavení počítače a fake harnessy. Žádný živý model nebyl volán. Pytest hlásí stávající deprekační varování Pydantic v enginu.
- `MYPYPATH=tests uv run mypy` s výčtem deseti změněných Python souborů: bez chyb. `MYPYPATH` zpřístupňuje sdílené testovací helpery při kontrole konkrétních souborů.
