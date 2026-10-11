# Harness adaptéry claude / codex / pi, registr a kontraktové testy

**adw_id:** `751a0ea3` · **base:** `cb32bd5` · spec: `specs/751a0ea3_harness-adapters-contract.md`

## Co se změnilo a proč

V `aifactory` přibyl balíček `aifactory.harness`. Každý HAIFA agent v něm má harness zapsaný výslovně
(`harness: claude | codex | pi`, rozhodnutí D13) a harness se nikdy neodvozuje z jména modelu.
Codex je nový adaptér. Claude a pi registr neportuje znovu: ukazuje na existující
`aifactory.engine.agent_cc` a `aifactory.engine.agent_pi`, které tato změna neupravuje.

- **Registr** (`harness/__init__.py`): `HARNESSES` mapuje jméno harnessu na modul adaptéru a alias `claude_code` vede na `claude`.
  `canonical()` / `load()` převádějí jméno na modul, `check_interface()` vrací, které části sdíleného API
  (`run`, `resolve_model`, `context_window`, `ToolCallTracker`) modulu chybí.
  `install()` zaregistruje všechny harnessy do `aifactory.engine.agents.INTERFACES`. Je idempotentní a klíče, které už
  existují, nepřepisuje. Vynucení `writes:` zůstává v `engine/permissions.py` (kontroluje git diff), adaptér ho neřeší.
- **Codex adaptér** (`harness/codex.py`): spouští `codex exec --json` a čte JSONL po řádcích. Zachovává stejný
  streamovací kontrakt jako `agent_cc` a `agent_pi`.
  - System prompt se předává jako `-c developer_instructions=…`.
  - První kolo je `codex exec … -C <cwd>`. Opravné kolo je `codex exec resume … -- <thread_id> <prompt>`. Thread id se
    bere z události `thread.started` a hned se uloží do `<session_dir>/<session_id>.codex.json`.
  - Proces vždy běží s `Popen(cwd=request.cwd)`.
  - Sandbox: výchozí volba je `--dangerously-bypass-approvals-and-sandbox`. Proměnná `CODEX_SANDBOX` ji nahradí
    přes `-c sandbox_mode=…`.
  - Thinking se mapuje na `model_reasoning_effort` (`EFFORT_MAP`).
  - Usage se u resume účtuje jako rozdíl proti uloženému kumulativnímu stavu. Cost zůstává 0.0.
  - `resolve_model` přijme `gpt-5.5` i `openai/gpt-5.5` a odmítne modely Claude.
  - Pokud je nenulový exit a chybí text, adaptér vyhodí `RuntimeError`.
- **Konfigurace** (`harness/config.py`):
  - `load_config()` / `normalize_raw()` přijímají klíč `harness`, pro kompatibilitu se sssf i `coding_agent`.
    Oba klíče se normalizují do `coding_agent`.
  - Harness se může zdědit z `defaults`.
  - Když harness chybí, je neznámý nebo si `harness` a `coding_agent` odporují, vznikne `HarnessConfigError`,
    který vypíše všechny problémy. Výchozí `"pi"` z enginu se nepoužije.
  - Typy `AgentConfig` / `ConfigDefaults` / `SSSFConfig` jsou podtřídy typů z enginu a rozšiřují `Literal` na `claude|codex|pi`.
  - `validate()` nejdřív zavolá `install()` a pak `agents.validate`.
- **Přepis u kroku** (`harness/override.py`):
  - `StepOverride(harness, model, thinking)` popisuje přepis. `effective_agent()` změní jen pole, která přepis
    uvádí, takže samotná změna modelu harness nemění. Mimo pi se vyprázdní `harness_engineering`.
  - `check_override()` ověří thinking level a to, že harness daný model umí.
  - Context manager `step_override(cfg, agent_name, override)` agenta v `cfg.agents` na dobu kroku vymění a na konci
    ho vždycky vrátí zpět.
  - Diff ukazuje jen toto API. Napojení na interpret workflow v diffu není.
- **CLI** (`cli.py`): přibyl příkaz `factory harness check [--json] [--config PATH]`.
  - Pro každý harness najde binárku (proměnné `CLAUDE_CODE_PATH` / `CODEX_PATH` / `PI_PATH`, jinak podle jména), zavolá
    `--version` a vypíše cestu, verzi a agenty, kteří harness používají.
  - S `--config` kontroluje jen harnessy, které roster opravdu používá.
  - Návratové kódy: 0 = vše OK, 1 = něco chybí, 2 = neplatná konfigurace.
  - `factory harness` bez podpříkazu vypíše nápovědu.
  - Logika je v `harness/check.py` (`HarnessStatus`, `check_harness`, `check_all`).

## Testy (`aifactory/tests/harness/`)

Testy nevolají skutečné CLI ani model. Soubor `harness_fakes.py` nahrazuje `subprocess.Popen` třídami
`FakePopen`/`FakeSpawner`, které přehrávají JSONL z `fixtures/` (`claude_turn`, `codex_turn`, `codex_resume`,
`codex_failed`, `pi_turn`), a podvrhuje katalog modelů pro pi.

- `test_harness_contract.py` je parametrizovaný přes všechny tři harnessy a ověřuje:
  - sdílené rozhraní;
  - že nahrané kolo dá očekávaný `AgentResult`;
  - **stejný tvar envelope** v `envelope.json` i v tabulce `envelopes`;
  - že **opravné kolo obnoví tutéž session**: claude `--session-id` → `--resume`, Codex `exec` → `exec resume <thread_id>` bez `-C`;
  - **zápis událostí do trace** (`agent_start` < `tool_call` < `agent_end`, `handoff`);
  - že **cwd je adresář volajícího** (`Popen` kwarg `cwd`, u Codexu i `-C`);
  - Codex-specifické věci: tvar příkazu, reset čítačů, selhané kolo, `resolve_model`, sandbox.
- `test_harness_registry.py`: `install`, `canonical`, `check_interface` a to, že se harness neodvozuje z modelu.
- `test_harness_config.py`: výslovný harness, dědění, alias, chybějící harness, konflikt, `harness_engineering` jen pro pi.
- `test_harness_override.py`: sémantika `StepOverride` a obnova agenta po kroku.
- `test_harness_check_cli.py`: `harness check` s podvrženými `shutil.which` a `subprocess.run`.
- `tests/test_smoke.py`: `harness` se už nepočítá mezi neimplementované příkazy a `main(["harness"])` vrací 0.

## Jak ověřit

```bash
just test tests/harness      # nebo celé: just test
just typecheck
just lint
cd aifactory && uv run factory harness check            # všechny tři CLI
cd aifactory && uv run factory harness check --json --config <roster.yaml>
```
