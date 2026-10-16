# Řetěz provede bezpečnou akci sám

Když v auto-continue řetězu běh selže, factory se podívá na druh selhání a tam, kde je
oprava bezpečná, ji udělá sama:

| Druh selhání | Co factory udělá |
|---|---|
| `quota` (vyčerpaná kvóta) | jednou pokračuje na záložním harnessu (`fallback` v `local.yaml` nebo `agents.yaml`) |
| `process_gone` (proces běhu skončil) | jednou běh zopakuje |
| `nothing_to_do` s důvodem agenta | označí task jako hotový bez změn a řetěz jde dál |
| ostatní | nic, řetěz se zastaví a selhání čeká na tebe |

Každý běh se opravuje nejvýš jednou. Když oprava nepomůže, řetěz se zastaví jako dřív.

## Kde to uvidíš

- Na **Přehledu** má karta repozitáře sekci **Factory zasáhla sama**, například
  „Factory pokračovala na Claude Code po vyčerpání kvóty Codexu“. Řádek vede na běh.
- `factory task run ID --auto --json`: `data.chain.events`.
- V trace DB: `task_chains.events`.

## Jak to vypnout

Nastavení `auto_heal` se dědí jako `auto_continue` (projekt → step → task) a je
výchozí zapnuté. Vypneš ho v `index.md` projektu nebo stepu, případně v tasku:

```yaml
auto_heal: false
```

nebo `factory backlog edit M01-S01 --auto-heal off`. S vypnutým `auto_heal` factory
nepřepne harness ani u jednotlivého běhu a řetěz se při každém selhání zastaví.
