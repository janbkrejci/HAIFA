# T49: Výsledek task retry v JSON

PR doplňuje regresní testy k T48. Produkční implementace již posuzuje aktuální
stav pokusu společně pro `task run` a `task retry`; nebyla změněna.

Test automatického mergování nyní ověřuje úspěšnou JSON obálku a stav `succeeded`
pro retry bez volby fáze i s `--from plan`. V obou variantách ověřuje také merge
a pokračování dalším úkolem. Nový test opakovaně odmítnutého review ověřuje
exit 1, `run_failed` a `accept_not_met` pro stejný běh.

Ověření se omezuje na tyto regresní scénáře, lint a typy změněných testů.
V prostředí bez `bash` lze místo receptu `just pytest` použít z adresáře
`aifactory` přímo `uv run pytest` se stejnými cestami testů.
