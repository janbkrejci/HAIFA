# Sdílená databáze týmu

HAIFA umí sdílet běhy, trace, PR metadata a backlog mezi počítači. Výchozí lokální SQLite funguje dál bez konfigurace. Sdílená varianta používá HAIFA SQLite službu přes HTTP; přímý MSSQL/ODBC driver zatím podporován není.

## Spuštění serveru

Na počítači s checkoutem HAIFA a `uv`:

```sh
just shared-db --data-dir ./team-db --host 0.0.0.0 --port 4710
```

Nebo z instalovaného Python balíčku:

```sh
python -m aifactory.database.server --data-dir ./team-db --host 0.0.0.0 --port 4710
```

Služba se spouští zvlášť od dashboardu. Bez `--host` poslouchá pouze na `127.0.0.1`. Adresář `team-db` obsahuje trvalá SQLite data; zálohujte jej standardním SQLite backupem nebo po zastavení služby.

Docker z kořene checkoutu HAIFA:

```sh
docker build -f aifactory/bundle/database.Dockerfile -t haifa-db .
docker run --name haifa-db -p 4710:4710 -v haifa-db:/data haifa-db
```

Databáze je podle zadání veřejná read/write, bez přihlašování. Kdo dosáhne na endpoint, může číst a měnit data. HTTPS lze zajistit reverzní proxy před službou.

## Připojení všech projektů

Každý člen týmu nastaví v HAIFA home soubor `database.yaml`:

```yaml
url: http://db-host:4710
```

Home je obvykle `~/.config/haifa`, případně cesta daná `HAIFA_HOME` nebo `$XDG_CONFIG_HOME/haifa`. Jednorázové připojení lze nastavit přes prostředí:

```sh
HAIFA_DATABASE_URL=http://db-host:4710 just dash
HAIFA_DATABASE_URL=http://db-host:4710 just factory backlog list
```

Pro trvalé nastavení prostředí lze použít stávající HAIFA home `env` soubor. Připojení konkrétního projektu má nejvyšší prioritu v jeho necommitovaném `.factory/local.yaml`:

```yaml
database_url: http://db-host:4710
```

Priorita je `local.yaml` > `HAIFA_DATABASE_URL` > home `database.yaml`. `database_url` nepatří do sdíleného `.factory/config.yaml`. Po změně nastavení restartujte dashboard. Pro návrat k lokálnímu režimu odstraňte všechna nastavení URL; použije se původní `trace_db`.

## Jak se projekty propojí

Oba checkouty musí mít remote na stejnou repository. HAIFA používá remote pojmenovaný v `.factory/config.yaml` (standardně `origin`). Například `git@github.com:Team/Repo.git` a `https://github.com/Team/Repo` označují stejný projekt. Rozdílné lokální adresáře nevadí. Fork nebo jiná remote cesta má samostatná data. Repo bez síťového remote v tomto režimu nefunguje.

Nová vzdálená DB nezačne automaticky obsahovat starší lokální běhy. První načtení backlogu naplní prázdný projekt jeho Markdown soubory. Další checkouty načtou sdílený obsah a nové běhy používají serverovou databázi. Před prvním připojením uchovejte/commitněte své místní backlog změny; první synchronizace při rozdílném vzdáleném obsahu necommitnuté změny odmítne přepsat.

## Souběžná práce

Běhy a změny backlogu se zobrazují přes stávající live aktualizace dashboardu. `task add/edit/link` validují obsah a atomicky zveřejní změny; změny Markdown souborů se synchronizují také při dalším načtení backlogu. Změny různých souborů lze sloučit. Při souběžné úpravě stejného souboru dostanete `remote_backlog_conflict`: uchovejte místní editaci stranou, obnovte soubor na poslední synchronizovaný obsah, znovu načtěte backlog a aplikujte editaci na aktuální obsah. Pokud DB změnil jiný člen během validace příkazu, stačí načíst aktuální backlog a příkaz opakovat.

Smazání synchronizovaného souboru se automaticky nepublikuje a vyvolá konflikt; pro odebrání tasku používejte `status: cancelled`. Sdílení backlogu neprovádí Git commit ani push. Nadále používejte obvyklé factory příkazy pro publikování backlogu do Git.

Agentní procesy, checkouty a log soubory jsou na počítači, který běh spustil. Pause/resume lze žádat z jiného počítače přes DB. Stop spouštějte na původním počítači: cizí PID se neposílá místnímu operačnímu systému. Osiřelé běhy reaper vyhodnocuje pouze na původním počítači; při jeho výpadku mohou do jeho návratu zůstat označené jako running. Služba nepřesouvá agentní procesy ani lokální artefakty mezi stroji.

Pokud DB není dostupná, zápis skončí chybou; nevytvoří se oddělená lokální historie. Odpojené klientské transakce se po 120 sekundách nečinnosti vrátí zpět. Expirace během transakce vyžaduje opakování celé operace, zatímco nečinné připojení se obnoví automaticky.
