# Installation

The GIRO installation guide: prerequisites, installing the `giro` tool from a `giro-<version>.zip` distribution, and verifying the installation. The same installation instructions are included as `INSTALL.md` in the bundle and as the **Installation** chapter in the dashboard guide (book icon in the topbar).

You do not need access to GIRO's source repository. The bundle includes the `aifactory` wheel, pinned dependencies (`constraints.txt`), installation scripts `install.sh` (macOS, Linux, WSL) and `install.bat` with `install.ps1` (Windows), uninstall scripts `uninstall.sh` and `uninstall.bat` with `uninstall.ps1`, this guide, third-party licenses and `SHA256SUMS` checksums.

## Prerequisites <!-- section:co-budes-potrebovat -->

- **System:** macOS, Linux, Windows through WSL, or native Windows 10/11 x64 (without WSL).
- **Git** with a name and email configured for commits.
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** and Python 3.11 or newer. uv installs and updates `giro`.
- **Bash, `curl` and `unzip`** for installation on macOS and Linux. On Windows, only `winget` is needed; `install.bat` installs the rest.
- **Hosting CLI** for your repositories: [GitHub CLI](https://github.com/cli/cli#installation) (`gh`) for GitHub, Azure CLI `az` with the `azure-devops` extension for Azure DevOps. Local repositories (provider `local`) need no hosting CLI.
- **At least one harness**, installed and signed in: [Claude Code](https://code.claude.com/docs/en/setup) (`claude`), [Codex CLI](https://github.com/openai/codex) (`codex`) or [pi](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent) (`pi`, requires Node.js).
- **just**, if your repositories run tests through a `justfile`.

After installation, `giro check` and the **Machine check** section on the **Library** page show what is missing.

## macOS <!-- section:macos -->

Install tools with [Homebrew](https://brew.sh/):

```bash
brew install git gh uv
uv python install 3.12
```

Continue with [Identity and sign-in](#/guide/instalace/identita-a-prihlaseni).

## Linux and WSL <!-- section:linux-a-wsl -->

For example, on Ubuntu 24.04 (also in WSL):

```bash
sudo apt update
sudo apt install git bash curl unzip gh
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
```

Continue with [Identity and sign-in](#/guide/instalace/identita-a-prihlaseni).

## Identity and sign-in <!-- section:identita-a-prihlaseni -->

Set your commit identity and sign in to GitHub CLI:

```bash
git config --global user.name "Your name"
git config --global user.email "you@example.com"
gh auth login
gh auth setup-git
```

For Azure DevOps instead:

```bash
az extension add --name azure-devops
az login
```

Install a harness, for example Claude Code:

```bash
curl -fsSL https://claude.ai/install.sh | bash
claude
```

Complete sign-in when first running `claude`. Other harnesses: `codex login`, `pi auth login`.

## Installing the bundle <!-- section:instalace-balicku -->

Obtain `giro-<version>.zip` from your team administrator. The target repository `janbkrejci/GIRO` becomes an installation source only after verified cutover T06. The currently active [HAIFA releases](https://github.com/janbkrejci/HAIFA/releases/latest) contain `haifa-H.zip` (H is the last HAIFA 0.1 version). Extract it and run the installer:

```bash
unzip giro-<version>.zip
cd giro-<version>
./install.sh
uv tool update-shell
```

The script verifies `SHA256SUMS`, installs `giro` with `uv tool install` using `constraints.txt` in a separate uv environment, and prepares and refreshes the library (see [Default library](#/guide/instalace/vychozi-knihovna)). `uv tool update-shell` adds uv's tools directory to PATH; then open a new terminal.

## Windows without WSL <!-- section:windows-bez-wsl -->

On Windows 10/11 x64, `install.bat` handles everything. It needs only `winget` (check with `winget --version`; otherwise install **App Installer** from Microsoft Store).

1. Extract `giro-<version>.zip` (right-click in File Explorer and choose **Extract All**).
2. In the `giro-<version>` directory, double-click `install.bat` (or run it from `cmd` or PowerShell).

The installer:

1. verifies `SHA256SUMS`,
2. installs missing `git`, `uv`, `gh` and Node.js through `winget`, and the `claude` and `codex` harnesses through `npm`,
3. asks for a commit name or email if Git has none,
4. installs `giro` with `uv tool install` using `constraints.txt` and adds uv's tools directory to PATH,
5. clones the default team library if none exists (`giro library clone --seed-fallback`, see [Default library](#/guide/instalace/vychozi-knihovna)), then refreshes it from the installed version's seed (`giro library seed`).

Installation through `winget` may require administrator confirmation. Rerunning is safe: existing tools are not reinstalled. Sign in where needed (`gh auth login`, `gh auth setup-git`, `claude`, `codex login`) and open a new terminal to load the updated PATH.

## Default library <!-- section:vychozi-knihovna -->

On a machine without a library, both installers clone the default team library [HAIFA-LIBRARY](https://github.com/janbkrejci/HAIFA-LIBRARY) (public repository, `main` branch). An organization can select another library through `GIRO_LIBRARY_URL` (full Git URL) in the environment or `$GIRO_HOME/env`, similar to `GIRO_UPDATE_REPO` for releases.

If cloning fails (no network or access), the installer creates a local seed library with a warning. Preserve the local library and unsent changes before cloning the team library later with `giro library clone`. Installation uses non-destructive `giro library seed`: modified items remain `kept`. A dirty library is preserved with a diagnostic when refresh fails. Review `giro library seed --dry-run`; replace a specific item only with explicit `--take`. The skill keeps its library identity `factory`, with content generated by `giro --skill`. Repository overrides in `.factory/` remain unchanged.

Changes reach HAIFA-LIBRARY only through pull requests (see [Library and team](#/guide/knihovna-a-tym)).

## Verifying installation <!-- section:overeni-instalace -->

```bash
giro --version
giro check
```

`giro --version` prints the installed version. `giro check` only reads: outside a repository it checks the machine and library; inside one it also checks the repository. Each finding has a code, severity (`error`, `warning`, `info`) and advice. Do not start tasks while the check reports `error`. See [Troubleshooting](#/guide/aktualizace-a-reseni-problemu/reseni-problemu) for failures. Use `giro check --offline` to skip hosting and harness sign-in queries.

If the shell cannot find `giro`, run `uv tool update-shell` and open a new terminal.

Start the dashboard with `giro obs` ([First run](#/guide/prvni-beh)); install a newer version with `giro upgrade giro-<version>.zip` ([Updates and troubleshooting](#/guide/aktualizace-a-reseni-problemu)).

## Uninstalling <!-- section:odinstalace -->

In the extracted bundle, run `uninstall.bat` (Windows) or `./uninstall.sh` (macOS, Linux, WSL). The script uninstalls `giro` and asks whether to delete the GIRO home directory (`~/.config/giro`, or `GIRO_HOME`) containing machine settings, the library and repository registry. `-Purge` (`--purge`) deletes it without asking; `-KeepData` (`--keep-data`) retains it. Deleting it loses unsent library changes, so run `giro library push` first.

Without the bundle, use `uv tool uninstall aifactory`. Dependencies (git, uv, gh, Node.js, harnesses), repository configuration (`.factory/`) and the backlog remain.

To move from older HAIFA, first update to the last HAIFA with the “HAIFA is becoming GIRO” alert. Once GIRO is released, click the migration action: it verifies the bundle, preserves a backup and restores the dashboard at the same address. Successful GIRO shows no migration alert and uses the new repository for normal updates. Backups are never automatically deleted. Standalone startup with old data may return `migration_required`; after stopping all processes, use `giro migrate --confirm --haifa-bundle /path/haifa-H.zip` with the verified last HAIFA bundle. Two distinct unmarked homes block startup. For rollback, stop all writes, preserve the new state too, then restore every original path and the software from the verified backup; do not remove the marker to bypass recovery. The source repository documents the full protocol in `docs/rebranding/release.md`.

`factory` remains a compatibility alias of `giro`; `HAIFA_*` are legacy aliases of `GIRO_*`. A nonempty new name wins within a layer; process environment wins over `<home>/env`. `.factory/`, `factory/backlog/`, Python distribution `aifactory`, item `skill/factory` and the HAIFA-LIBRARY URL remain technical compatibility names. Browser preferences keep their storage keys at the same origin. Purging a marked migration home is refused; use `--keep-data` / `-KeepData` to preserve data.

## License <!-- section:licence -->

GIRO uses the MIT license. Third-party licenses are in `THIRD_PARTY_NOTICES`.
