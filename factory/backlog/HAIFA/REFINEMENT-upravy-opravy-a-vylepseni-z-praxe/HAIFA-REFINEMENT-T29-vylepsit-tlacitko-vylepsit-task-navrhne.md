---
id: HAIFA-REFINEMENT-T29
title: "Vylepšit tlačítko Vylepšit task: navrhne i workflow"
status: todo
workflow: build-test-review
depends_on: []
related: [HAIFA-REFINEMENT-T07, HAIFA-REFINEMENT-T18, HAIFA-S01-T38, HAIFA-S03-T21]
writes: [aifactory/]
---

## Zadání
Tlačítko „Vylepšit agentem“ na detailu tasku (a ve formuláři tasku) má zároveň navrhnout i správné workflow pro task. Samostatné tlačítko pro návrh a volbu workflow vedle výběru workflow ve formuláři zůstává na svém místě a funguje dál.

## Současný stav
- `ImproveButton.vue` volá `/backlog/task-advice`. Návrh obsahuje i pole `workflow`, ale jen z existujícího katalogu. `TaskForm.applyParameters` ho zapíše do výběru a zahodí případný výsledek návrhu workflow (`advice.value = null`).
- `WorkflowAdvice.vue` (návrh workflow) umí doporučit existující nebo nové workflow (`decision`, `workflow_yaml`, `outline`, `reason`). Uloží se přes `workflow_advice_id` při uložení tasku.

## Požadavek
- Po jednom kliknutí na „Vylepšit agentem“ dostane uživatel vylepšené parametry tasku i návrh workflow. Návrh workflow má stejnou kvalitu a možnosti jako samostatné tlačítko návrhu workflow, včetně možnosti navrhnout nové workflow, a vychází z už vylepšeného zadání.
- Navržené workflow se předvyplní do výběru workflow ve formuláře. Zobrazí se jeho zdůvodnění (u nového workflow i náhled jako u WorkflowAdvice). Při uložení se nové workflow uloží stejně jako dnes (`workflow_advice_id`).
- Samostatné tlačítko návrhu workflow zůstává a dál jde spustit samostatně.
- Během běhu je stav vidět (spinner nebo blokace polí jako dnes). Chyba návrhu workflow nesmí zahodit už aplikované vylepšení parametrů. Uživatel uvidí chybovou hlášku a může návrh workflow spustit samostatným tlačítkem.
- Zachovat stávající pravidla: rušení při změně zadání nebo repa, blokaci u hotových, zrušených, běžících a v review tasků, zobrazení nákladů a agenta.

## Akceptační kritéria
- Klik na „Vylepšit agentem“ na detailu tasku i ve formuláři vyplní vylepšené parametry a navržené workflow včetně zdůvodnění.
- Pokud návrh doporučí nové workflow, uloží se po uložení tasku a task na něj odkazuje.
- Samostatné tlačítko návrhu workflow funguje beze změny chování.
- Testy frontendu (ImproveButton, TaskForm, TaskDetail, WorkflowAdvice) a dotčené backendové testy pokrývají nové chování. Statický bundle dashboardu je přegenerovaný.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
