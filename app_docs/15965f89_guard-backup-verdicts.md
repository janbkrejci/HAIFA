# Hlídač zápisů: záloha hlavního checkoutu, `context_handoff_dir` v promptech, verdikty R1/R10

Opravuje tři chyby z validace proti GitHubu s rosterem `claude-haiku` (běh `github-185807`):

| # | Chyba | Oprava |
|---|-------|--------|
| V7 | Agent vrátil necommitnutou práci v hlavním checkoutu, hlídač hlásil `REVERTED-BY-AGENT (uncommitted work lost, cannot restore)` | Před každým voláním agenta se necommitnutý stav uloží a po volání se přesně obnoví |
| V6 | Planner zapsal `context_handoff/plan.md` do worktree | Prompty výslovně říkají, že `<context_handoff_dir>` je absolutní cesta mimo repo |
| V8 | R10 hlásil `inconclusive`, i když `run_ok` neprošel | `inconclusive` jen tehdy, když prošly všechny ostatní kontroly |

## 1. Záloha a obnova checkoutu (`aifactory/src/aifactory/run/backup.py`, nový)

- `capture(root, dest, patterns)` zkopíruje do `dest/files/` každou „špinavou“ cestu: změny sledovaných souborů proti `HEAD` (ve stromu i v indexu) a nesledované soubory, které nejsou gitignorované. Symlinky ukládá jako cíl odkazu. Zaznamená `HEAD`, větev a strom indexu (`git write-tree`) a zapíše `manifest.json`. Když kopie selže, vyhodí `OSError`.
- `verify(backup, patterns)` vrátí každou cestu, jejíž obsah už neodpovídá stavu před voláním: cesta, která byla špinavá už předtím, se porovnává s uloženými bajty (SHA-256), každá jiná s `HEAD`. Když se změnil index, přidá pseudo-cestu `(index)`.
- `restore(backup, patterns, paths)` vrátí uvedené cesty do uloženého stavu. Cokoli při tom přepíše nebo smaže, nejdřív přesune do `<backup>/replaced/`, takže se nic neztratí. Pro každou cestu vrátí výsledek: `restored from backup`, `rolled back`, `deleted`, `not restored: HEAD moved` nebo `could not restore (…; backup kept at …)`. Když se pohnul `HEAD` nebo větev, obnoví jen cesty, které byly špinavé už předtím, a index nechá být.
- Prefixy v `patterns` (`ignored()`) se neukládají ani nekontrolují. Gitignorované soubory git nevidí, a proto zůstávají mimo zálohu i kontrolu.

## 2. Hlídač (`aifactory/src/aifactory/run/guard.py`)

- `TaskWriteGuard.snapshot()` před každým voláním agenta uloží zálohu hlavního checkoutu (s vynecháním `main_ignored`) i worktree do `<session>/guard_backup/NNN/{main,worktree}`. Bez session adresáře použije dočasný adresář `haifa-guard-*`. Když záloha selže, vyhodí `PermissionBreach("cannot back up the main checkout before <agent>…")` a agent se nespustí.
- `enforce()`:
  - **Hlavní checkout:** `backup.verify` a potom `backup.restore` na všechno, co se liší. Každá cesta se zapíše do chyby jako `main checkout: <cesta> — <výsledek>` a nakonec se přidá řádek s cestou k záloze. Posunutý `HEAD` se dál jen hlásí a nevrací se.
  - **Worktree:** kontroluje i dřívější necommitnuté změny (práci předchozích fází). Když je agent bez oprávnění změní nebo vrátí, obnoví se ze zálohy. Změny na čistých cestách vrací `roll_back` jako dřív.
  - Bez porušení se záloha fáze smaže. Při porušení zůstane zachovaná.
- `roll_back()` přišel o parametr `before` i o obě větve `REVERTED-BY-AGENT … cannot restore` a `left as-is`. Volá se už jen pro cesty, které byly před fází čisté.

## 3. Prompty (`aifactory/validation/template/.factory/prompts/`)

Do `builder/user.md`, `documenter/user.md`, `planner/system.md`, `planner/user.md`, `reviewer/system.md` a `reviewer/user.md` přibyla věta (v `user.md` hned před `## Task`, v `system.md` mezi instrukcemi):

> `<context_handoff_dir>` is an absolute path outside the repo. Write handoff files at exactly that path; never create a directory of the same name inside the repo or the worktree.

## 4. Verdikty scénářů (`aifactory/validation/scenarios.py`)

- Nový `_inconclusive_unless_failed(res, why)`: vrátí `inconclusive` jen tehdy, když všechny kontroly prošly. Jinak si důvod jen poznamená a verdikt `failed` zůstane. Na něj se nově odkazuje `_roster_gap`.
- V R10 mimo `local` se větev „opravné kolo neproběhlo“ dřív ukončovala `res.inconclusive(...)` bez ohledu na výsledky kontrol. Teď jde přes `_inconclusive_unless_failed`, takže neúspěšný běh (`run_ok`) dává `failed`.

## Testy (žádný nevolá model)

- `aifactory/tests/run/test_guard_backup.py`: jednotkové testy `backup`. Pokrývají `git checkout -- .` a `git clean -fd` nad úpravou sledovaného souboru i nad novým souborem, staged změnu, smazaný sledovaný soubor, stejně dlouhou úpravu, spustitelný bit, ignorované prefixy a `git add` agenta (tedy `(index)`).
- `aifactory/tests/run/test_task_run.py::test_agent_reverting_main_checkout_work_is_restored`: falešný planner spustí v hlavním checkoutu `git checkout -- .` a `git clean -fd`. Test ověří, že běh je `failed`, že `README.md` i `notes/wip.txt` mají původní obsah, že chyba jmenuje obě cesty i `guard_backup` a že v ní není `cannot restore`.
- `aifactory/tests/validation/test_agent_prompts_handoff_dir.py`: každý `*.md` pod `validation/template/.factory/prompts` a `aifactory/src`, který zmiňuje `context_handoff_dir`, musí obsahovat danou větu, a to mimo sekci `## Task`. Takových souborů musí být aspoň 6.
- `aifactory/tests/validation/test_validation_verdicts.py`: `StubContext` místo sandboxu. Ověřuje, že R1 i R10 s neúspěšným během skončí `failed` a s úspěšným během, kterému chybí jen harness nebo opravné kolo, skončí `inconclusive`.

Plán změny: `specs/15965f89_guard-backup-verdicts.md`.

## Ověření

```sh
just test
just typecheck
just lint
just validate --remote local
```

Když hlídač zasáhne v hlavním checkoutu, najdete stav před fází v `<session>/guard_backup/NNN/main/` (`files/` a `manifest.json`). Co obnova přepsala, je v `replaced/`.
