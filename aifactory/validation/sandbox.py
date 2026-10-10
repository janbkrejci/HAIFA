"""The test repository: the template materialized, a local bare remote or the GitHub sandbox.

The main checkout the scenarios work in is always ``<workdir>/repo``. Nothing
outside the workdir is written, except in ``--remote github`` the sandbox
repo on GitHub: a new base branch ``haifa-validate/<stamp>`` and the
``factory/*`` branches and PRs the runs create. ``main`` of the sandbox is never
changed; only ``task resolve`` force-pushes (with a lease) a ``factory/*`` branch.
"""

from __future__ import annotations

import datetime
import os
import re
import shutil
import string
import subprocess
from dataclasses import dataclass
from pathlib import Path

VALIDATION_DIR = Path(__file__).resolve().parent
AIFACTORY_DIR = VALIDATION_DIR.parent
HAIFA_ROOT = AIFACTORY_DIR.parent
TEMPLATE_DIR = VALIDATION_DIR / "template"
PROMPT_AGENTS = ("planner", "builder", "tester", "reviewer", "documenter")
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


def materialize(dest: Path, base: str, provider: str) -> list[str]:
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
                base=base, provider=provider
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


@dataclass
class Sandbox:
    remote: str  # local | github
    repo: Path  # the main checkout
    base: str
    remote_url: str
    github_repo: str | None = None  # owner/name
    bare: Path | None = None  # local: the bare origin


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
