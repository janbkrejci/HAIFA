# Ochrana akcí dashboardu podle stavu tasku

Běžící task a task čekající na review či merge PR nelze znovu spustit,
upravovat, vylepšovat agentem, označit jako hotový ani mu odebírat vazby.
Přechod do těchto stavů při živém obnovení zavře otevřené úpravy.
Blokovaný task lze dále upravovat; spuštění je dostupné pouze tehdy,
když všechny nehotové závislosti čekají v otevřených PR.
U závislostí na stepu či projektu se stavy nehotových tasků načtou z backlogu.
Opožděná odpověď staršího načtení nesmí přepsat novější výsledek a chyba
načtení ponechá spuštění zakázané.

Dialog spuštění nenabízí obcházení nesplněných závislostí pomocí force.
Stacked start nad otevřenými PR zůstává dostupný podle kontroly backendu.
Detail běhu nezná aktuální stav tasku; případný konflikt already_running
proto zobrazí ze serverové odpovědi 409. Kanban běžící task nepřetáhne.

## Ověření

Cílené komponentové testy se spouštějí z `aifactory/web`:

```sh
bun run test src/components/backlog/TaskDetail.test.ts src/components/backlog/RunDialog.test.ts src/components/backlog/KanbanBoard.test.ts src/components/runs/RunDetail.test.ts src/components/runs/FailureCard.test.ts
```

Kontrola shody dodaného statického buildu musí zachytit soubory před
přegenerováním, včetně souborů dosud nesledovaných Gitem. Z kořene repozitáře:

```sh
python3 - <<'PYTHON'
from pathlib import Path
import subprocess

root = Path('aifactory/src/aifactory/web/static')
def snapshot():
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob('*') if p.is_file()}

before = snapshot()
subprocess.run(['just', 'web-build'], check=True)
after = snapshot()
assert before == after, 'Statický build má jiné názvy souborů nebo bajty.'
print(f'Shoduje se všech {len(before)} souborů včetně jejich obsahu.')
PYTHON
```

Samotné úspěšné sestavení ani `git diff` neprokazují shodu původně dodaných
souborů. Kontrola výše porovnává relativní názvy i celý obsah a sestavení
současně provede kontrolu TypeScriptu.

Servírování distribuovaného buildu pokrývá pouze tento cílený test:

```sh
just pytest tests/web/test_web_app.py::test_packaged_build_is_served -n0
```

Ostatní testy tohoto backendového souboru se kvůli této frontendové změně
nespouštějí: ověřují nezměněné API obálky, HTTP metody a validaci hostitele.
