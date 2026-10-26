# Sdílení knihovny přes fork — kompatibilita s gh 2.102.0

Pro účet bez práva zápisu HAIFA volá `gh repo fork OWNER/REPO --clone=false`.
Přepínač `--remote=false` byl odstraněn: gh jej při explicitním argumentu
repozitáře odmítá i s hodnotou false. Tento tvar příkazu nepřidává místní remote.

Regresní test `test_reader_sends_a_pull_request_from_a_fork` kontroluje, že
žádný argument forku nezačíná `--remote`. Nad lokálními bare repozitáři a fake gh
ověřuje také push větve do forku, správný head PR a nezměněnou hlavní větev knihovny.

## Kontrola ostatních volání gh

Prohledány Python zdroje v `aifactory/src`. Výkonná volání jsou v
`library/share.py`, `providers/github.py` a `check/machine_rules.py`.
Jejich přepínače byly porovnány s lokální nápovědou gh 2.102.0:

- `repo view`, `repo fork` a `api user` pro výběr cíle sdílení;
- `pr create`, `list`, `view`, `checks`, `merge`, `edit` a `comment`;
- `run view --job --log-failed` a `api` pro diagnostiku a schvalování;
- `auth token --user` a `auth status --hostname`.

Další nepodporované kombinace přepínačů nebyly nalezeny. Kontrola nespouštěla
zápisy na GitHub; integrace používá fake gh a místní Git repozitáře.
