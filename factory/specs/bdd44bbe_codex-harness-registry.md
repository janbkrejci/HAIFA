# Plán: harness Codex a výslovná volba harnessu (D13)

## Cíl

Tři adaptéry se stejným rozhraním: Claude Code, Codex a pi. Harness se u agenta zapisuje výslovně (`coding_agent: claude | codex | pi`), neodvozuje se ze jména modelu. Prototyp přidá:

- vlastní adaptér `haifa_proto/harness/codex.py`,
- registr harnessů, který za běhu zapíše adaptéry do `adw_modules.agents.INTERFACES` a rozšíří typ `coding_agent`,
- kontraktový test nad všemi třemi adaptéry s falešným procesem,
- příkaz `haifa-proto harness check`.

Mimo rozsah: interpret workflow, volba harnessu u kroku (úkol 1.4), běh ve worktree.

## Pevná omezení

- `vendor/` se **neupravuje**. Všechno se registruje nebo přepojuje za běhu z `haifa_proto`.
- Testy **nespouštějí** skutečné `codex`, `claude`, `pi` ani model. `subprocess.Popen` a `subprocess.run` se v testech vždy nahrazují falešnými.
- Zápisy (`writes:`) hlídá jen `adw_modules/permissions.py` přes git diff. Adaptér Codexu nijak neřeší `writes`: nepřidává `--add-dir`, neskládá sandbox podle `writes` a nesahá na `permissions`. Funguje stejně jako `agent_cc`, který běží s `bypassPermissions`, protože zápisy pohlídá `permissions.py`.

## Zjištěný stav (recon)

- Engine se importuje jen přes `prototype/src/haifa_proto/engine.py` (`load_engine_module(name)`, `ensure_engine_on_path()`). Totéž platí pro nový kód. mypy má `adw_modules.*` jako `ignore_missing_imports` a `follow_imports = skip`, takže typy z vendoru jsou `Any`.
- `vendor/.../adw_modules/agents.py`:
  - `INTERFACES = {"pi": agent_pi, "claude_code": agent_cc}`.
  - `interface(agent)` a `validate()` hledají `INTERFACES[agent.coding_agent]`.
  - `validate()` odmítne `harness_engineering` u jiného harnessu než `pi`. To platí automaticky i pro `codex`.
  - `execute()` volá `harness.run(request, on_event=..., on_wait=..., on_spawn=..., on_exit=...)` a `harness.ToolCallTracker()`.
  - `load_config()` staví `SSSFConfig(**raw)` přes **globální jméno** `SSSFConfig` v modulu `agents`.
- `data_types.py`: `AgentConfig.coding_agent` i `ConfigDefaults.coding_agent` mají typ `Literal["pi", "claude_code"]`. `SSSFConfig` obsahuje `agents: list[AgentConfig]` a `defaults: ConfigDefaults` (ověř přesné názvy polí v `data_types.py` ř. 379+). `AgentRequest = PiRequest` má pole `prompt, system_prompt, model, thinking, session_id, session_dir, raw_output_path, tools, extensions, cwd`. `AgentResult = PiResult` má pole `text, returncode, session_id, tokens, cost, usage: UsageBreakdown, context_tokens, context_window`. `UsageBreakdown.add_turn(usage_dict_in_pi_vocab, total_tokens)` přijímá klíče `input, output, cacheRead, cacheWrite, reasoning, cost{total,...}`.
- `agent_cc.py` je vzor pro Codex:
  - `_SessionState` je stavový soubor v `session_dir`, který si pamatuje „started“ a kumulativní součty.
  - Streamování jde přes `Popen(stdin=DEVNULL, stdout=PIPE, stderr=PIPE, text=True, bufsize=1, cwd=request.cwd, env=operator_env())`. Každý řádek se připisuje do `raw_output_path`.
  - `on_spawn`/`on_exit` dostávají pid.
  - Když návratový kód není 0 a chybí text, adaptér vyhodí `RuntimeError`.
  - Záznam `tool_call` má klíče `tool, tool_call_id, args, ok, label, result_snippet?, ended_at, duration_ms?, started_at?`.
