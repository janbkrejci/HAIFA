# HAIFA-S02-T04: Odolnější auto merge PR

## Příčina

GitHub počítá mergeovatelnost asynchronně. Předběžná kontrola auto merge používá
`GitHubProvider.status()`, který dosud opakoval dotaz nejvýše pětkrát s dvousekundovou
pauzou (osm sekund čekání). Pokud odpověď zůstala `UNKNOWN`, auto merge skončil
s `mergeability_unknown`, ještě před delším čekáním v `merge()`.

## Změna

- Výchozí limit `status()` je 30 dotazů s dvousekundovou pauzou mezi dotazy.
  Jeden blok obsahuje nejvýše 58 sekund pauz plus dobu odpovědí upstreamu.
- Auto merge při otevřeném PR se stavem `UNKNOWN` po dvousekundové pauze spustí
  další blok. Opakuje automaticky bez celkového limitu, dokud není mergeovatelnost
  známá nebo PR přestane být otevřený. Stejný postup platí po auto resolve.
- `MERGEABLE` umožní pokračovat přes stávající kontrolu checks a schválení.
- `CONFLICTING`, zavřený nebo již mergovaný PR ukončí čekání okamžitě.
- Trvalé `UNKNOWN` zůstává čekáním, nikoli konfliktem nebo konečnou chybou.
  Při chybě poskytovatele skončí auto merge s `status_unavailable`.
  Běžné čtení stavu mimo auto merge nadále používá omezený počet dotazů.
- Existující ochrany review, checks, shody head commitu a opakování merge zůstávají.

## Ověření

Regresní testy s falešným `gh` ověřují automatický merge, konflikt i červené checks
po více než dvou celých blocích dotazů, ukončení při chybě upstreamu a ukončení při
zavření či merge PR po vyčerpání prvního bloku. Běžné čtení stavu má nadále test
omezeného čekání. Testy nevolají síť ani model a nahrazují skutečné čekání záznamem pauz.
