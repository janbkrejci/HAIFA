# Spec: Backend AI průvodce, read-only konverzace nad všemi repy

## Cíl

Uživatel se z dashboardu ptá na registrovaná repa, tasky, běhy, PR, konfiguraci
a knihovnu. Odpověď vzniká z dat, která agent průvodce přečte, ne z obecné nápovědy.
Tento task dodává backend: API, běh agenta a prompt. Panel řeší GUIDE-S02-T02,
navrhování akcí GUIDE-S02-T03.

## Návrh

- `web/assistant.py`: `AssistantManager` drží vlákna v
  `$HAIFA_HOME/assistant/threads/<id>/` (`thread.json`, `sessions/`, `work/`, `turns/NNN/`).
  Nejvýš dvě odpovědi naráz, ve vlákně jedna.
- Harness, model a thinking se vyberou při založení vlákna:
  `harness_settings.effective_override` (nastavení počítače z dashboardu), jinak výchozí
  hodnoty knihovního agenta `guide`. Vlákno volbu drží, takže každá zpráva pokračuje
  ve stejné session (`session_id` + `session_dir`; adaptéry z nich dělají
  `claude --resume`, `codex exec resume`, pi `--session-id`). Ztracenou session
  nahradí nová a kontext se pošle znovu.
- Pracovní adresář agenta je `work/` mimo všechna repa: prázdný git repozitář
  se skriptem `guide`, který volá `aifactory.web.assistant_gate`.
- `web/assistant_gate.py` je jediná cesta k datům:
  - `guide repos`,
  - `guide factory REPO PŘÍKAZ...` jen pro `task list/show/runs`, `backlog list/check`,
    `check`, `config show`, `library list/show`, `workflow show` (ten odpovídá brána
    sama, YAML workflow repa nebo balíčku). Vždy s `--json`, `cwd` je repo podle id.
    `--repo` a argument s `.env` se odmítnou,
  - `guide sql REPO "SELECT ..."` nad trace DB: `mode=ro`, `PRAGMA query_only`
    a authorizer, který povolí jen čtení. Sdílený databázový server se nedotazuje.
- Vynucení read-only podle harnessu (`AgentRequest.allowed_commands`, engine
  `aifactory 3.5`): claude běží s `--permission-mode dontAsk`, `--tools Bash`
  a `--allowedTools Bash(./guide) Bash(./guide *)`. Codex běží v sandboxu
  `read-only`. Pro pi platí jen ochrana zápisu níže.
- Ochrana zápisu: před odpovědí a po ní kontroluje `run.guard.TaskWriteGuard`
  (s `writes: []`) hlavní checkout každého registrovaného repa a pracovní adresář.
  Zápis se vrátí a odpověď skončí chybou `writes_violation`.
- Kontext první zprávy session tvoří `factory --skill`, kapitoly příručky
  a seznam registrovaných rep. Systémový prompt je `system.md` knihovního agenta
  `guide` (HEAD knihovny, jinak semínko `seed/agents/guide/`).
- Tajemství: hodnoty z `.env*` registrovaných rep a HAIFA home a z proměnných
  prostředí s názvem typu TOKEN/SECRET/KEY/PASSWORD se nahradí `[redacted]` všude,
  kde jdou k agentovi: v promptech, výstupu brány a textu odpovědi.
- Kontext obrazovky: zpráva `{text, screen?: {repo, task, run}}`, krátké jednořádkové
  řetězce. V promptu je to sekce „Screen the user is looking at“.

## API (jen dashboard pro více rep)

- `GET /api/assistant/threads`, `POST /api/assistant/threads` (`{title?}`, 201)
- `GET /api/assistant/threads/{id}`
- `POST /api/assistant/threads/{id}/messages` (202; 409 `busy`)
- `GET /api/assistant/threads/{id}/stream?after=SEQ`: SSE `start`, `text`, `tool`,
  `done`/`error`, `idle`

Zápisy procházejí stávající ochranou `WriteGuardMiddleware` a `StaleCodeMiddleware`.

## Testy

`tests/web/test_web_assistant.py` s fake harnessem ověřuje pokračování session, odmítnutí
příkazů mimo allowlist, read-only SQL, vrácení zápisu do repa, nepřítomnost tajemství
a kontext obrazovky v promptu. Argv claude a codex pro read-only agenta testují
`tests/harness/`.
