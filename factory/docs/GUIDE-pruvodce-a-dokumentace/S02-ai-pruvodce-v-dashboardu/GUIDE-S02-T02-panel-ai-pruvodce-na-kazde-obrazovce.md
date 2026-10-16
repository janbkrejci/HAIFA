# AI průvodce: panel v dashboardu

Ikona jiskry v horní liště otevře panel **AI průvodce** na kterékoli obrazovce. Panel
zůstane otevřený a se stejným vláknem i při přechodu mezi obrazovkami a po obnovení stránky.

## Použití

- Napiš otázku a odešli ji tlačítkem **Odeslat** nebo klávesou Enter (Shift+Enter je nový řádek).
- Nad polem zprávy je chip s aktuální obrazovkou (repo, task, běh). Pošle se s otázkou,
  takže průvodce ví, co je „tenhle běh“. Křížkem ho pro danou obrazovku odebereš.
- Odpověď se vypisuje průběžně, i s příkazy, které průvodce spouští. Je to markdown;
  zmíněné tasky, běhy a PR jsou odkazy do dashboardu.
- Prázdné vlákno nabídne tři otázky podle obrazovky, u selhaného běhu třeba
  „Proč tenhle běh selhal?“.
- Ikona hodin ukáže starší vlákna, **+** založí nové. V hlavičce je harness a model,
  který vláknu odpovídá. Vybírá se při první zprávě podle nastavení počítače.

## Omezení

- Odkaz z textu bez repa vede do repa, ke kterému se otázka vztahovala; bez kontextu
  do jediného registrovaného repa, jinak do repa otevřeného v URL.
- Odkaz na PR podle čísla vede na obrazovku Review repa, ne na konkrétní PR.