- `agent_pi.resolve_model` volá `pi --list-models` přes `_pi_catalog()` (s `lru_cache`) a `context_window` čte `MODELS_JSON`. V testu je potřeba přes monkeypatch nahradit `agent_pi._pi_catalog` a `agent_pi.MODELS_JSON`.
- `agent_cc` zapisuje stav do `Path(request.session_dir) / f"{uuid}.state.json"`. V testu stačí `tmp_path`.
- Codex CLI na tomto stroji: `codex-cli 0.139.0`.
  - `codex exec [OPTIONS] [PROMPT]` přijímá `--json`, `-m/--model`, `-C/--cd`, `-c key=value` (hodnota se parsuje jako TOML), `-s/--sandbox`, `--dangerously-bypass-approvals-and-sandbox`, `--skip-git-repo-check`, `-o`.
  - `codex exec resume [OPTIONS] [SESSION_ID] [PROMPT]` přijímá `--json`, `-m`, `-c`, `--dangerously-bypass-approvals-and-sandbox` a `--skip-git-repo-check`. **Nepřijímá `-C` ani `-s`.** Pracovní adresář se proto u resume určuje přes `cwd=` v `Popen` a sandbox přes `-c sandbox_mode=...`.
  - Binárka zná konfigurační klíče `developer_instructions` a `model_instructions_file`.
- Existující test `tests/test_cli.py::test_subcommands_are_noops` parametrizuje `backlog/task/serve`. Nový `harness` bez podpříkazu musí vypsat nápovědu a vrátit 0, stejně jako `backlog`.
- Recepty: `just test` (`cd prototype && uv run pytest`), `just typecheck` (mypy strict), `just lint` (ruff check a ruff format --check).

## Návrh

### Názvy harnessů

`HarnessName = Literal["claude", "codex", "pi", "claude_code"]`.

- `claude`, `codex` a `pi` jsou kanonické názvy podle D13.
- `claude_code` zůstává jako alias kvůli zpětné kompatibilitě se sssf configy a s vendor kódem (`models.py`, `chain.py`, `cli.py` zapisují `claude_code`). Registr ho mapuje na stejný modul jako `claude`.
- `harness check` vypisuje jen kanonické tři.

### 1. `prototype/src/haifa_proto/harness/__init__.py` (nový): registr

```python
HARNESSES: dict[str, str] = {           # kanonické jméno -> modul adaptéru
    "claude": "adw_modules.agent_cc",
    "codex":  "haifa_proto.harness.codex",
    "pi":     "adw_modules.agent_pi",
}
ALIASES: dict[str, str] = {"claude_code": "claude"}
CLI_BINARIES: dict[str, tuple[str, str]] = {   # jméno -> (env proměnná, výchozí binárka)
    "claude": ("CLAUDE_CODE_PATH", "claude"),
    "codex":  ("CODEX_PATH", "codex"),
    "pi":     ("PI_PATH", "pi"),
}
```

Funkce:

- `canonical(name: str) -> str` přeloží alias. Neznámé jméno vyhodí `ValueError` se seznamem dostupných.
- `load(name: str) -> ModuleType` zavolá nejdřív `engine.ensure_engine_on_path()` a pak `importlib.import_module(HARNESSES[canonical(name)])`.
- `install() -> ModuleType` je idempotentní:
  1. Zavolá `config_types.install()` (bod 2).
  2. Přes `engine.load_engine_module("agents")` získá modul `agents`.
  3. Pro každé jméno z `HARNESSES` i `ALIASES` nastaví `agents.INTERFACES[name] = load(name)`. Klíč `claude_code` tedy zůstane na `agent_cc`.
  4. Vrátí modul `agents`.

  Nic v `vendor/` se nepřepisuje na disku. Mění se jen slovník v paměti.
- `REQUIRED_API = ("run", "resolve_model", "context_window", "ToolCallTracker")` a `check_interface(module) -> list[str]` vrací chybějící atributy. `install()` vyhodí `RuntimeError`, když něco chybí.

### 2. `prototype/src/haifa_proto/harness/config_types.py` (nový): rozšíření typu `coding_agent`

Robustní varianta bez sahání na `model_fields` vendorových tříd:

