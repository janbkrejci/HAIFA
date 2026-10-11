# HAIFA-REFINEMENT-T06: Výsledky kontroly Factory

## Ověřený stav

Ověřeno dne 2026-10-08 z worktree `b60b39e3`. Příkaz
`just factory check --json` kontroluje hlavní checkout
`/Users/jbk/Documents/HAIFA` a konfiguraci v base `main`, commit
`eb890f4db10842d588870210a49a71b8261cd0ca`.

| Nález | Výsledek | Další postup |
| --- | --- | --- |
| `repo_onboarded` (repo, info) | Akce `adopt` ověřena a provedena bez zápisů. Nález zůstává jako informace o úspěšném onboardingu. | Na tomto počítači není co importovat. Na dalším počítači použít `factory adopt`, nikdy znovu `onboard`. |
| `item_local` (repo, info) | Přetrvává pro `manual-test-duration`, verze `60c19b4d`. Export ověřen pouze náhledem. | Operátor musí exportovat workflow do knihovny a commitnout vazbu v manifestu do base mimo tento běh. |

### `repo_onboarded`: adopt

`just factory adopt --dry-run --json` skončil kódem 0. Knihovna
`/Users/jbk/.config/haifa/library` má očekávané ID
`edd1ceda-ef2e-4f4d-b7a8-68b029433780`, `matches: true`, a head
`e634c367f167cf46a5f4cd5f0b80d6e738be49ae`. Všech devět položek manifestu
(čtyři agenti a pět workflows) má `state: synced`, `adopt: present`.
`imported: []`, `plan: null`; nejsou potřeba žádné zápisy do knihovny.

Na základě tohoto náhledu byl proveden `just factory adopt --json`.
Výsledek: exit code 0, `ok: true`, `dry_run: false`, `imported: []`,
`plan: null`, `committed: false`, `library_commit: null`,
`repo_changed: false`. Informační nález dál správně zaznamenává onboarding
z `pre_library` dne `2026-10-08T16:21:38Z` od Jan B. Krejčí (Factory 0.1.0).

### `item_local`: export

`just factory config export workflow manual-test-duration --dry-run --json`
skončil kódem 0, `ok: true`, `validation.ok: true`, `blockers: []`.
Náhled má `target: worktree`; není to ověření připravenosti commitu do main.
Obsahuje přesně tyto změny:

- V knihovně vytvořit `workflows/manual-test-duration.yaml`.
- V repozitáři upravit `.factory/manifest.yaml`, přidat vazbu na položku
  `manual-test-duration` s verzí
  `sha256:60c19b4db36ddbf9868f3ef48c116d663854b508f50fbf93b860e06d34fa8812`.

`export.action: create`, předchozí verze v manifestu a knihovně jsou `null`.
Náhled nic nezapsal: `written: false`, `committed: false`, `pushed: false`,
`library_commit: null`. Workflow nebylo spuštěno.

Překážkou skutečného exportu jsou oprávnění běhu: `.factory/` je chráněná
a není mezi povolenými cestami, knihovna je mimo worktree. Export nejprve
zapisuje a commituje knihovnu a poté upravuje manifest. Ani výchozí export
bez `--commit` tedy není v rozsahu běhu. Změna pouze v knihovně by navíc
neodstranila lokální stav workflow v konfiguraci base.

## Postup pro operátora po skončení běhů

V hlavním checkoutu obnovit náhled pro commit do base:

```bash
cd /Users/jbk/Documents/HAIFA
just factory config export workflow manual-test-duration --dry-run --commit --json
```

Zkontrolovat aktuální verzi, cílové soubory v knihovně i repozitáři,
validaci a prázdné `blockers`. Exit code 0 náhledu sám nestačí. Případný
`run_in_progress` řešit dokončením aktivních běhů; další překážky řešit podle
aktuálního výstupu. Poté použít čerstvý `data.digest` tohoto náhledu
(nikoli `library_plan.digest` ani digest z worktree):

```bash
just factory config export workflow manual-test-duration --commit --expect <DIGEST_Z_NOVEHO_PLANU> --json
just factory check --json
just factory adopt --dry-run --json
```

Export může commitovat a pushovat konfiguraci repozitáře; tuto operaci
provádí operátor. Pokud se plán změnil, obnovit jej před opakováním.
Ověřit, že kontrola již neobsahuje `item_local` pro toto workflow a nový
náhled `adopt` uvádí `manual-test-duration` jako `synced` / `present`.
`repo_onboarded` má zůstat informačním nálezem.

Na dalším počítači nejprve zajistit odpovídající knihovnu a poté spustit
`factory adopt --dry-run --json` a `factory adopt --json`. Manifest nyní
uvádí `library.remote: null`; nelze z něj odvodit funkční příkaz pro klonování.
Operátor musí zajistit přenos knihovny nebo její dostupný remote. Opětovný
onboarding repozitáře není správný postup.

## Validace

Po operacích a zápisu dokumentů opakovaný `just factory check --json`
skončil kódem 0, `ok: true`: **0 error, 2 warning, 2 info**.
Oba vybrané informační nálezy přetrvávají z důvodů popsaných výše.
Další nálezy jsou `workflow_unset` pro `HAIFA-S90-T01`, `HAIFA-S90-T03`,
`HAIFA-S90-T04`, `HAIFA-S90-T07` a `codex_not_isolated` na tomto počítači;
jsou mimo vybraný rozsah. Kontrola nehlásí žádný nález knihovny.

`uv run mypy --cache-dir .mypy_cache` z `aifactory/` prošel s exit code 0
(406 zdrojových souborů). `just lint` prošel s exit code 0 (Ruff check
i kontrola formátování 420 souborů). Cache mypy zůstává ve worktree.
`git diff --check` skončil kódem 0. Mění se jen dva dokumenty tohoto úkolu,
proto regresní testy ani celá testovací sada nejsou potřeba.
