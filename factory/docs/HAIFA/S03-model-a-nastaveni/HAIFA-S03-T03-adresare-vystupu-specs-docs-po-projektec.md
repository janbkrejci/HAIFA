# HAIFA-S03-T03: Adresáře výstupů (specs, docs) po projektech

## Co se změnilo

Spec a dokumentace tasku už nemusí jít vždy do `specs_dir`/`docs_dir` z `.factory/config.yaml`.
Klíče `specs_dir` a `docs_dir` lze nastavit ve front matter tasku i v `index.md` stepu nebo projektu.
Dědí se stejně jako `test` nebo `workflow`: platí nejbližší nastavená hodnota (task → step → projekt),
jinak hodnota z configu. Výsledné cesty se dostanou do promptu agentů i do proměnných
`{{spec_path}}` a `{{doc_path}}`.

```yaml
# backlog/M07-…/index.md
---
id: M07
title: …
specs_dir: docs/M07/specs
docs_dir: docs/M07/app
---
```

### Validace

Hodnota musí být neprázdný relativní řetězec bez `..` a nesmí to být absolutní cesta (`.` projde).
- `factory backlog check` hlásí neplatnou hodnotu (task, step i projekt) jako `invalid_field`.
  Hodnota se přesto v modelu ponechá, aby task, který ji zdědí, selhal a nepoužil potichu adresář z configu.
- `factory task run` pak skončí s kódem `invalid_output_dir` (exit 2) ještě před založením worktree,
  větve a voláním jakéhokoli agenta.

### Zápis výstupů mimo `writes` (guard)

Podle `docs/decisions.md` („Výstupy po projektech“) smí agent s neprázdnými vlastními `writes`
zapsat oba výstupní soubory svého tasku, i když je jeho `writes` nepokrývají. Platí, že:
- cesta musí být v rozsahu tasku (`TaskScope.permits`) a nesmí být mezi `protected_files`,
- agent s `writes: []` výstupy zapsat nesmí,
- jiné soubory mimo `writes` agenta guard dál vrací a fáze selže.

## Kde to je

| Soubor | Změna |
|---|---|
| `aifactory/src/aifactory/backlog/model.py` | `specs_dir`, `docs_dir` přidány do `INHERITED_KEYS` |
| `aifactory/src/aifactory/backlog/derived.py`, `backlog/__init__.py` | `effective_specs_dir()`, `effective_docs_dir()` (nejbližší hodnota přes `_nearest`) |
| `aifactory/src/aifactory/backlog/loader.py` | `OUTPUT_DIR_KEYS`, `_dir_issue()`; kontrola v `index.md` i v tasku |
| `aifactory/src/aifactory/config/settings.py`, `config/__init__.py` | veřejná `check_relative_dir()` (postavená na `_relative`) |
| `aifactory/src/aifactory/run/scope.py` | `output_paths()` bere zděděné adresáře, `OutputDirError`, `TaskScope.is_output()` |
| `aifactory/src/aifactory/run/task.py` | `OutputDirError` → `TaskRunError("invalid_output_dir", …)` |
| `aifactory/src/aifactory/run/guard.py` | `_permitted()` povoluje výstupy tasku agentovi s neprázdnými `writes` |
| `aifactory/src/aifactory/skill/codes.py`, `skill/skill.md` | nový kód `invalid_output_dir` a popis klíčů |
| `specs/HAIFA-S03-T03-adresare-vystupu-specs-docs-po-projektec.md` | spec tasku |

## Jak ověřit

```sh
just test && just typecheck && just lint
```

Nové testy (jen falešný harness, model se nevolá):
- `aifactory/tests/backlog/test_backlog_output_dirs.py` – `check_relative_dir` (přijme `docs/M07/specs`,
  `.`; odmítne `../x`, `/abs`, prázdné, ne-řetězce), `backlog check` hlásí `../x` v projektu i chybné hodnoty
  v tasku, nejbližší hodnota vyhrává a `docs_dir: null` v tasku propadne na předka.
- `aifactory/tests/run/test_task_output_dirs.py` – projekt se `specs_dir: docs/M07/specs` dostane spec
  do `docs/M07/specs/…` a běh projde (cesty jsou v promptu); step/task přebijí projekt; zápis planneru mimo
  jeho `writes` a mimo výstupy se vrátí a fáze selže; agent s `writes: []` výstup zapsat nesmí;
  neplatný adresář zastaví běh s `invalid_output_dir` bez worktree a bez větve `factory/`.
