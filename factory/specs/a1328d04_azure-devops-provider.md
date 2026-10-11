# Plán 2.11 — Provider Azure DevOps (`az repos`) proti falešnému `az`

## Cíl

Implementovat `AzureProvider(GitProvider)` v `aifactory/src/aifactory/providers/azure.py`.
Rozhraní z 2.10 (`providers/base.py`) se **nemění**. Provider umí `create_pr`, `status`
(včetně `unknown` a opakování dotazu), `merge` se strategií `squash`/`merge` a kontrolou
`head_sha`, a `comment`. Organizace, projekt a repo jsou v `.factory/config.yaml`.
Chybějící `az`, chybějící rozšíření `azure-devops` nebo chybějící přihlášení vrací
srozumitelnou `ProviderError` z vlastní kontroly provideru (ne `factory harness check`).
Testy běží proti falešnému `az` na `PATH`, nevolají síť.

Neměnit `vendor/` ani `prototype/`. V prototypu ani ve vendoru žádná reference pro `az repos` není.

## Vzor

`providers/github.py` + `tests/providers/gh_fake.py` + `tests/providers/test_providers_github.py`.
Azure provider kopíruje jejich strukturu (třída CLI wrapperu, `attempts`/`delay`/`sleep`
injektované v konstruktoru, falešný CLI se sdíleným bin adresářem kvůli pomalému prvnímu
spuštění na macOS).

## 1. Konfigurace — `aifactory/src/aifactory/config/settings.py`

Přidat model a pole:

```python
class AzureSettings(BaseModel):
    """``azure:`` section of ``.factory/config.yaml`` (git_provider: azure)."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    organization: str   # "contoso" nebo "https://dev.azure.com/contoso"
    project: str
    repository: str

    @field_validator("organization", "project", "repository")
    -> strip, prázdné = ValueError("must not be empty")

    @property
    def organization_url(self) -> str:
        # obsahuje "://" -> vrátit bez koncového "/"; jinak f"https://dev.azure.com/{name}"
```

V `ProjectSettings` přidat `azure: AzureSettings | None = None` a
`@model_validator(mode="after")`: když `git_provider == "azure"` a `azure is None`, vyhodit
`ValueError("git_provider 'azure' needs an 'azure' section with organization, project and repository")`.
Díky `parse_project_settings` se z toho stane `ConfigIssue` (validation_issues už umí `<root>` loc).
Sekce `azure` s jiným providerem je povolená (ignoruje se).

Tvar v configu:

```yaml
git_provider: azure
azure:
  organization: contoso            # nebo https://dev.azure.com/contoso
  project: Fabrikam
  repository: fabrikam-app
```

Ověřit, že `config show --json` (`run.to_json()`) sekci serializuje (pydantic model_dump
nested modelu — mělo by fungovat bez zásahu; pokud `to_json` dělá něco ručně, doplnit).

## 2. Provider — nový `aifactory/src/aifactory/providers/azure.py`

Docstring modulu: provider `azure`, všechno přes `AzCli.run`, executable `az` z `PATH`
nebo `$AIFACTORY_AZ`, vždy `--output json --only-show-errors`, u `az repos` vždy
`--detect false` a explicitní `--org` (az nesmí nic odvozovat z git remote).
Komentáře jdou přes `az devops invoke` (skupina `az repos pr` nemá příkaz na komentář).
Azure počítá `mergeStatus` asynchronně (`queued`/`notSet`), proto `status` opakuje dotaz
jako GitHub. Poznámka: ověřeno jen proti falešnému `az` (dle dokumentace), živé ověření čeká.

### Konstanty

```python
UNKNOWN_ATTEMPTS = 5
UNKNOWN_DELAY = 2.0
API_VERSION = "7.1"
PAT_ENV = "AZURE_DEVOPS_EXT_PAT"
```

### `AzError(ProviderError)` a `AzCli`

- `AzError(args, returncode, stderr)`: kód `az_not_logged_in`, pokud `stderr.lower()`
  obsahuje `"az login"` nebo `"tf400813"` (Azure DevOps „not authorized“); jinak `az_failed`.
  Zpráva `f"az {' '.join(args[:3])}: {stderr.strip() or f'exit {rc}'}"`. Uložit
  `args_`, `returncode`, `stderr` jako u `GhError`.