```python
HarnessName = Literal["claude", "codex", "pi", "claude_code"]

class HaifaAgentConfig(data_types.AgentConfig):
    coding_agent: HarnessName = "pi"

class HaifaConfigDefaults(data_types.ConfigDefaults):
    coding_agent: HarnessName = "pi"

class HaifaSSSFConfig(data_types.SSSFConfig):
    agents: list[HaifaAgentConfig] = ...      # přesně podle signatury pole v SSSFConfig
    defaults: HaifaConfigDefaults = ...       # dtto (default_factory)
```

- Třídy se vytvářejí uvnitř funkce `_build()` až po `engine.load_engine_module("data_types")`, protože vendor se musí nejdřív dostat na `sys.path`. Výsledek se uloží do cache na úrovni modulu.
- `install()` přepojí globální jména tam, kde se podle nich skutečně staví: `data_types.AgentConfig`, `data_types.ConfigDefaults`, `data_types.SSSFConfig`, `agents.SSSFConfig` a `agents.AgentConfig`. Stejně přepojí `session.SSSFConfig`, `permissions.SSSFConfig/AgentConfig` a `tracer.AgentConfig`, pokud v modulu existují (projdi `hasattr`). Tyto moduly jména používají jen v anotacích, přepojení je jen pro konzistenci.
- Podtřídy zůstávají `isinstance` původních tříd, takže vendor kód dál funguje.
- Ověření v testu: `agents.load_config(path)` na YAML s `coding_agent: codex` projde a `agents.validate(cfg, [name])` s `model: gpt-5.5` projde (prompt soubory vytvoř v `tmp_path`). Bez `install()` by `load_config` spadl na ValidationError. Test to nekontroluje, protože pořadí testů by ho rozbilo.

Poznámka: pokud má `SSSFConfig` u `agents`/`defaults` jiný default nebo jiný typ než výše, zkopíruj přesnou signaturu z `data_types.py` a změň jen typ prvku.

### 3. `prototype/src/haifa_proto/harness/codex.py` (nový): adaptér Codexu

Hlavička modulu:

```python
from haifa_proto import engine
_dt = engine.load_engine_module("data_types")
_utils = engine.load_engine_module("utils")
AgentRequest = _dt.AgentRequest; AgentResult = _dt.AgentResult
now_iso = _utils.now_iso; operator_env = _utils.operator_env
```

Konstanty (čtou se z env stejně jako v `agent_cc`):

- `CODEX_PATH = os.environ.get("CODEX_PATH", "codex")`
- `CODEX_SANDBOX = os.environ.get("CODEX_SANDBOX", "")`. Prázdná hodnota znamená `--dangerously-bypass-approvals-and-sandbox`. Jde o stejné rozhodnutí jako `bypassPermissions` v `agent_cc`: nikdo neodpovídá na schválení a zápisy hlídá `permissions.py`. Hodnota `read-only`, `workspace-write` nebo `danger-full-access` znamená, že se místo bypassu použije `-c sandbox_mode="<v>"` a `-c approval_policy="never"`. Ty fungují u `exec` i `resume`, proto `-c`, ne `-s`.
- `CODEX_SAFE_MODE = env "CODEX_SAFE_MODE" (default "1")`. Když je zapnutý, přidá `-c project_doc_max_bytes=0`, aby se do promptu nenačítal `AGENTS.md` z repa. Je to obdoba `--safe-mode` v `agent_cc`: agenta definuje jeho system prompt.
- `RESULT_SNIPPET_CHARS = ARG_VALUE_CHARS = 20_000`, `LABEL_CHARS = 80`, `PRIMARY_ARGS` jako v `agent_cc`.
- `EFFORT_MAP = {"off": "minimal", "minimal": "minimal", "low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "xhigh"}`
- `CONTEXT_WINDOWS` je malá tabulka záložních hodnot, jen pro řádek v trace před během. `DEFAULT_CONTEXT_WINDOW = 272_000`.

`resolve_model(pattern) -> tuple[str, str]` pracuje offline, stejně jako u claude:

