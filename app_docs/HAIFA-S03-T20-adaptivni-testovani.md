# HAIFA-S03-T20 — Adaptivní testování

`just check-scoped` nyní vybírá testy podle dotčených subsystémů a integračních sousedů. Výběr zajišťuje deterministický selektor bez dalšího modelového běhu. Workflow může použít vlastní program se stejným JSON protokolem a výslovně odložit širší ověření na souhrnný task.

## Použití

Dosavadní `just check-scoped` používá nový executor; workflow jej vykonává přímo, se zachováním metadat a jediného testovacího slotu. Vlastní workflow zapne selektor takto:

```yaml
name: adaptive
description: Build and verify affected subsystems
steps:
  - build
  - test:
      selector: [uv, run, --project, aifactory, python, aifactory/tests/select_checks.py]
      full_argv: [just, check]
      allow_skip: true
accept: test.passed
```

Bez selektoru platí dosavadní priorita příkazu task → index → konfigurace → `just test`. Při chybě výběru se použije `full_argv`, jinak efektivní původní příkaz s `HAIFA_TEST_TIER=full`; jeho rozsah se označuje `legacy`. Proměnná `HAIFA_TEST_TIER=full` a rebase/resolve vynutí fallback příkaz a přebijí přeskočení i odklad.

## Protokol a vykonávání

Selektor dostane JSON na stdin; stdout obsahuje jediný plán, diagnostika patří na stderr. Příklad kontextu:

```json
{"version":1,"repo_root":"/repo/worktree","baseline":"0123456789012345678901234567890123456789","head":"abcdefabcdefabcdefabcdefabcdefabcdefabcd","changed_paths":["aifactory/src/aifactory/workflow/parse.py"],"force_full":false,"fallback_argv":["just","check"],"test_timeout":600,"defer_to":null}
```

Příklad vlastního cíleného plánu:

```json
{"version":1,"coverage":"scoped","reason":"Workflow parser changed","checks":[{"name":"workflow","argv":["uv","run","--project","aifactory","pytest","aifactory/tests/workflow","aifactory/tests/run","-n","2","--maxfail=1"],"timeout":300}]}
```

`full`/`scoped` vyžadují 1–32 kontrol, `none`/`deferred` žádnou. Model odmítá neznámé klíče, chybné typy, duplicitní či nebezpečná jména a prázdná argv. Timeout kontroly je kladné celé číslo. Selektor má limit nejvýše 30 sekund a výstup 1 MiB; chyby kontextu, selektoru nebo plánu vyvolají fallback.

Diff zahrnuje commity od připnutého základu, staged/unstaged/untracked změny, odstranění a oba názvy přejmenování. Task runner předává base SHA, samostatné workflow zachytí HEAD před agenty. `HAIFA_TEST_BASE` přenáší základ do podprocesů; samostatný CLI jinak používá merge-base HEAD/main. Každý nový testovací krok výběr přepočítá.

Kontroly běží sekvenčně ve worktree bez shellu, sdílejí jeden slot a časový rozpočet; čekání na slot a výběr mají oddělené limity. První neúspěšná kontrola vrací selhání do opravné smyčky. Vyčerpaný rozpočet zabrání spuštění další kontroly. `none` vyžaduje `allow_skip` a prázdný nebo dokumentační diff: `.md`/`.rst` v kořeni či pod docs/specs/app_docs/backlog.

## Pravidla HAIFA

| Změna | Vybrané ověření |
|---|---|
| Dokumenty nebo prázdný diff | Žádné kontroly |
| workflow; run; review | workflow + run; run + review; review + run |
| config; backlog; providers | config + check + onboard; backlog + run; providers + run |
| harness; library; web backend | harness + workflow; library + onboard; web + e2e |
| Frontend | `web-test` + e2e |
| Test soubor, včetně pomalého | Konkrétní test; při odstranění jeho adresář |
| Engine, nemapované cesty, infrastruktura nebo chybějící testová cesta | `just check` |

Backendový výběr přidává import smoke test, `typecheck` a `lint`. Pytest používá dva workery, e2e běží sériově; relevantní pomalé testy nejsou globálně vyloučeny. Frontend samotný nepřidává backendový pytest, mypy ani Ruff. Testy ověřují výběr příkazů; změna nedokládá měřené procento zrychlení.

## Souhrnné a periodické ověření

Do test kroku lze přidat `defer_to: PROJECT-S01-T99`. Vyžaduje selektor i `full_argv`. Cíl musí být jiný existující task ve stejném projektu se stavem `todo`, pevným test workflow, bez dalšího odkladu a explicitním efektivním test příkazem shodným s `full_argv`. Kontrola proběhne před builderem; neplatný cíl vrací `invalid_test_deferral`. Samostatné workflow potřebuje resolver.

Vlastní selektor může vrátit `scoped` pro minimum kontrol nyní, nebo:

```json
{"version":1,"coverage":"deferred","reason":"Verification in aggregate task","checks":[]}
```

Vestavěný selektor nadále používá mapu subsystémů. Operátor vytvoří souhrnný test-and-fix task přes factory příkazy, vymezí povolené cesty oprav a spustí jej po skupině změn. Odklad jej automaticky nespouští.

`just full-check` ověřuje celý `main` v izolovaném checkoutu a při selhání zakládá opravný task. Příprava checkoutu nyní při chybě skončí bez změny zeleného záznamu. `check-scoped` připomene plné ověření, pokud je jeho stáří neznámé nebo přesahuje 15 commitů.

## Kde změna žije a jak ji ověřit

- `aifactory/src/aifactory/testing/{model,context,executor}.py`: protokol, diff a vykonávání; `aifactory/tests/{tiers,select_checks}.py` a `justfile`: konkrétní výběr HAIFA a recepty.
- `aifactory/src/aifactory/workflow/{model,parse,interpreter}.py`, `aifactory/src/aifactory/run/task.py` a `aifactory/src/aifactory/engine/{runner,quality,data_types}.py`: volby workflow, baseline, validace odkladů a výsledky.
- `aifactory/src/aifactory/review/prbody.py` a `aifactory/src/aifactory/skill/{skill.md,codes.py}`: reportování a veřejný kontrakt.

Artefakty fáze obsahují `plan.json`, `selector.log` a logy kontrol. `test_plan` přenáší rozsah, důvod, počet vykonaných kontrol, cíl odkladu a důvod fallbacku do review i PR. `passed=true` při `none`/`deferred` znamená splnění politiky s nulou kontrol; PR to výslovně uvádí.

Regrese pokrývají protokol, fallback, časový rozpočet, sloty, opravu a nový výběr, odklady, resolve, reportování i zelený záznam full-check. Cílené ověření:

```bash
uv run --project aifactory pytest aifactory/tests/workflow/test_workflow_adaptive_test.py aifactory/tests/workflow/test_workflow_inputs.py aifactory/tests/run/test_task_test_deferral.py aifactory/tests/run/test_task_resolve.py aifactory/tests/test_tiers.py aifactory/tests/check/test_justfile_recipes.py -n0 --maxfail=1
```

Pro plné ověření implementace použijte `just check`. V této dokumentační fázi testy nebyly spouštěny.