- `AzCli(cwd, executable=None)`: `self.executable = executable or os.environ.get("AIFACTORY_AZ") or "az"`.
  - `run(*args) -> str`: `subprocess.run([exe, *args], cwd=..., input="", capture_output=True, text=True)`;
    `FileNotFoundError` -> `ProviderError("az_missing", "az (Azure CLI) is not installed or not on PATH; install it: https://aka.ms/azure-cli")`;
    nenulový exit -> `AzError`.
  - `json(*args) -> Any`: `run` + `json.loads`; chyba parsování -> `ProviderError("az_failed", "... not JSON ...")`.

### Pomocné funkce

- `_commit(data, key) -> str | None`: `data[key]["commitId"]`, pokud je to dict se str.
- `_branch(ref) -> str`: odstraní prefix `refs/heads/`.
- `_ref(branch) -> str`: přidá `refs/heads/`, pokud tam není.

### `AzureProvider(GitProvider)`, `name = "azure"`

Konstruktor `(root, settings, az: AzCli | None = None, *, attempts=UNKNOWN_ATTEMPTS, delay=UNKNOWN_DELAY, sleep=time.sleep)`.
`attempts < 1` -> `ValueError`. `settings.azure is None` -> `ProviderError("invalid_config", "git_provider 'azure' needs an 'azure' section ...")`
(obrana, config validace by to měla chytit dřív). Uložit `self.azure = settings.azure`, `self._checked = False`.

**`check() -> None`** (veřejná, vlastní kontrola provideru; volá se lazy přes `_ready()` před
první operací a výsledek se cachuje v `_checked`):
1. `az --version` — `FileNotFoundError` -> `az_missing` (z `AzCli.run`); nenulový exit -> přemapovat na `ProviderError("az_missing", ...)`.
2. `az extension show --name azure-devops --output json` — nenulový exit ->
   `ProviderError("az_devops_missing", "the azure-devops extension of az is missing; run: az extension add --name azure-devops")`.
3. Přihlášení: pokud je `os.environ.get(PAT_ENV)` neprázdné -> OK. Jinak `az account show --output json`;
   nenulový exit -> `ProviderError("az_not_logged_in", "az is not logged in; run 'az login' or set AZURE_DEVOPS_EXT_PAT")`.

Každá veřejná operace (`create_pr`, `status`, `merge`, `comment`) začíná `self._ready()`.

Společné argumenty: `org = ["--org", self.azure.organization_url]`, `tail = ["--detect", "false", "--output", "json", "--only-show-errors"]`
(pro `devops invoke` bez `--detect`, pouze `--org`, `--output json`, `--only-show-errors`).

**`create_pr(branch, title, body)`**

```
az repos pr create --org <url> --project <p> --repository <r>
   --source-branch <branch> --target-branch <settings.base> --title <title>
   [--description <line> <line> ...] --detect false --output json --only-show-errors
```

- `--description`: dokumentace — „each value sent to this arg will be a new line“.
  `body.splitlines()`; prázdné tělo -> argument vynechat. Řádek, který začíná `-` a
  neobsahuje mezeru (argparse by ho vzal jako přepínač, např. `---`), dostane jednu
  úvodní mezeru (v markdownu neškodí). Tuto transformaci dát do `_description_lines(body)`.
- Odpověď (objekt PR dle `az repos pr create/show`): `pullRequestId` (int) povinné, jinak
  `ProviderError("az_failed", "az repos pr create: no pullRequestId in output")`.
- URL: `f"{repository.webUrl}/pullrequest/{id}"`, když `repository.webUrl` je str; jinak
  `f"{org_url}/{quote(project)}/_git/{quote(repository)}/pullrequest/{id}"` (`urllib.parse.quote`, `safe=""`).
- Vrátit `PullRequest(id=str(id), url=..., branch=branch, base=settings.base, title=title)`.

