# Installation

The HAIFA (Helios AI Factory) installation guide: prerequisites, installing the `factory` tool from a `haifa-<version>.zip` distribution, and verifying the installation. The same installation instructions are included as `INSTALL.md` in the bundle and as the **Installation** chapter in the dashboard guide (book icon in the topbar).

You do not need access to HAIFA's source repository. The bundle includes the `aifactory` wheel, pinned dependencies (`constraints.txt`), installation scripts `install.sh` (macOS, Linux, WSL) and `install.bat` with `install.ps1` (Windows), uninstall scripts `uninstall.sh` and `uninstall.bat` with `uninstall.ps1`, this guide, third-party licenses and `SHA256SUMS` checksums.

## Prerequisites <!-- section:co-budes-potrebovat -->

- **System:** macOS, Linux, Windows through WSL, or native Windows 10/11 x64 (without WSL).
- **Git** with a name and email configured for commits.
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** and Python 3.11 or newer. uv installs and updates `factory`.
- **Bash, `curl` and `unzip`** for installation on macOS and Linux. On Windows, only `winget` is needed; `install.bat` installs the rest.
- **Hosting CLI** for your repositories: [GitHub CLI](https://github.com/cli/cli#installation) (`gh`) for GitHub, Azure CLI `az` with the `azure-devops` extension for Azure DevOps. Local repositories (provider `local`) need no hosting CLI.
- **At least one harness**, installed and signed in: [Claude Code](https://code.claude.com/docs/en/setup) (`claude`), [Codex CLI](https://github.com/openai/codex) (`codex`) or [pi](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent) (`pi`, requires Node.js).
- **just**, if your repositories run tests through a `justfile`.

After installation, `factory check` and the **Machine check** section on the **Library** page show what is missing.

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

Get the latest `haifa-<version>.zip` from the [HAIFA releases page](https://github.com/janbkrejci/HAIFA/releases/latest), or from your team administrator. Extract it and run the installer:

```bash
unzip haifa-<version>.zip
cd haifa-<version>
./install.sh
uv tool update-shell
```

The script verifies `SHA256SUMS`, installs `factory` with `uv tool install` using `constraints.txt` in a separate uv environment, and prepares and refreshes the library (see [Default library](#/guide/instalace/vychozi-knihovna)). `uv tool update-shell` adds uv's tools directory to PATH; then open a new terminal.

## Windows without WSL <!-- section:windows-bez-wsl -->

On Windows 10/11 x64, `install.bat` handles everything. It needs only `winget` (check with `winget --version`; otherwise install **App Installer** from Microsoft Store).

1. Extract `haifa-<version>.zip` (right-click in File Explorer and choose **Extract All**).
2. In the `haifa-<version>` directory, double-click `install.bat` (or run it from `cmd` or PowerShell).

The installer:

1. verifies `SHA256SUMS`,
2. installs missing `git`, `uv`, `gh` and Node.js through `winget`, and the `claude` and `codex` harnesses through `npm`,
3. asks for a commit name or email if Git has none,
4. installs `factory` with `uv tool install` using `constraints.txt` and adds uv's tools directory to PATH,
5. clones the default team library if none exists (`factory library clone --seed-fallback`, see [Default library](#/guide/instalace/vychozi-knihovna)), then refreshes it from the installed version's seed (`factory library seed --all`).

Installation through `winget` may require administrator confirmation. Rerunning is safe: existing tools are not reinstalled. Sign in where needed (`gh auth login`, `gh auth setup-git`, `claude`, `codex login`) and open a new terminal to load the updated PATH.

## Default library <!-- section:vychozi-knihovna -->

On a machine without a library, both installers clone the default team library [HAIFA-LIBRARY](https://github.com/janbkrejci/HAIFA-LIBRARY) (public repository, `main` branch). An organization can select another library through `HAIFA_LIBRARY_URL` (full Git URL) in the environment or `$HAIFA_HOME/env`, similar to `HAIFA_UPDATE_REPO` for releases.

If cloning fails (no network or access), the installer creates a local library from the seed and prints a warning. To clone the team library later, delete or move the local library and run `factory library clone`. For both new and existing libraries, the installer then runs `factory library seed --all`: every seed item (agents, workflows, pi extensions and the `factory` skill) is replaced with the installed HAIFA version, even if the team modified it. Items absent from the seed (team imports) remain. Repositories are unchanged: customizations belong in the repository's `.factory/`. If refreshing fails, installation completes with a warning; refresh manually with `factory library seed --all`.

Changes reach HAIFA-LIBRARY only through pull requests (see [Library and team](#/guide/knihovna-a-tym)).

## Verifying installation <!-- section:overeni-instalace -->

```bash
factory --version
factory check
```

`factory --version` prints the installed version. `factory check` only reads: outside a repository it checks the machine and library; inside one it also checks the repository. Each finding has a code, severity (`error`, `warning`, `info`) and advice. Do not start tasks while the check reports `error`. See [Troubleshooting](#/guide/aktualizace-a-reseni-problemu/reseni-problemu) for failures. Use `factory check --offline` to skip hosting and harness sign-in queries.

If the shell cannot find `factory`, run `uv tool update-shell` and open a new terminal.

Start the dashboard with `factory obs` ([First run](#/guide/prvni-beh)); install a newer version with `factory upgrade haifa-<version>.zip` ([Updates and troubleshooting](#/guide/aktualizace-a-reseni-problemu)).

## Uninstalling <!-- section:odinstalace -->

In the extracted bundle, run `uninstall.bat` (Windows) or `./uninstall.sh` (macOS, Linux, WSL). The script uninstalls `factory` and asks whether to delete the HAIFA home directory (`~/.config/haifa`, or `HAIFA_HOME`) containing machine settings, the library and repository registry. `-Purge` (`--purge`) deletes it without asking; `-KeepData` (`--keep-data`) retains it. Deleting it loses unsent library changes, so run `factory library push` first.

Without the bundle, use `uv tool uninstall aifactory`. Dependencies (git, uv, gh, Node.js, harnesses), repository configuration (`.factory/`) and the backlog remain.

## License <!-- section:licence -->

HAIFA uses the MIT license. Third-party licenses are in `THIRD_PARTY_NOTICES`.
