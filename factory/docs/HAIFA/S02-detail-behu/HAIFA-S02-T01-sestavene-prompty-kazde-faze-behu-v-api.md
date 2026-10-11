# HAIFA-S02-T01: Sestavené prompty každé fáze běhu v API

## Co se změnilo a proč

Engine dosud ukládal sestavené prompty jen jednou za agenta do `<session>/<agent>/prompts/{system,user}.md`. Další fáze téhož agenta je přepsala, takže fáze `build` ukazovala prompt z `revise_1`. Nově si každá fáze agenta nechá vlastní kopii a dashboard ji vydává přes API.

### Ukládání (engine)

- `aifactory/src/aifactory/engine/prompts.py`: přibyly konstanta `PHASES_DIR = "phases"` a funkce `phase_dir(prompts_dir, phase_name)`. Funkce vrací `<agent>/prompts/phases/<phase>/`.
- `aifactory/src/aifactory/engine/agents.py` (`execute`): po uložení promptů na úrovni agenta zapíše tentýž `system.md` a `user.md` ještě do `phase_dir(..., phase.params.name)`. Soubory agenta zůstávají a dál v nich je poslední fáze. Obě změny mají značku `# aifactory 2.10:`.

Rozložení v session adresáři:

```
<data_dir>/sessions/<run_id>/<agent>/prompts/
  system.md, user.md                 # poslední fáze agenta (jako dřív)
  phases/<phase_name>/system.md, user.md
```

### Hledání session adresáře

`aifactory/src/aifactory/run/task.py` má novou funkci `session_dir_of(repo, run_id)`. Vrací `<data_dir>/sessions/<run_id>`, přičemž `data_dir` bere z konfigurace běhu v hlavním checkoutu: z `data_dir` v `agents.yaml`, jinak z `.factory/data`. Session adresář se tedy nehledá vedle trace DB.

### API

`GET /api/runs/{run_id}/phases/{phase_id}/prompts`: route a handler `run_phase_prompts` jsou v `aifactory/src/aifactory/web/app.py`, logika ve funkci `phase_prompts` v `aifactory/src/aifactory/web/runs.py`.

Odpověď je standardní envelope a její `data` obsahuje:

| pole | význam |
|---|---|
| `run_id`, `phase_id`, `phase`, `agent`, `kind` | identifikace fáze z tabulky `phases` (`phase` = `name`, `agent` = `owner`) |
| `system`, `user` | text promptu, nebo `null`, když soubor chybí |
| `source` | `"phase"` (soubory fáze), `"agent"` (záložní poslední prompty agenta), nebo `"none"` |
| `legacy` | `true`, pokud je `source == "agent"`; v `warnings` je pak i varování |
| `truncated` | `{system: bool, user: bool}` |
| `max_bytes` | `MAX_PROMPT_BYTES` (256 KiB) |

Jak se odpověď skládá:
- Fáze s `kind == "code"` prompty nemá. Vrátí `source: "none"` a obě hodnoty `null`.
- Nejdřív se čte `phases/<name>/`. Když tam není ani jeden soubor, použijí se prompty na úrovni agenta (to platí pro starší běhy).
- Chybějící soubor dává `null` s HTTP 200.
- Neplatné `run_id` nebo `phase_id` vrátí 400 `invalid_value`. Povolený vzor je `[A-Za-z0-9][A-Za-z0-9._-]{0,199}` bez `..`.
- Neznámý běh vrátí 404 `unknown_run`. Neznámá fáze, nebo fáze jiného běhu, vrátí 404 `unknown_phase`. Tento kód přibyl v `aifactory/src/aifactory/skill/codes.py` a mapuje se na 404.
- Ochrana proti cestě ven: `owner` a `name` z DB musí projít stejnou kontrolou segmentu, jinak se nic nečte a vrátí se varování. Každý soubor se po vyřešení symlinků musí nacházet uvnitř session adresáře, jinak je `null`.
- Soubor delší než `MAX_PROMPT_BYTES` se zkrátí a nastaví se `truncated.<kind> = true`. Text se dekóduje jako UTF-8 s `errors="replace"`.

## Jak ověřit

Testy v `aifactory/tests/`, model se nevolá:
- `aifactory/tests/engine/test_phase_prompts.py`: fáze `build` a `revise_1` téhož agenta mají přes falešný harness každá svůj `user.md`; soubor na úrovni agenta drží poslední fázi.
- `aifactory/tests/web/test_web_phase_prompts.py`:
  - build a revise mají v API různé prompty,
  - starší běh dostane prompty agenta (`legacy`),
  - chybějící soubory a fáze typu `code` vrací `null`,
  - neznámý běh a neznámá fáze vrací 404, neplatné id 400,
  - únik přes `owner` i přes symlink se nepovede,
  - velký soubor se zkrátí,
  - `data_dir` z `agents.yaml` se respektuje.

```
just test
just typecheck
just lint
```

Ručně: `curl http://127.0.0.1:4700/api/runs/<run_id>/phases/<phase_id>/prompts`.

Mimo rozsah: zobrazení v UI, `context_handoff/` a `raw_output.jsonl`.
