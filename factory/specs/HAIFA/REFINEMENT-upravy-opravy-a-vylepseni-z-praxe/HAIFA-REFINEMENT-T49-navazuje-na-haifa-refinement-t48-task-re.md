# T49: Regresní pokrytí výsledku task retry

T48 skončila bez změn, protože `task run` a `task retry` již používají společné
`_chain_output` a `_emit_runs`. Pro navazující PR doplníme chybějící přímé
ověření JSON obálky, bez změny produkčního chování.

- Úspěšný retry bez `--from` i s `--from plan` vrátí exit 0, `ok: true`,
  `error: null` a `data.run.state: succeeded`, i když se PR automaticky mergne
  a řetězec pokračuje dalším úkolem.
- Retry znovu odmítnutý review vrátí exit 1, `ok: false`, `run_failed`
  a stav `failed` s důvodem `accept_not_met`.
- Testy používají lokální Git a naprogramované agenty, bez živých modelů a služeb.
