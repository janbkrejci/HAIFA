# HAIFA-S06-T04: Převod instalace sssf při onboardingu

## Co se změnilo

`factory onboard` teď umí převést repo s instalací sssf (`adws/`, stav `sssf`). Dřív takové repo skončilo blokátorem `sssf_not_supported`. Převod je jednorázový: konfigurace sssf přejde do knihovny a do nového `.factory/` (`config.yaml`, `agents.yaml`, `prompts/`, `extensions/`, `workflows/`, `manifest.yaml` s `onboarding.source: sssf`). Převodník čte jen strom base (`git ls-tree`, `git cat-file`) a nic nespouští. `adws/` zůstane byte po bytu a do repa se jen přidává.

Postup je stejný jako u `pre_library`: `--dry-run`, ukázat `data.report` (nově i s `detail`), `data.files`, `data.library_plan` a `data.digest`, pak `--commit --expect DIGEST`. Nový přepínač `--workflows` přidá kromě `simple-sdlc` i knihovní workflow ostatních rozpoznaných stock chainů. Na repu `pre_library` vrátí `conflicting_options`.

### Tabulka převodu (implementace v `onboard/sssf.py`)

| sssf | HAIFA | kód |
|---|---|---|
| roster `adws/adw_sssf_config/sssf.config.yaml` (jen tento) | `.factory/agents.yaml` s odkazem na roster v hlavičce | `converted`; další rostery hlásí varování `alternate_rosters` |
| `coding_agent` | `harness` (`claude_code` → `claude`) | |
| `model`, `tools`, `color`, `writes`, `disallowed_commands` | stejné klíče | |
| `thinking: auto` | `medium` | `changed_meaning` |
| `writes` s `**/*.md` | ponechá se | `changed_meaning` |
| `defaults.protected_files` | `protected_files` v `config.yaml` za `.factory/` | |
| `defaults.data_dir`, `observability` | nic | `not_converted` |
| stock `system.md` | prompt položky z knihovny | `linked` |
| upravený `system.md` | `git merge-file` (base stock, ours repo, theirs knihovna). Čistý merge → `converted`, konflikt jen ze vložení → `--union` | `converted` / `carried_over` |
| jiný konflikt / upravený `user.md` | text knihovny, změna ocitovaná v `detail` | `manual` |
| agent bez stock předlohy | prompty beze změny, nová položka | `manual` |
| `.ts` v `harness_engineering` + relativní importy | položka typu `extension`, vazba agenta `harness_engineering` | `linked` / `converted`; `.ts`, který žádný agent nenačítá, je `not_converted` |
| stock chain podle blob id | knihovní workflow stejného jména (`simple-sdlc` vždy, ostatní s `--workflows`) | `linked` / `not_converted` |
| upravený chain, neznámý `adw_*.py` | nic | `manual` |
| ostatní stock skripty, recepty | nic | `not_converted` |
| `quality.py`: testovací blok (literály `argv`, `timeout_seconds`, čteno přes `ast`) | `test_command`, `test_timeout` | `converted`; `_placeholder` nenastaví nic |
| `quality.py`: lint, typecheck, build | nic | `not_converted` |
| jiné změny `adw_modules/` proti stock | nic | `manual` |
| `adws/`, `.claude/skills/sssf/`, `justfile`, `.env`, `.env.sample` | zůstanou | `left_in_place` |

Výsledek agenta shodný s obsahem knihovny se napojí. Jinak vznikne nová položka se jménem podle O2 (`<slot>` nebo `<slot>-<slug repa>`, případně podle `--name`). Base, remote a provider v `config.yaml` se zjistí jako u `factory init` (M8). Když repo nemá `.factory/config.yaml` a nakonfigurovaná base není repo sssf, použije se zjištěná base.

Nové blokátory:
- `sssf_roster_invalid`: roster chybí nebo není platný. Nahrazuje `sssf_not_supported`.
- `source_not_committed`: rozšířený i na necommitnuté změny a nesledované soubory v čtených částech `adws/`.

## Kde to je

- `aifactory/src/aifactory/onboard/sssf.py`: převodník (`extract_sssf`, `SssfConversion`), vyplní stejnou `Extraction` jako `extract_pre_library`.
- `aifactory/src/aifactory/onboard/merge.py`: `merge_prompt` (výsledky `stock`, `same`, `clean`, `union`, `conflict`) a `quote_change`. `git merge-file` běží v dočasném adresáři.
- `aifactory/src/aifactory/onboard/quality.py`: `parse_quality` čte `QualityCheckSpec` přes `ast`.
- `aifactory/src/aifactory/onboard/stock.py` a `onboard/sssf_stock/`: stock data zkopírovaná z `vendor/sssf/templates`, takže převod funguje i bez `vendor/`. Obsahují `stock.yaml` (purpose a blob id promptů, blob id chainů včetně dvou variant `adw_simple_sdlc`, skripty a moduly), `prompts/<agent>/{system,user}.md` a `quality.py.txt`.
- `aifactory/src/aifactory/onboard/onboard.py`: `plan_onboard` se větví na `_plan_pre_library` a `_plan_sssf`. Ty sdílejí konec plánu `_finish`. Dál obsahuje detekci base (`_detected_state`), kontrolu necommitnutých změn `adws/` (`_sssf_changes`), pole `source` v plánu a zprávu commitu `onboard <repo> (sssf)`.
- `aifactory/src/aifactory/onboard/extract.py`: `ReportRow.detail`, typ `extension` v `entries` a obecnější `_check_options` a `_library_heads`.
- `aifactory/src/aifactory/cli.py`: přepínač `--workflows`, popis převodu a výpis `detail` pod řádkem zprávy.
- `aifactory/src/aifactory/skill/skill.md` a `skill/codes.py`: postup pro sssf repo s tabulkou převodu, kód `sssf_roster_invalid` a varování `alternate_rosters`.

## Ověření

```bash
just test        # nebo: uv run pytest aifactory/tests/onboard
just typecheck
just lint
```

- `aifactory/tests/onboard/test_sssf.py` staví repa z `vendor/sssf/templates` se záplatami (`onboard_repo.py`):
  - Omnibus: claude, `quality.py` s 1800 s a `just lint`.
  - JSST: pi, rozšíření, builder a reviewer se vloženými pravidly, union.
  - amber: čistý merge.
  - upravený chain, s `--workflows` i bez něj.
  
  Zprávy se porovnávají se zlatými soubory v `aifactory/tests/onboard/golden/sssf_*.txt`. Převedená konfigurace musí projít `load_config` a validací `simple-sdlc`, bajty `adws/` se nesmí změnit a druhé spuštění vrátí `already_onboarded`. Další testy pokrývají chybějící roster, `source_not_committed`, `--workflows` na `pre_library` a base z detekce.
- `aifactory/tests/onboard/test_sssf_parts.py` testuje jednotlivé části: stock data shodná s `vendor/`, merge (stock, same, union, clean, conflict), `parse_quality` a uzávěr importů `.ts`.
- `test_onboard.py::test_state_blockers` teď u sssf repa čeká převod místo blokátoru.
- Validační testy promptů (`test_agent_prompts_handoff_dir.py`, `test_validation_template.py`) vynechávají `onboard/sssf_stock/`, protože to jsou stock prompty sssf, ne prompty HAIFA.
