"""The test repository: the template materialized, a local bare remote or a hosted sandbox.

The main checkout the scenarios work in is always ``<workdir>/repo``. Nothing
outside the workdir is written, except in ``--remote github`` and ``--remote
azure`` the sandbox repo on the hosting: a new base branch
``haifa-validate/<stamp>`` and the ``factory/*`` / ``factory-sync/*`` branches and
PRs the runs create. The default branch of the sandbox is never changed; only
``task resolve`` force-pushes (with a lease) a ``factory/*`` branch.

In ``--remote azure`` git authenticates over HTTPS through a credential helper in
the clone's repo-local config that hands git a fresh ``az`` access token (or
``$AZURE_DEVOPS_EXT_PAT``) on every call; no token is written to a file.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shlex
import shutil
import string
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

VALIDATION_DIR = Path(__file__).resolve().parent
AIFACTORY_DIR = VALIDATION_DIR.parent
HAIFA_ROOT = AIFACTORY_DIR.parent
TEMPLATE_DIR = VALIDATION_DIR / "template"
PROMPT_AGENTS = ("planner", "builder", "tester", "test-reviewer", "reviewer", "documenter")
SENTINEL = "haifa-validate: committed prompt"
SENTINEL_LINE = f"<!-- {SENTINEL} -->"
BASE_PREFIX = "haifa-validate/"
GIT_NAME = "HAIFA Validate"
GIT_EMAIL = "haifa-validate@example.invalid"


class SetupError(RuntimeError):
    """The test repository cannot be prepared (exit code 2)."""


def git(cwd: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8"
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} (in {cwd}) failed: {result.stderr.strip()}")
    return result.stdout.strip()


def git_ok(cwd: Path, *args: str) -> bool:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True).returncode == 0


# ── template ─────────────────────────────────────────────────────────────────


def provider_settings(azure: AzureRepo | None) -> str:
    """The provider section of the sandbox's ``config.yaml`` (empty without azure)."""
    if azure is None:
        return ""
    return (
        "azure:\n"
        f"  organization: {json.dumps(azure.organization_url)}\n"
        f"  project: {json.dumps(azure.project)}\n"
        f"  repository: {json.dumps(azure.repository)}"
    )


def materialize(dest: Path, base: str, provider: str, azure: AzureRepo | None = None) -> list[str]:
    """Copy the template into `dest` and render ``*.tmpl``; return the files written.

    The prompts (``.factory/prompts/<agent>/``, taken over from
    ``adws/adw_data/prompt_engineering`` plus the validation rule of the
    reviewer) get the sentinel line at the end of ``user.md``, which R4 looks for.
    """
    written: list[str] = []
    for src in sorted(TEMPLATE_DIR.rglob("*")):
        if src.is_dir() or "__pycache__" in src.parts:
            continue
        rel = src.relative_to(TEMPLATE_DIR)
        text: str | None = None
        if rel.suffix == ".tmpl":
            rel = rel.with_suffix("")
            text = string.Template(src.read_text(encoding="utf-8")).substitute(
                base=base, provider=provider, provider_settings=provider_settings(azure)
            )
        elif (
            rel.parts[:2] == (".factory", "prompts")
            and rel.name == "user.md"
            and rel.parent.name in PROMPT_AGENTS
        ):
            text = src.read_text(encoding="utf-8").rstrip("\n") + f"\n\n{SENTINEL_LINE}\n"
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if text is None:
            shutil.copyfile(src, target)
        else:
            target.write_text(text, encoding="utf-8", newline="\n")
        written.append(rel.as_posix())
    return written


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


# ── local ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AzureRepo:
    """An Azure DevOps repository: organization URL, project and repository name."""

    organization_url: str
    project: str
    repository: str

    @property
    def web_url(self) -> str:
        project = quote(self.project, safe="")
        return f"{self.organization_url}/{project}/_git/{quote(self.repository, safe='')}"

    def repo_args(self) -> list[str]:
        return [
            "--org",
            self.organization_url,
            "--project",
            self.project,
            "--repository",
            self.repository,
        ]


@dataclass
class Sandbox:
    remote: str  # local | github | azure
    repo: Path  # the main checkout
    base: str
    remote_url: str
    github_repo: str | None = None  # owner/name
    bare: Path | None = None  # local: the bare origin
    azure: AzureRepo | None = None  # azure: the sandbox repo


