# Harness Codex a registr harnessů (D13)

## Co se změnilo a proč

Prototyp teď zná tři coding agenty (harnessy) se stejným rozhraním: `claude`, `codex`, `pi`. Harness se u agenta píše výslovně (`coding_agent: claude | codex | pi`) a nikdy se neodvozuje ze jména modelu. `vendor/` zůstává beze změny, protože vše se registruje za běhu.

- **Adaptér Codexu** (`harness/codex.py`) má stejné rozhraní jako vendorovaný `agent_cc`: `run(request, on_event, on_spawn, on_exit, on_wait) -> AgentResult`, `resolve_model`, `context_window` a `ToolCallTracker`.
- **Registr** (`harness/__init__.py`) mapuje názvy na moduly: `claude` → `adw_modules.agent_cc`, `codex` → `haifa_proto.harness.codex`, `pi` → `adw_modules.agent_pi`. Alias `claude_code` → `claude` zůstává kvůli starším configům. Funkce `install()` ověří rozhraní každého modulu a zapíše ho do `agents.INTERFACES`. Je idempotentní.
- **Rozšíření typů configu** (`harness/config_types.py`): vendor typuje `coding_agent` jako `Literal["pi", "claude_code"]`. Prototyp proto vytvoří podtřídy `AgentConfig`, `ConfigDefaults` a `SSSFConfig` s literálem `claude | codex | pi | claude_code` a za běhu je dosadí do `adw_modules.{data_types, agents, permissions, tracer, session, cli}`. Podtřídy zůstávají `isinstance` originálů.
- **`haifa-proto harness check`** (`harness/check.py`, `cli.py`) vypíše pro každý harness cestu k binárce a první řádek výstupu `--version`. Když binárka na PATH chybí, vypíše `MISSING`. Binárku lze přepsat proměnnými `CLAUDE_CODE_PATH`, `CODEX_PATH` a `PI_PATH`. Přepínač `--json` vrací strojově čitelný výstup. Exit kód je 1, pokud některý harness není v pořádku.

## Jak adaptér Codexu řídí CLI

- **První kolo:** `codex exec --json -m <model> -C <cwd> ... -- <prompt>`.
- **Opravné kolo** (neplatný JSON, porušené gates): `codex exec resume ... -- <thread_id> <prompt>`. `thread_id` přichází v události `thread.started` a hned se ukládá do `<session_dir>/<session_id>.codex.json`. `resume` nepřijímá `-C`, takže obě kola běží s `Popen(cwd=request.cwd)`.
- **Systémový prompt** se předává jako `-c developer_instructions=<JSON/TOML řetězec>` v každém kole. Nepředává se jako `model_instructions_file`, protože ten by nahradil vestavěné instrukce Codexu.
- **Úroveň přemýšlení:** `thinking` se mapuje na `model_reasoning_effort` (`off` → `minimal`, `max` → `xhigh`).
- **`CODEX_SAFE_MODE`** (výchozí zapnuto) přidává `-c project_doc_max_bytes=0`, takže repozitářový `AGENTS.md` se ignoruje.
- **Oprávnění:** výchozí je `--dangerously-bypass-approvals-and-sandbox`. Proměnná `CODEX_SANDBOX=<mode>` ho nahradí za `-c sandbox_mode=... -c approval_policy="never"`. Adaptér zápisy nepovoluje ani neomezuje, `writes:` dál hlídá `permissions.py` podle git diffu.
- **`resolve_model`** přijímá `gpt-5.5` nebo `openai/gpt-5.5`. Modely Claude, aliasy (`opus` …) a jiné providery odmítá.
- **`context_window`** bere hodnotu z pevné tabulky (výchozí 272 000).

**Výstup `run`:**

- `text` je poslední `agent_message`.
- Tokeny se berou z `turn.completed.usage`. Hodnota se chápe jako kumulativní součet za thread, takže resume kolo účtuje jen rozdíl. Pokud některý čítač klesne, bere se hodnota tak, jak přišla.
- Náklad zůstává `0.0`, protože Codex náklady nehlásí.
- Nenulový exit bez textu vyhodí `RuntimeError` se zprávou z `turn.failed`/`error` nebo ze stderr.
- `request.tools` i `request.extensions` se ignorují.

**`ToolCallTracker`** skládá dvojice `item.started`/`item.completed` do jednoho záznamu `tool_call`. Záznam má tvar `tool, tool_call_id, args, ok, label, result_snippet, started_at, ended_at, duration_ms`. Převod položek:

| Položka Codexu | `tool` |
| --- | --- |
| `command_execution` | `bash` |
| `file_change` | `edit` |
| `mcp_tool_call` | `<server>.<tool>` |
| `web_search` | `web_search` |

## Soubory

- `prototype/src/haifa_proto/harness/__init__.py`: registr, `canonical`, `load`, `check_interface`, `install`
- `prototype/src/haifa_proto/harness/codex.py`: adaptér Codexu
- `prototype/src/haifa_proto/harness/config_types.py`: rozšíření `coding_agent`
- `prototype/src/haifa_proto/harness/check.py` a `prototype/src/haifa_proto/cli.py`: `harness check`
- Testy:
  - `prototype/tests/test_harness_contract.py`: kontraktový test nad všemi třemi adaptéry
  - `prototype/tests/test_harness_registry.py`
  - `prototype/tests/test_cli_harness.py`
  - `prototype/tests/test_cli.py`: přidán `harness`
- Falešný `Popen`: `prototype/tests/harness_fakes.py`
- Nahrané JSONL výstupy: `prototype/tests/fixtures/harness/*.jsonl`
- Specifikace: `specs/bdd44bbe_codex-harness-registry.md`

## Použití a ověření

```sh
cd prototype
uv run haifa-proto harness check          # tabulka harnessů
uv run haifa-proto harness check --json
uv run pytest tests/test_harness_contract.py tests/test_harness_registry.py tests/test_cli_harness.py
```

Testy nespouštějí skutečné CLI. `subprocess.Popen` nahrazuje `FakeSpawner`, který přehrává nahrané JSONL výstupy.

**Kontraktový test ověřuje pro každý harness:**

- `text`, tokeny, náklad a `usage`
- normalizované záznamy `tool_call`
- `on_spawn`/`on_exit`
- zápis surového výstupu
- `cwd` a `stdin=DEVNULL`

**U Codexu navíc ověřuje:**

- argv prvního kola
- opravné kolo přes `exec resume` do stejného threadu s delta účtováním tokenů
- reset čítačů
- selhané kolo
- `resolve_model`
- přepínání sandboxu

**Registr config ověřuje:**

- `coding_agent: codex` projde přes `agents.load_config`/`validate` a `agents.interface()` vrátí modul `codex`
- `harness_engineering` u Codexu vendorová validace odmítne

Pro použití v kódu nejprve zavolejte `haifa_proto.harness.install()` a teprve potom `agents.load_config`.