**`_status_once(pr)`**: `az repos pr show --id <id> --org <url> --detect false --output json --only-show-errors`
(`pr show` bere jen `--id/--org/--detect`, ne `--project`). Musí to být dict, jinak `az_failed`.
- `head = _commit(data, "lastMergeSourceCommit")`
- `status` (lowercase): `completed` -> `PrStatus(MERGED, head_sha=head, merge_sha=_commit(data, "lastMergeCommit"))`;
  `abandoned` -> `PrStatus(CLOSED, head_sha=head)`; jinak (`active`) podle `mergeStatus` (lowercase):
  `succeeded` -> `MERGEABLE`; `conflicts` -> `CONFLICT`; cokoliv jiného (`queued`, `notset`,
  `failure`, `rejectedbypolicy`, chybí) -> `UNKNOWN`.

**`status(pr)`**: stejná smyčka jako v GitHubu — opakovat, dokud je `OPEN`+`UNKNOWN`, max
`attempts`, mezi pokusy `sleep(delay)`. (Pro jednoduchost se opakuje u všech UNKNOWN.)

**`merge(pr, head_sha, subject, strategy=None)`**
1. `chosen = self._strategy(strategy)` (neplatná -> `invalid_strategy` ještě před voláním `az`).
2. `current = self.status(pr)`: `MERGED` -> vrátit `current.merge_sha`; `CLOSED` ->
   `MergeFailed("merge_failed", "PR <id> is abandoned")`; `CONFLICT` -> `MergeFailed("conflict", ...)`.
3. `current.head_sha != head_sha` -> `MergeFailed("merge_failed", f"PR {id} moved: {current.head_sha} != {head_sha}")`.
   (CLI nemá obdobu `--match-head-commit`; `az repos pr update --status completed` pošle
   `lastMergeSourceCommit` načtený těsně předtím, zbylé okno závodu zdokumentovat v docstringu.)
4. ```
   az repos pr update --id <id> --org <url> --status completed
      --squash {true|false} --merge-commit-message <subject>
      --delete-source-branch false --detect false --output json --only-show-errors
   ```
   (`squash` -> `--squash true`, `merge` -> `--squash false`; mazání větve patří do 2.12.)
5. `AzError` -> jako v GitHubu: zkusit `_status_once`; `OPEN`+`CONFLICT` ->
   `MergeFailed("conflict", ...)`, jinak `MergeFailed("merge_failed", stderr nebo message)`.
   Výjimka: `AzError` s kódem `az_not_logged_in` se propaguje jako je (nepřebalovat).
6. Úspěch: odpověď je objekt PR. `status == "completed"` -> vrátit `_commit(resp, "lastMergeCommit")`.
   Jinak (dokončení je asynchronní) pollovat `_status_once` až `attempts`× se `sleep(delay)`
   mezi pokusy: `MERGED` -> `merge_sha`; `CLOSED` -> `MergeFailed("merge_failed", ...)`;
   `OPEN`+`CONFLICT` -> `MergeFailed("conflict", ...)`; po vyčerpání ->
   `MergeFailed("merge_failed", f"PR {id} not completed after {attempts} checks")`.

**`comment(pr, body)`** — REST „Pull Request Threads - Create“ přes `az devops invoke`:
- Zapsat do dočasného souboru (`tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")`)
  `{"comments": [{"parentCommentId": 0, "content": body, "commentType": 1}], "status": 1}`;
  soubor smazat ve `finally`.
- ```
  az devops invoke --area git --resource pullRequestThreads
     --route-parameters project=<p> repositoryId=<r> pullRequestId=<id>
     --http-method POST --in-file <path> --api-version 7.1
     --org <url> --output json --only-show-errors
  ```

### Registrace — `providers/__init__.py`

Větev `azure` v `get_provider` vrací `AzureProvider(root, settings)` (lazy import jako GitHub).
Aktualizovat docstring modulu (`local`, `github`, `azure`). Volitelně reexport nic dalšího netřeba.

## 3. Falešný `az` — nový `aifactory/tests/providers/az_fake.py`

Kopie `gh_fake.py` s úpravami (gh_fake neměnit):
- env `AIFACTORY_FAKE_AZ_STATE`, soubor `az`, sdílený adresář `aifactory-fake-az-<uid>-<hash>`,
  `install_fake_az(tmp_path, monkeypatch, responses)`, `prepare_shared_az(tmp_dir)`, `AzLog`, `reply`.
