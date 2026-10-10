# Limity předplatného v topbaru

Topbar dashboardu ukazuje vpravo nenápadně, kolik zbývá z limitů předplatného Claude a Codex.

- Zobrazí se jen harnessy, které repo používá (`harness` v `.factory/agents.yaml` nebo ve
  workflow). `pi` limity předplatného nemá.
- Pro každý harness dvě okna: **5h** a **1w**. Pruh se plní zleva využitým podílem neutrální
  barvou, číslo vedle ukazuje volná procenta (zbývá 30 % → pruh na 70 %, text „30 %“).
  Tooltip uvádí využití, volný podíl a čas obnovení okna.
- Claude: čte se OAuth usage endpoint předplatného, ke kterému je přihlášený Claude Code
  (token z `~/.claude/.credentials.json` nebo z macOS keychainu). Vypršelé přihlášení se
  ukáže jako „–“ s vysvětlením v tooltipu; přihlaste se znovu v `claude`.
- Codex: použijí se poslední limity, které codex CLI zapsal do `~/.codex/sessions`
  (`CODEX_HOME`). Okno, jehož obnovení už proběhlo, se ukáže jako volné.
- API: `GET /api/limits`; server výsledek drží 60 s, frontend se ptá jednou za minutu.
- Na šířce pod 1180 px se limity skryjí.
