Přenes rozhraní `GitProvider` a providery `github` (přes `gh`) a `local` do `aifactory` a doplň stav mergeability.

Where: `aifactory/src/aifactory/providers/`, `aifactory/tests/`. Zdroj: `prototype/src/haifa_proto/providers/`, `gitops.py`.

Done means:
- Rozhraní: vytvořit PR, stav PR (`open`, `merged`, `closed`), mergeability (`mergeable`, `conflict`, `unknown`), merge se strategií z konfigurace (výchozí squash, D9), komentář.
- Když hosting vrátí mergeability `unknown`, provider dotaz opakuje s omezeným počtem pokusů. Konflikt vrací chybu `conflict`, ne `merge_failed`.
- Provider se vybírá v `.factory/config.yaml`.
- Testy: `local` proti dočasnému bare repu, `github` proti falešnému `gh` včetně odpovědi `unknown`, pak `conflict`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: Azure DevOps (2.11), tok approve a return (2.12).

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají síť.