def _apply_roster(repo: Path, roster: Path | None) -> None:
    if roster is None:
        return
    from validation.roster import apply_roster  # roster imports this module

    apply_roster(repo, roster)


def _exclude_hidden(repo: Path) -> None:
    from validation.hidden import exclude

    exclude(repo)


def setup_local(workdir: Path, roster: Path | None = None) -> Sandbox:
    bare = workdir / "remote.git"
    repo = workdir / "repo"
    git(workdir, "init", "-q", "--bare", "-b", "main", str(bare))
    git(workdir, "init", "-q", "-b", "main", str(repo))
    git(repo, "config", "user.name", GIT_NAME)
    git(repo, "config", "user.email", GIT_EMAIL)
    git(repo, "config", "commit.gpgsign", "false")
    _exclude_hidden(repo)
    materialize(repo, "main", "local")
    _apply_roster(repo, roster)
    commit_all(repo, "validation sandbox")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "-u", "origin", "main")
    return Sandbox("local", repo, "main", str(bare), bare=bare)


# ── github ───────────────────────────────────────────────────────────────────

_GITHUB_FORMS = (
    re.compile(r"^(?:https?://)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$"),
    re.compile(r"^git@github\.com:([\w.-]+)/([\w.-]+?)(?:\.git)?$"),
    re.compile(r"^([\w.-]+)/([\w.-]+?)(?:\.git)?$"),
)


def normalize_repo(value: str | None) -> str:
    """``owner/name`` from ``owner/name``, an https URL or an ssh URL; raise ``SetupError``."""
    text = (value or "").strip()
    if not text:
        raise SetupError(
            "HAIFA_SANDBOX_REPO is not set: put the GitHub sandbox repo "
            "(owner/name or its URL) into .env"
        )
    for form in _GITHUB_FORMS:
        match = form.match(text)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
    raise SetupError(f"HAIFA_SANDBOX_REPO={text!r} is not a GitHub repo (owner/name or URL)")


def gh_executable() -> str:
    return os.environ.get("AIFACTORY_GH") or "gh"