- `openai/<id>` → `("openai", id)`.
- Holé id bez `/` → `("openai", pattern)`.
- Jiný prefix providera (`anthropic/…`, `google/…`) nebo `claude-*` / alias claude (`opus`, `sonnet`, `haiku`, `fable`) → `ValueError` se srozumitelnou hláškou.
- Prázdný řetězec → `ValueError`.
- Harness se ze jména modelu **neodvozuje**. Funkce jen ověřuje, že model dává smysl pro Codex.

`context_window(provider, model_id) -> int` vrací hodnotu z tabulky, jinak `DEFAULT_CONTEXT_WINDOW`.

`_SessionState(path)` je kopie vzoru z `agent_cc`. Ukládá:

- `thread_id`: id vlákna Codexu z `thread.started`,
- `totals`: poslední kumulativní součty usage.

Soubor je `Path(request.session_dir) / f"{_safe(request.session_id)}.codex.json"`.

Sestavení příkazu (`build_command(request, state) -> list[str]`, veřejná funkce kvůli testu):

```
společné = ["--json", "-m", model_id,
            "-c", f"model_reasoning_effort={json.dumps(effort)}",
            "-c", f"developer_instructions={json.dumps(request.system_prompt)}",
            "--skip-git-repo-check",
            *sandbox_args, *(safe_mode_args)]
první kolo:  [CODEX_PATH, "exec", *společné, "-C", request.cwd, request.prompt]
opravné kolo: [CODEX_PATH, "exec", "resume", *společné, state.thread_id, request.prompt]
```

