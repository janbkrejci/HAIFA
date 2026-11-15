# Ukázkové repo GIRO

Malá knihovna `textstats` (jen standardní knihovna Pythonu) se statistikami textu: slova,
počet slov a počet řádků. Vytvořil ji příkaz `giro try`, aby šlo GIRO vyzkoušet bez
vlastního repa, GitHubu a `gh`.

- Testy: `python -m unittest discover -s tests -t .` (na macOS a Linuxu `python3`).
- Backlog: `factory/backlog/`, tři tasky rostoucí velikosti. Spusťte je v dashboardu
  (`giro obs --repo .`) nebo `giro task run DEMO-S01-T01`.
- Továrna: `.factory/config.yaml` s `git_provider: local`. Běh končí lokální větví, schválení
  ji sloučí do `main`; nic se nepushuje.

Repo je vaše: smažte ho, až ho nebudete potřebovat.
