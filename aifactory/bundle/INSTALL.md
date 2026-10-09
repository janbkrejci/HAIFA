# Instalace HAIFA @VERSION@

HAIFA (Helios AI Factory) je lokální řídicí panel a CLI `factory` pro řízení agentních úkolů v repu. Bundle obsahuje vše potřebné k instalaci, přístup k repu HAIFA nepotřebuješ.

## Předpoklady

- macOS nebo Linux (Windows jen přes WSL) a `bash`.
- [uv](https://docs.astral.sh/uv/) na PATH. Instalace: `curl -LsSf https://astral.sh/uv/install.sh | sh` nebo `brew install uv`.
- `git` a CLI agentů, které budeš používat (například `claude`). Co chybí, ukáže `factory check`.

## Instalace

Rozbal bundle a spusť instalační skript:

```bash
unzip haifa-@VERSION@.zip
cd haifa-@VERSION@
./install.sh
```

Skript ověří součty v `SHA256SUMS` a nainstaluje nástroj `factory` přes `uv tool install` s verzemi závislostí z `constraints.txt`.

## Ověření

```bash
factory check
```

Příkaz zkontroluje prerekvizity a přihlášení. Pokud `factory` shell nenajde, spusť `uv tool update-shell` a otevři nový terminál.

## Přidání prvního repa

V kořeni repa spusť:

```bash
cd ~/cesta/k/repu
factory init
```

Repo můžeš přidat i z dashboardu, který otevře `factory obs`.

## Aktualizace

Novou verzi nainstaluješ z nového bundlu:

```bash
factory upgrade haifa-<verze>.zip
```

## Licence třetích stran

Viz `THIRD_PARTY_NOTICES`.