- `install_fake_az` navíc `monkeypatch.delenv("AIFACTORY_AZ")` a `monkeypatch.delenv("AZURE_DEVOPS_EXT_PAT")` (raising=False).
- Klíč odpovědi: slova argv před prvním argumentem začínajícím `--` spojená mezerou
  (`"repos pr create"`, `"repos pr show"`, `"repos pr update"`, `"devops invoke"`,
  `"account show"`, `"extension show"`); je-li prázdný, `args[0]` (`"--version"`).
- Log: `{"argv", "stdin", "cwd", "in_file"}` — když argv obsahuje `--in-file`, skript
  přečte obsah souboru v okamžiku volání (provider ho pak smaže) a uloží ho jako JSON
  (nebo text, když nejde parsovat).
- Default odpověď `{"stdout": "", "exit": 0}` (takže `check()` projde bez nastavení).
- Helpery pro realistické odpovědi dle dokumentace `az repos pr` (camelCase objekt
  GitPullRequest): `pr_json(id=7, status="active", merge_status="succeeded", head=HEAD, merge=None, web_url=...)`
  vrací dict s klíči `pullRequestId`, `codeReviewId`, `status`, `mergeStatus`, `isDraft`,
  `title`, `description`, `sourceRefName` (`refs/heads/...`), `targetRefName`,
  `lastMergeSourceCommit {commitId,url}`, `lastMergeTargetCommit`, `lastMergeCommit` (nebo chybí/None),
  `repository {id,name,url,webUrl,project{id,name}}`, `createdBy {displayName,uniqueName}`,
  `creationDate`, `closedDate`, `mergeId`, `url` (REST URL `.../_apis/git/repositories/.../pullRequests/7`),
  `completionOptions`. Helper `thread_json()` pro odpověď `devops invoke`
  (`{"id": 1, "status": "active", "comments": [...], "publishedDate": ...}`).

Import v testech funguje stejně jako `from gh_fake import ...` (rootdir/prepend import mode, bez `__init__.py`).
Musí projít `mypy --strict` (soubor je v `files = ["src", "tests"]`) a ruff.

## 4. Testy — nový `aifactory/tests/providers/test_providers_azure.py`

Module-scoped autouse fixture `prepare_shared_az`. `_provider(tmp_path, sleeps, attempts=5, **settings)`
s `ProjectSettings.model_validate({"git_provider": "azure", "azure": {"organization": "contoso", "project": "Fab Rikam", "repository": "app"}, **settings})`.
`_calls(log, key)` filtr podle klíče. Testy (všechny bez sítě):

Konfigurace / výběr:
1. `organization_url`: `contoso` -> `https://dev.azure.com/contoso`; plná URL s `/` na konci se ořízne.
2. `git_provider: azure` bez sekce `azure` -> `parse_project_settings` vrátí None a issue zmiňuje `azure`.
3. Prázdný `project` / neznámý klíč v `azure` -> issue.

Kontrola provideru:
4. `az` chybí (`AzCli(executable=tmp_path/"nope")` jako `az` provideru) -> `create_pr` vyhodí `ProviderError` kód `az_missing`.
5. `extension show` exit 1 -> `az_devops_missing`, hláška obsahuje `az extension add`.
6. `account show` exit 1 -> `az_not_logged_in`, hláška obsahuje `az login`; žádné `repos pr` volání neproběhlo.
7. `account show` exit 1, ale `AZURE_DEVOPS_EXT_PAT` nastaven -> operace projde, `account show` se nevolal.
8. Kontrola běží jednou: dvě operace -> `--version` zavolán jednou.
9. `repos pr show` selže se stderr obsahujícím `az login` -> kód `az_not_logged_in`; jiný stderr -> `az_failed`.

create_pr:
10. Přesné argv (`--org https://dev.azure.com/contoso`, `--project`, `--repository`, `--source-branch`, `--target-branch main`, `--title`, `--description` řádky, `--detect false`, `--output json`); výsledné `PullRequest` s URL z `repository.webUrl`.
11. Víceřádkový body včetně prázdného řádku a `---` -> `--description` hodnoty, `---` s úvodní mezerou; prázdný body -> žádné `--description`.
12. Odpověď bez `repository.webUrl` -> URL složená z org/projekt/repo (projekt s mezerou URL-kódovaný).
13. Odpověď bez `pullRequestId` / ne-JSON -> `az_failed`.

