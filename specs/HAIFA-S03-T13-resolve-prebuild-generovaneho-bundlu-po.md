# HAIFA-S03-T13: Resolve – přebuild generovaného bundlu po vyřešení konfliktu

## Problém
Resolve smí měnit jen soubory s konfliktem. Konflikt v generovaném bundlu
(`aifactory/src/aifactory/web/static/`) vyžaduje přebuild, který vytvoří nové
`assets/index-*.js|css` a smaže staré; hlídač to vrátil jako zásah mimo rozsah
(HAIFA-S03-T11, run b80cf773).

## Řešení
- `.factory/config.yaml` dostal klíč `generated`: seznam `{path, command, timeout}`
  (`GeneratedOutput` v `config/settings.py`; `command` jako řetězec nebo seznam,
  `timeout` výchozí 600 s).
- Nový code krok `rebuild` (`workflow/rebuild.py`, registr `CODE_ACTIONS`,
  `roles.yaml`): přestaví každý generovaný výstup, který obsahuje soubor
  s konfliktem z výsledku `rebase`. Build smí měnit jen soubory uvnitř
  přestavovaných výstupů, jinak krok selže. Bez takového konfliktu nedělá nic.
- `resolve.yaml`: `rebuild` (when `rebase.conflict`) běží v cyklu před každým `test`.
- `ConflictWriteGuard` vynechá z rozsahu agentů soubory uvnitř generovaných
  výstupů; agent `resolve`/`fix` je měnit nesmí. Code krok hlídač nesleduje.
- `finish_resolve` ověří, že každý konfliktní výstup byl přestavěn, a commitne
  celý výstup (`git add -A -- <path>`) spolu s vyřešenými soubory.
- Prompt resolve agentovi řekne, že generované výstupy nemá měnit ani buildit.

## Testy
`tests/run/test_task_resolve_generated.py`: přebuild bundlu falešným build
příkazem, porušení hlídače při zásahu agenta do bundlu, konflikt jen ve zdrojích.
