# Založení chybějícího backlogu

Při načítání backlogu (`factory backlog list/check`, zápisy úloh, dashboard) HAIFA
chybějící složku backlogu bez wildcardu (např. `backlog/`) tiše vytvoří a pracuje
s prázdným backlogem, místo aby hlásila `missing_backlog_dir`.

- Wildcardový vzor (`moduly/*/backlog`), který nic nenajde, se hlásí dál.
- `factory check` kontroluje backlog commitnutý v base a nic nevytváří — varování
  `backlog_missing` zůstává.
- API: `load_backlog(root, settings, create_missing=False)` zachová staré chování.
