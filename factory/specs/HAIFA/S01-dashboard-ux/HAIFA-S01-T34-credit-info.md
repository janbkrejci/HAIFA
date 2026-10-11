# HAIFA-S01-T34: Credit info

## Problém
Engineer v dashboardu nevidí, kolik mu zbývá z 5hodinových a týdenních limitů předplatného
Claude a Codex, na kterých běží agenti.

## Řešení
- `aifactory/src/aifactory/web/limits.py`:
  - `used_harnesses(repo)`: harnessy s limity (`claude`, `codex`) uvedené v
    `.factory/agents.yaml` a `.factory/workflows/*.yaml` (klíč `harness` / `coding_agent`).
  - `claude_limits()`: OAuth token Claude Code (`~/.claude/.credentials.json`, na macOS
    keychain `Claude Code-credentials`) a `GET https://api.anthropic.com/api/oauth/usage`
    (`five_hour`, `seven_day`, pole `utilization` v %).
  - `codex_limits()`: poslední `rate_limits` s oknem z logů `~/.codex/sessions/**/*.jsonl`
    (`primary`/`secondary`, `window_minutes` ≤ 1 den = 5h, jinak 1w); okno po `resets_at`
    se počítá jako nevyužité.
  - `LimitsSource`: cache na 60 s, chyba jednoho providera je v jeho `error`, endpoint nepadá.
- `aifactory/src/aifactory/web/app.py`: `GET /api/limits` →
  `{providers: [{harness, label, windows: [{id, label, used, left, resets_at}], error}]}`,
  `create_app(..., limits_source=)`.
- `aifactory/web/src/lib/limits.ts`: `useLimits()` (poll 60 s), `pct`, `windowTip`.
- `aifactory/web/src/components/LimitsBar.vue`: v topbaru vlevo od přepínače motivu; na okno
  tenký progressbar plněný zleva využitým podílem neutrální barvou (`--faint`) a volné %
  (zbývá 30 % → pruh 70 %, text „30 %“). Tooltip s detailem a časem obnovení. Pod 1180 px skrytý.
- Build do `aifactory/src/aifactory/web/static/`.

## Testy
- `aifactory/tests/web/test_web_limits.py`: harnessy z konfigurace, Claude (odpověď, bez
  přihlášení, 401), Codex (poslední okno, prošlý reset, chybějící logy), cache, endpoint.
- `aifactory/web/src/components/LimitsBar.test.ts`: pruh a volná %, chyba providera,
  helpery, načtení z `/api/limits`.