def gh(cwd: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        [gh_executable(), *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8"
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def stamp(when: datetime.datetime | None = None) -> str:
    return (when or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")


def setup_github(
    workdir: Path,
    owner_name: str,
    when: datetime.datetime | None = None,
    roster: Path | None = None,
) -> Sandbox:
    repo = workdir / "repo"
    result = subprocess.run(
        [gh_executable(), "repo", "clone", owner_name, str(repo), "--", "-q"],
        cwd=workdir,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise SetupError(f"gh repo clone {owner_name}: {result.stderr.strip()}")
    base = f"{BASE_PREFIX}{stamp(when)}"
    start = "origin/HEAD" if git_ok(repo, "rev-parse", "--verify", "-q", "origin/HEAD") else "HEAD"
    git(repo, "checkout", "-q", "-b", base, start)
    git(repo, "config", "commit.gpgsign", "false")
    _exclude_hidden(repo)
    materialize(repo, base, "github")
    _apply_roster(repo, roster)
    commit_all(repo, f"validation sandbox ({base})")
    git(repo, "push", "-q", "-u", "origin", base)
    # Earlier validations left factory/* branches on GitHub; next_branch only sees
    # local branches, so fetch them to keep new branch names free.
    git(repo, "fetch", "-q", "origin", "+refs/heads/factory/*:refs/heads/factory/*", check=False)
    url = git(repo, "remote", "get-url", "origin")
    return Sandbox("github", repo, base, url, github_repo=owner_name)


# ── azure ────────────────────────────────────────────────────────────────────

AZURE_SANDBOX_ENV = "HAIFA_AZURE_SANDBOX_REPO"
AZURE_DEVOPS_RESOURCE = "499b84ac-1321-427f-aa17-267ca6975798"
AZ_TAIL = ("--detect", "false", "--output", "json", "--only-show-errors")
_SEGMENT = r"[^/?#\s]+"
_AZURE_FORMS = (
    (
        re.compile(
            rf"^https://(?:{_SEGMENT}@)?({_SEGMENT})\.visualstudio\.com/"
            rf"({_SEGMENT})/_git/({_SEGMENT})/?$"
        ),
        "https://{}.visualstudio.com",
    ),
    (
        re.compile(
            rf"^https://(?:{_SEGMENT}@)?dev\.azure\.com/({_SEGMENT})/"
            rf"({_SEGMENT})/_git/({_SEGMENT})/?$"
        ),
        "https://dev.azure.com/{}",
    ),
    (re.compile(r"^([\w.-]+)/([^/:\s]+)/([^/:\s]+)$"), "https://dev.azure.com/{}"),
)


def normalize_azure_repo(value: str | None) -> AzureRepo:
    """The Azure DevOps sandbox from a clone URL or ``org/project/repo``; raise ``SetupError``."""
    text = (value or "").strip()
    forms = (
        "https://<org>.visualstudio.com/<project>/_git/<repo>, "
        "https://dev.azure.com/<org>/<project>/_git/<repo> or <org>/<project>/<repo>"
    )
    if not text:
        raise SetupError(
            f"{AZURE_SANDBOX_ENV} is not set: put the Azure DevOps sandbox repo ({forms}) into .env"
        )
    for form, org_url in _AZURE_FORMS:
        match = form.match(text)
        if match:
            org, project, repository = match.groups()
            return AzureRepo(org_url.format(org), unquote(project), unquote(repository))
    raise SetupError(f"{AZURE_SANDBOX_ENV}={text!r} is not an Azure DevOps repo ({forms})")


def az_executable() -> str:
    return os.environ.get("AIFACTORY_AZ") or "az"


def az(cwd: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        [az_executable(), *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8"
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"az {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def azure_credential_helper() -> str:
    """A git credential helper that prints a fresh Azure DevOps token for every call.

    ``$AZURE_DEVOPS_EXT_PAT`` wins when set; otherwise ``az account
    get-access-token`` is asked. The token is printed to git, never stored.
    """
    token = " ".join(
        shlex.quote(part)
        for part in (
            az_executable(),
            "account",
            "get-access-token",
            "--resource",
            AZURE_DEVOPS_RESOURCE,
            "--query",
            "accessToken",
            "--output",
            "tsv",
        )
    )
    return (
        '!f() { test "$1" = get || exit 0; echo username=haifa; '
        f'echo "password=${{AZURE_DEVOPS_EXT_PAT:-$({token})}}"; }}; f'
    )


def git_auth_args() -> list[str]:
    """``git -c`` options that reset the global helpers and use the token helper only."""
    return ["-c", "credential.helper=", "-c", f"credential.helper={azure_credential_helper()}"]


def azure_show(cwd: Path, target: AzureRepo) -> dict[str, object]:
    """``az repos show`` of the sandbox; ``SetupError`` when it is not reachable."""
    result = subprocess.run(
        [az_executable(), "repos", "show", *target.repo_args(), *AZ_TAIL],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise SetupError(
            f"az repos show {target.web_url}: {(result.stderr or result.stdout).strip()}"
        )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SetupError(f"az repos show {target.web_url}: not JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("remoteUrl"), str):
        raise SetupError(f"az repos show {target.web_url}: no remoteUrl in the output")
    return data


def setup_azure(
    workdir: Path,
    target: AzureRepo,
    when: datetime.datetime | None = None,
    roster: Path | None = None,
) -> Sandbox:
    data = azure_show(workdir, target)
    url = str(data["remoteUrl"])
    repo = workdir / "repo"
    result = subprocess.run(
        ["git", *git_auth_args(), "clone", "-q", url, str(repo)],
        cwd=workdir,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise SetupError(f"git clone {url}: {result.stderr.strip()}")
    # repo-local, so every worktree HAIFA creates authenticates the same way
    git(repo, "config", "credential.helper", "")
    git(repo, "config", "--add", "credential.helper", azure_credential_helper())
    base = f"{BASE_PREFIX}{stamp(when)}"
    start = "origin/HEAD" if git_ok(repo, "rev-parse", "--verify", "-q", "origin/HEAD") else "HEAD"
    git(repo, "checkout", "-q", "-b", base, start)
    git(repo, "config", "commit.gpgsign", "false")
    _exclude_hidden(repo)
    materialize(repo, base, "azure", azure=target)
    _apply_roster(repo, roster)
    commit_all(repo, f"validation sandbox ({base})")
    git(repo, "push", "-q", "-u", "origin", base)
    git(repo, "fetch", "-q", "origin", "+refs/heads/factory/*:refs/heads/factory/*", check=False)
    return Sandbox("azure", repo, base, url, azure=target)