status (parametrizovat):
14. `active/succeeded` -> OPEN MERGEABLE, `active/conflicts` -> OPEN CONFLICT, `completed` -> MERGED s `merge_sha`, `abandoned` -> CLOSED; `head_sha` z `lastMergeSourceCommit`; argv `repos pr show --id 7 --org ... --detect false --output json`.
15. `queued` pak `succeeded` -> MERGEABLE, jeden `sleep(DELAY)`.
16. `notSet` stále -> po `attempts` UNKNOWN, `attempts-1` spánků.
17. `queued` pak `conflicts` -> CONFLICT.

merge:
18. Výchozí strategie squash -> `repos pr update ... --status completed --squash true --merge-commit-message <subject> --delete-source-branch false`; vrací `lastMergeCommit.commitId` z odpovědi.
19. `merge_strategy: merge` z configu -> `--squash false`; explicitní `strategy="merge"` přebije config.
20. Neplatná strategie -> `invalid_strategy`, žádné volání `az`.
21. Už MERGED -> vrací merge sha bez `update`; ABANDONED -> `merge_failed`; CONFLICT -> `conflict` bez `update`.
22. `head_sha` nesedí -> `merge_failed`, žádný `update`.
23. `update` selže a následný `show` ukáže `conflicts` -> `MergeFailed` `conflict`; jinak `merge_failed` se stderr.
24. `update` vrátí `active` (asynchronní dokončení), další `show` `completed` -> vrátí merge sha; stále `active` -> `merge_failed` po `attempts`.

comment:
25. argv `devops invoke --area git --resource pullRequestThreads --route-parameters project=Fab Rikam repositoryId=app pullRequestId=7 --http-method POST --in-file <path> --api-version 7.1 --org ...`; `in_file` == `{"comments":[{"parentCommentId":0,"content":"hello","commentType":1}],"status":1}`; dočasný soubor po volání neexistuje.
26. `devops invoke` selže -> `ProviderError` `az_failed`.

Ostatní:
27. `attempts=0` -> `ValueError`.

### Úprava `tests/providers/test_providers_select.py`

`test_azure_is_not_supported_yet` nahradit `test_azure_from_config`: config s `git_provider: azure` + sekce `azure` -> `isinstance(provider, AzureProvider)`, `provider.name == "azure"` (konstruktor nesmí volat `az`). Přidat test chybějící sekce (nebo ho mít v test_providers_azure — stačí jednou).

## 5. Dokumentace

- `BACKLOG.md` a `backlog/` neměnit (stav řeší workflow).
- Nová dokumentace do `app_docs/` není součástí tohoto kroku (dělá ji dokumentační fáze), ale docstring modulu `azure.py` musí popsat konfiguraci, kontrolu a použité příkazy `az`.

## Ověření

Z kořene repa:

```
just test          # celá sada, musí projít (exit 0)
just typecheck     # mypy --strict src + tests
just lint          # ruff check + ruff format --check (spustit `cd aifactory && uv run ruff format .` před kontrolou)
```

Rychlá iterace: `just test tests/providers -q`.
Kontrola, že testy nevolají síť: všechny `az` volání jdou přes fake (`AzCli` bez explicitního
executable používá `az` z `PATH`, kam `install_fake_az` dá fake první); žádný test nekonstruuje
provider bez `install_fake_az`, pokud provádí operaci (výjimka: test s neexistujícím executable).
Posuzovat podle exit kódu příkazů.

## Soubory

- upravit: `aifactory/src/aifactory/config/settings.py`, `aifactory/src/aifactory/providers/__init__.py`, `aifactory/tests/providers/test_providers_select.py`
- nové: `aifactory/src/aifactory/providers/azure.py`, `aifactory/tests/providers/az_fake.py`, `aifactory/tests/providers/test_providers_azure.py`
- neměnit: `vendor/`, `prototype/`, `providers/base.py`, `gh_fake.py`