- **Systémový prompt** jde přes `-c developer_instructions=<TOML string>`. `json.dumps(str)` dává platný TOML basic string (escapuje `"`, `\`, `\n` a řídicí znaky jako `\uXXXX`).
  - Proč ne `model_instructions_file`: nahradil by vestavěné instrukce Codexu, včetně návodu k jeho nástrojům.
  - Instrukce se posílají v každém kole, protože `-c` platí jen pro jeden proces.
  - Tento způsob popiš v docstringu.
- `-C request.cwd` jde jen u prvního kola, protože `resume` ho nezná. `Popen(cwd=request.cwd)` platí v obou případech.
- `request.tools`: Codex nemá allowlist nástrojů, proto se ignoruje. Uveď to v docstringu. `request.extensions` se ignoruje, protože `validate()` je u jiných harnessů než pi stejně odmítá.
- Prompt jde jako poslední argument v argv a stdin je `DEVNULL` (stejný důvod jako u pi/claude).

`run(request, on_event=None, on_spawn=None, on_exit=None, on_wait=None) -> AgentResult` má stejnou signaturu a pořadí keyword argumentů jako `agent_cc.run`:

1. Zavolá `resolve_model`, načte stav a sestaví příkaz. Resume se použije, jen když má stav `thread_id`.
2. Zavolá `Popen` jako `agent_cc`, pak `on_spawn(pid)`. Každý řádek stdout připíše do `raw_output_path` a přeskočí prázdné řádky a ne-JSON. Události zpracuje takto:
   - `thread.started` → `thread_id = event["thread_id"]`, zapsat do stavu **hned**. Jen takové vlákno je pak možné obnovit přes resume.
   - `item.completed` s `item.type == "agent_message"` → `result.text = item["text"]` (poslední vyhrává).
   - `turn.completed` → `usage = event["usage"]` (`input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_output_tokens`), uložit poslední.
   - `turn.failed` → `last_error = event["error"]["message"]`, `error` → `last_error = event["message"]`.
   - Každou událost předá `on_event(event)`.
3. Přečte `stderr`, zavolá `returncode = process.wait()`, pak `on_exit(pid)`.
4. Usage: Codex hlásí `usage` jako součet za vlákno (`total_token_usage`). Po `resume` proto hrozí dvojí započtení stejně jako u claude. Pokud jsou všechny položky ≥ předchozí uložené hodnoty, bere se **delta** proti `state.totals`. Pokud některá položka klesne (nový čítač), bere se hodnota tak, jak přišla. Mapování na slovník pi pro `UsageBreakdown.add_turn`:
   - `input = input_tokens - cached_input_tokens` (u OpenAI input zahrnuje cache, pi ne),
   - `cacheRead = cached_input_tokens`,
   - `cacheWrite = 0`,
   - `output = output_tokens`,
   - `reasoning = reasoning_output_tokens`,
   - `cost = {"total": 0.0}`.

   `billed = input_tokens + output_tokens` z delty. `result.tokens += billed` a `result.cost` zůstává 0.0, protože Codex náklady nehlásí a nic se nevymýšlí. `context_tokens` zůstává 0, protože Codex obsazenost okna nehlásí. `state.save(totals)`.
5. Když `returncode != 0` a chybí `result.text` → `RuntimeError(f"codex exited {rc}: {(last_error or stderr).strip()[-800:]}")`.
6. `on_wait` se nepoužívá, protože Codex čeká na rate limity uvnitř procesu. Napiš to do docstringu jako v `agent_cc`.

`ToolCallTracker.observe(event) -> dict | None` vydá jeden záznam na **dokončenou** položku nástroje ve stejném tvaru jako `agent_cc`/`agent_pi`: `tool, tool_call_id, args, ok, label, result_snippet?, ended_at, duration_ms?, started_at?`. Názvy nástrojů jsou ve slovníku pi (malá písmena), stejně jako roster.

- `item.started` → `_announce(item.id, tool, args)`. Spustí hodiny a uloží `started_at`. Vrací `None`.
- `item.completed` podle `item.type`:

  | `item.type` | `tool` | `args` | `ok` | `result_snippet` |
  |---|---|---|---|---|
  | `command_execution` | `bash` | `{"command": item.command}` | `item.status == "completed"` a `exit_code in (0, None)` | `aggregated_output` |
  | `file_change` | `edit` | `{"path": první path, "changes": item.changes}` | `status == "completed"` | `"\n".join(f"{kind} {path}")` |
  | `mcp_tool_call` | `f"{server}.{tool}"` | `item.arguments or {}` | `status == "completed"` a bez `error` | text z `result.content[*].text`, jinak `error.message` |
  | `web_search` | `web_search` | `{"query": item.query}` | `True` | — |
  | jiné (`agent_message`, `reasoning`, `todo_list`, `error`) | — vrací `None` | | | |

- `label` vzniká přes `_label(tool, args)`, kopii z `agent_cc` (seznam `args` projde přes `PRIMARY_ARGS` a nestringové hodnoty se přeskočí). Ořez přes `_clip`.
- `item.updated` se ignoruje, jen doplní `_announce`, pokud položka ještě chybí.

### 4. `prototype/src/haifa_proto/harness/check.py` (nový) a CLI

- `HarnessStatus` (dataclass): `name, binary, path: str | None, version: str | None, error: str | None`.
- `check_harness(name) -> HarnessStatus`:
  1. Binárka se vezme z env (`CLI_BINARIES`), jinak se použije výchozí jméno.
  2. `shutil.which(binary)`. Když vrátí `None`, výsledek je `path=None, error="not on PATH"`.
  3. Jinak `subprocess.run([path, "--version"], capture_output=True, text=True, timeout=15, env=operator_env())`.
  4. Verze je první neprázdný řádek stdout, jinak první neprázdný řádek stderr.
  5. O úspěchu rozhoduje **návratový kód**, ne text výstupu. Nenulový kód nebo výjimka `OSError`/`TimeoutExpired` dá `error`.
- `check_all() -> list[HarnessStatus]` projde `HARNESSES` v pořadí `claude, codex, pi`.
- CLI (`cli.py`): přidat `harness` subparser (se `set_defaults(harness_parser=...)` jako u backlog) a podpříkaz `check` s volbou `--json`.
  - Text: řádek na harness, např. `claude  /Users/.../claude  2.1.0 (Claude Code)` nebo `codex   MISSING  not on PATH`.
  - JSON: `{"ok": bool, "harnesses": [{"name", "binary", "path", "version", "error"}]}`.
  - Exit code: 0, když všechny mají `path` a `version`, jinak 1.
  - `harness` bez podpříkazu vypíše nápovědu a vrátí 0.

### 5. Testy (`prototype/tests/`)

Fixtures v `tests/fixtures/harness/` jsou ručně sestavené JSONL podle formátu příslušného CLI:

- `claude_turn.jsonl`: `system/init`, `assistant` s `tool_use` (Bash `ls`), `user` s `tool_result`, `assistant` s textem `{"status":"success"}` a `usage`, `result` s `modelUsage` (`inputTokens`…, `contextWindow`) a `total_cost_usd`.
- `pi_turn.jsonl`: `message_end` (assistant s blokem `toolCall` bash), `tool_execution_start`, `tool_execution_end` (`result.content` text, `isError` false), `message_end` (assistant s textem, `usage` s `input/output/cacheRead/cacheWrite/totalTokens/cost.total`).
- `codex_turn.jsonl`: `thread.started {thread_id: "019a-…"}`, `turn.started`, `item.started`/`item.completed` pro `command_execution` (`ls`, `exit_code 0`), `item.completed` `file_change`, `item.completed` `agent_message` s textem `not json`, `turn.completed` s usage (např. `input 1200`, `cached 200`, `output 300`, `reasoning 100`).
- `codex_resume.jsonl`: opravné kolo. `thread.started` se stejným id (Codex ho při resume znovu hlásí, adaptér to snese), `item.completed` `agent_message` `{"status":"success"}`, `turn.completed` s kumulativní usage (`input 2000`, `cached 500`, `output 450`, `reasoning 150`).

`tests/harness_fakes.py` (helper, ne test):

- `FakePopen(cmd, **kw)` zaznamená `cmd`, `cwd` a `env` do sdíleného seznamu `calls`. Má `stdout = io.StringIO(fixture_text)`, `stderr = io.StringIO(stderr_text)`, `pid = 4242` a `wait() -> returncode`.
- Továrna `fake_popen(monkeypatch, module, fixtures: list[str], returncode=0)` postupně vrací procesy s danými fixtures a nahradí `module.subprocess.Popen` přes `monkeypatch.setattr`.
- `normalize(records)` z každého záznamu vyhodí `started_at`, `ended_at` a `duration_ms`.

`tests/test_harness_contract.py` (parametrizovaný přes `claude`, `codex`, `pi`):

- Fixture `installed` volá `harness.install()`.
- U pi se přes monkeypatch nastaví `agent_pi._pi_catalog` na `lambda: [("openai", "gpt-5.5", 272000)]` a `agent_pi.MODELS_JSON` na neexistující soubor v `tmp_path`.
- Pro každý harness: modul z `agents.INTERFACES[name]` má `run`, `resolve_model`, `context_window` a `ToolCallTracker`. Signatura `run` obsahuje parametry `request, on_event, on_spawn, on_exit, on_wait` (`inspect.signature`).
- Pro každý harness se sestaví `AgentRequest` (`session_dir`/`raw_output_path` v `tmp_path`, `cwd=str(tmp_path / "repo")`). Test spustí `run` s `on_event`, který krmí `ToolCallTracker().observe`, a sbírá záznamy. Ověří:
  - `AgentResult.text`, `tokens`, `cost` a `usage` (vybraná pole) podle tabulky očekávání v testu,
  - `normalize(records)` == očekávaný seznam, stejná sada klíčů u všech tří harnessů (`{"tool", "tool_call_id", "args", "ok", "label", ...}`),
  - `on_spawn` a `on_exit` dostaly `4242`,
  - `raw_output_path` obsahuje všechny řádky fixture,
  - Popen dostal `cwd == request.cwd` a `stdin == DEVNULL`.
- Codex, první kolo: `cmd[:2] == [codex, "exec"]`, obsahuje `--json`, `-m gpt-5.5`, `-C <cwd>` a `developer_instructions=` s JSON-escapovaným system promptem (použij prompt s uvozovkami a novým řádkem). Neobsahuje `resume`. Poslední argument je prompt. Stavový soubor obsahuje `thread_id`.
- Codex, opravné kolo: druhé `run` se stejným `session_id`, `session_dir` a `codex_resume.jsonl`. Ověří:
  - `cmd[:4] == [codex, "exec", "resume", ...]` s thread_id před promptem, bez `-C`, `cwd` v Popen stále `request.cwd`,
  - `text == '{"status":"success"}'`,
  - tokeny druhého kola jsou **delta**: `(2000 - 1200) + (450 - 300) = 950`, `usage.cache_read_tokens == 300`,
  - `cost == 0.0`.
- Codex s chybou: `returncode=1`, fixture jen s `turn.failed` → `RuntimeError` s textem chyby.
- Codex `resolve_model`: `gpt-5.5` → `("openai", "gpt-5.5")`, `openai/gpt-5.5` → totéž, `anthropic/claude-opus-5`, `opus` a `google/gemini-x` → `ValueError`.
- Codex `CODEX_SANDBOX`: monkeypatch konstanty na `workspace-write` → příkaz obsahuje `-c sandbox_mode="workspace-write"` a neobsahuje `--dangerously-bypass-approvals-and-sandbox`. Výchozí stav obsahuje bypass. Příkaz nikdy neobsahuje `--add-dir`.

`tests/test_harness_registry.py`:

- `install()` je idempotentní. `INTERFACES` obsahuje `claude`, `codex`, `pi` a `claude_code`, přičemž `claude_code is claude`.
- `canonical("claude_code") == "claude"`, neznámé jméno vyhodí `ValueError`.
- Moduly pro `claude` a `pi` pocházejí z `vendor/.../adw_modules` (kontrola cesty jako v `test_engine_import.py`).
- Config: v `tmp_path` napiš `sssf.config.yaml` s agentem `coding_agent: codex`, `model: gpt-5.5` a existujícími prompt soubory. Pak `agents.load_config(str(path))`, `agents.validate(cfg, ["a"])` a `agents.interface(agent) is codex_module`. Druhý agent s `coding_agent: codex` a `harness_engineering: ["x"]` → `validate` vyhodí `SystemExit`.

`tests/test_cli_harness.py`:

- Přes monkeypatch nahraď `shutil.which` a `subprocess.run` v modulu `haifa_proto.harness.check`. Například codex chybí, claude vrací `2.1.0 (Claude Code)` a pi vrací verzi na stderr.
- `main(["harness", "check"])` vrátí 1, výstup obsahuje všechna tři jména, verze a `not on PATH`.
- Varianta `--json` má správnou strukturu. Když jsou všechny tři přítomné, návratový kód je 0.
- `main(["harness"]) == 0`. V `tests/test_cli.py` přidej `"harness"` do seznamu v `test_help_lists_subcommands` (a případně do noops parametrizace).

## Postup (pořadí)

1. `harness/config_types.py`, pak `harness/__init__.py` (registr a `install`).
2. `harness/codex.py`.
3. `harness/check.py` a napojení v `cli.py`.
4. Fixtures, `harness_fakes.py` a testy.
5. `just test`, `just typecheck` a `just lint`. Opravovat, dokud všechny tři neskončí s exit status 0. Kvůli mypy strict: vendorové typy jsou `Any`, JSON události typuj jako `dict[str, Any]` a u vracených hodnot přidej explicitní anotace.

## Ověření

- `just test`, `just typecheck` a `just lint` skončí s exit status 0.
- `git status --porcelain vendor/` je prázdné.
- `just proto harness check` na tomto stroji vypíše `claude`, `codex` (`codex-cli 0.139.0`) a `pi` s cestou a verzí.
- Volitelně, ručně a mimo testy: jedno skutečné kolo `codex exec --json` a `codex exec resume` potvrdí, že `turn.completed.usage` je kumulativní za vlákno, a tedy že delta je správně. Pokud by hodnota byla za kolo, stačí v `run` vypnout odečítání. Výsledek zapiš do docstringu.

## Soubory

Nové:

- `prototype/src/haifa_proto/harness/__init__.py`
- `prototype/src/haifa_proto/harness/config_types.py`
- `prototype/src/haifa_proto/harness/codex.py`
- `prototype/src/haifa_proto/harness/check.py`
- `prototype/tests/harness_fakes.py`
- `prototype/tests/test_harness_contract.py`
- `prototype/tests/test_harness_registry.py`
- `prototype/tests/test_cli_harness.py`
- `prototype/tests/fixtures/harness/{claude_turn,pi_turn,codex_turn,codex_resume}.jsonl`

Upravené:

- `prototype/src/haifa_proto/cli.py`: podpříkaz `harness check`
- `prototype/tests/test_cli.py`: `harness` v nápovědě

Neupravovat: cokoli ve `vendor/`.
