# Přebuild generovaných výstupů v `factory task resolve`

Generované výstupy uložené v gitu (např. bundle frontendu) se při konfliktu
neslučují ručně, ale přestaví se.

## Konfigurace
```yaml
# .factory/config.yaml
generated:
  - path: aifactory/src/aifactory/web/static/
    command: just web-build
    timeout: 900   # volitelné, výchozí 600 s
```

## Průběh resolve
1. `rebase` nahlásí soubory s konfliktem.
2. Agent `resolve` řeší jen konflikty mimo generované výstupy; hlídač mu
   generované soubory nepovolí.
3. Code krok `rebuild` spustí `command` pro každý výstup s konfliktem
   (před každým `test`, takže i po opravě `fix`). Build smí měnit jen
   soubory uvnitř výstupu.
4. `finish_resolve` commitne vyřešené soubory i celý přestavěný výstup
   (nové soubory přidá, staré smaže); commit message končí `; rebuild <path>`.

Konflikt jen ve zdrojích funguje beze změny – `rebuild` nic nespustí.

Pro HAIFA je potřeba doplnit uvedený záznam `generated` do `.factory/config.yaml`
(chráněný soubor, mění ho operátor přes `factory config`).
