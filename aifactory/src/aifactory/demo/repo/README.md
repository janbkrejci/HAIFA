# Ukázkové repo HAIFA

Malá knihovna `textstats` (jen standardní knihovna Pythonu) se statistikami textu: slova,
počet slov a počet řádků. Vytvořil ji příkaz `factory try`, aby šlo HAIFA vyzkoušet bez
vlastního repa, GitHubu a `gh`.

- Testy: `python -m unittest discover -s tests -t .` (na macOS a Linuxu `python3`).
- Backlog: `factory/backlog/`, tři tasky rostoucí velikosti. Spusťte je v dashboardu
  (`factory obs --repo .`) nebo `factory task run DEMO-S01-T01`.
- Továrna: `.factory/config.yaml` s `git_provider: local`. Běh končí lokální větví, schválení
  ji sloučí do `main`; nic se nepushuje.

Repo je vaše: smažte ho, až ho nebudete potřebovat.
