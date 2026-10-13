"""Library changes reach the remote only as pull requests (HAIFA-S05-T17).

The default team library is ``DEFAULT_LIBRARY_URL``; ``$HAIFA_LIBRARY_URL`` overrides it
(a company install, like ``HAIFA_UPDATE_REPO``). A change that would go to the remote
(``library push``, ``library seed``, import, the move into the library) is committed to
the local library at once and proposed on a new branch ``haifa-library/...``, never pushed
to the library branch itself. On GitHub the branch goes to the library repo when the user
may write to it, else to the user's fork (``gh repo fork``), and ``gh pr create`` opens
the pull request against the library branch. HAIFA never merges it, never approves it and
never uses ``--admin``: merging is the library maintainer's job. Other remotes get only
the branch; the pull request is opened by hand.

Sent changes are recorded in ``.git/haifa-pull-requests.json`` of the library by their
``git patch-id``, so they stay recognised after ``library pull`` rebases the local commits
onto the merged remote.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aifactory.library.store import REMOTE, LibraryStoreError, _git_detail
from aifactory.providers import git
from aifactory.providers.base import ProviderError

DEFAULT_LIBRARY_URL = "https://github.com/janbkrejci/HAIFA-LIBRARY.git"
LIBRARY_URL_ENV = "HAIFA_LIBRARY_URL"
PR_PREFIX = "haifa-library/"
STATE_FILE = "haifa-pull-requests.json"
WRITE_PERMISSIONS = ("ADMIN", "MAINTAIN", "WRITE")
OPEN = "OPEN"
DONE = "DONE"
CLOSED = "CLOSED"
# a new fork can take a moment before it accepts a push
FORK_PUSH_ATTEMPTS = 5
FORK_PUSH_DELAY = 3.0

_GITHUB = re.compile(
    r"^(?:https?://(?:[^@/]+@)?github\.com/|ssh://(?:[^@/]+@)?github\.com/|[^@/]+@github\.com:)"
    r"(?P<owner>[A-Za-z0-9-]+)/(?P<repo>[A-Za-z0-9._-]+?)(?P<suffix>\.git)?/?$"
)


def default_library_url(environ: Mapping[str, str] | None = None) -> str:
    """``$HAIFA_LIBRARY_URL``, else the HAIFA-LIBRARY repo."""
    env = os.environ if environ is None else environ
    return (env.get(LIBRARY_URL_ENV) or "").strip() or DEFAULT_LIBRARY_URL


def github_repo(url: str | None) -> tuple[str, str] | None:
    """(owner, repo) of a github.com URL (https, ssh or scp form); None for other hosts."""
    match = _GITHUB.match(url or "")
    return (match["owner"], match["repo"]) if match else None


def fork_url(url: str, login: str) -> str:
    """`url` of the library repo with the owner replaced by `login` (the fork)."""
    match = _GITHUB.match(url)
    if match is None:
        raise ValueError(f"not a GitHub URL: {url}")
    return url[: match.start("owner")] + login + url[match.end("owner") :]


# ── the record of sent changes ────────────────────────────────────────────────


@dataclass
class Proposal:
    """One change sent for review: the branch and, on GitHub, the pull request."""

    branch: str
    base: str
    title: str
    created: str
    repo: str | None = None  # owner/repo on GitHub
    head_repo: str | None = None  # the fork, when the branch is there
    url: str | None = None
    number: int | None = None
    state: str = OPEN
    patch_ids: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        del data["patch_ids"]
        data["fork"] = self.head_repo is not None
        return data


def _state_path(root: Path) -> Path:
    return root / ".git" / STATE_FILE


def read_proposals(root: Path) -> list[Proposal]:
    path = _state_path(root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out: list[Proposal] = []
    for entry in raw if isinstance(raw, list) else []:
        try:
            out.append(Proposal(**entry))
        except TypeError:
            continue
    return out


def write_proposals(root: Path, proposals: Sequence[Proposal]) -> None:
    path = _state_path(root)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps([asdict(p) for p in proposals], indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ── commits and patch ids ─────────────────────────────────────────────────────


def ahead_commits(root: Path, head: str, tip: str | None) -> list[str]:
    """Non-merge commits of `head` that `tip` lacks, oldest first."""
    rng = head if tip is None else f"{tip}..{head}"
    out = git.git(root, "rev-list", "--reverse", "--no-merges", rng)
    return out.split() if out else []


def patch_ids(root: Path, commits: Sequence[str]) -> dict[str, str]:
    """``git patch-id --stable`` of each commit; a commit without changes has none."""
    if not commits:
        return {}
    log = git.run_bytes(
        root, ["log", "-p", "--no-color", "--no-walk=unsorted", "--format=commit %H", *commits]
    )
    if log.returncode != 0:
        raise LibraryStoreError("commit_failed", f"git log: {_git_detail(log)}")
    proc = git.run_bytes(root, ["patch-id", "--stable"], input_bytes=log.stdout)
    out: dict[str, str] = {}
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) == 2:
            out[parts[1]] = parts[0]
    return out


def sent_ids(root: Path) -> set[str]:
    return {pid for p in read_proposals(root) if p.state == OPEN for pid in p.patch_ids}


def unsent_commits(root: Path, head: str, tip: str | None) -> list[str]:
    """Commits ahead of the remote whose change is in no open proposal, oldest first."""
    commits = ahead_commits(root, head, tip)
    ids = patch_ids(root, commits)
    sent = sent_ids(root)
    return [c for c in commits if c in ids and ids[c] not in sent]


def settle(root: Path, head: str, tip: str | None) -> list[Proposal]:
    """Mark proposals whose changes are no longer ahead of the remote as done (merged and
    pulled, or dropped); the proposals still open."""
    proposals = read_proposals(root)
    if not proposals:
        return []
    ahead = set(patch_ids(root, ahead_commits(root, head, tip)).values())
    changed = False
    for p in proposals:
        if p.state == OPEN and p.patch_ids and not ahead & set(p.patch_ids):
            p.state = DONE
            changed = True
    if changed:
        write_proposals(root, proposals)
    return [p for p in proposals if p.state == OPEN]


def transplant(root: Path, base: str, commits: Sequence[str], message: str) -> str:
    """One commit on `base` with the file changes of `commits` (oldest first)."""
    changes: dict[str, git.TreeChange] = {}
    for commit in commits:
        out = git.git(
            root, "diff-tree", "-r", "-z", "--no-renames", "--no-commit-id", "--root", commit
        )
        parts = out.split("\0")
        for i in range(0, len(parts) - 1, 2):
            meta, path = parts[i].split(), parts[i + 1]
            if len(meta) < 5:
                continue
            mode, blob = meta[1], meta[3]
            changes[path] = (path, None, None) if set(blob) == {"0"} else (path, mode, blob)
    return git.commit_tree_with(root, base, list(changes.values()), message)


# ── sending ───────────────────────────────────────────────────────────────────


def _gh(root: Path) -> Any:
    from aifactory.providers.github import GhCli

    return GhCli(root)


def _gh_call(fn: Any, *args: str) -> Any:
    try:
        return fn(*args)
    except ProviderError as exc:
        raise LibraryStoreError(
            "pr_failed", f"cannot open the pull request: {exc.message}; the library is unchanged"
        ) from exc


def push_branch(root: Path, target: str, sha: str, branch: str) -> None:
    """Push `sha` to the new branch `branch` of `target`, never forced and never to the
    library branch: only ``haifa-library/`` branches are pushed."""
    if not branch.startswith(PR_PREFIX):
        raise LibraryStoreError(
            "push_failed", f"refusing to push {branch}: not a {PR_PREFIX} branch"
        )
    proc = git.run_bytes(root, ["push", "--quiet", target, f"{sha}:refs/heads/{branch}"])
    if proc.returncode != 0:
        raise LibraryStoreError(
            "push_failed",
            f"git push {git.redact_url(target)} {branch}: {_git_detail(proc, target)}; "
            "the library is unchanged",
        )


def _branch_name(sha: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{PR_PREFIX}{stamp}-{sha[:8]}"


def _pr_number(url: str) -> int | None:
    match = re.search(r"/pull/(\d+)", url)
    return int(match.group(1)) if match else None


def propose(
    root: Path,
    sha: str,
    base: str,
    message: str,
    ids: Sequence[str],
) -> Proposal:
    """Send `sha` (a commit on the remote `base` tip) for review and record it.

    On GitHub: a branch in the library repo for a user with write access, else in the
    user's fork, and ``gh pr create`` against `base`. Elsewhere only the branch.
    """
    from aifactory.library.remote import remote_url

    url = remote_url(root)
    if url is None:
        raise LibraryStoreError("no_remote", f"the library at {root} has no remote {REMOTE}")
    title = message.strip().splitlines()[0] if message.strip() else "library change"
    body = (
        message.strip()
        + "\n\n---\nSent by HAIFA. The library maintainer reviews and merges this pull "
        "request; HAIFA never merges it.\n"
    )
    branch = _branch_name(sha)
    proposal = Proposal(
        branch=branch,
        base=base,
        title=title,
        created=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        patch_ids=list(ids),
    )
    slug = github_repo(url)
    if slug is None:
        push_branch(root, REMOTE, sha, branch)
    else:
        owner, repo = slug
        gh = _gh(root)
        proposal.repo = f"{owner}/{repo}"
        view = _gh_call(gh.json, "repo", "view", proposal.repo, "--json", "viewerPermission")
        permission = str(view.get("viewerPermission") or "") if isinstance(view, dict) else ""
        head = branch
        if permission.upper() in WRITE_PERMISSIONS:
            push_branch(root, REMOTE, sha, branch)
        else:
            _gh_call(gh.run, "repo", "fork", proposal.repo, "--clone=false", "--remote=false")
            login = str(_gh_call(gh.run, "api", "user", "--jq", ".login")).strip()
            if not login:
                raise LibraryStoreError("pr_failed", "gh api user returned no login")
            proposal.head_repo = f"{login}/{repo}"
            target = fork_url(url, login)
            for attempt in range(FORK_PUSH_ATTEMPTS):
                try:
                    push_branch(root, target, sha, branch)
                    break
                except LibraryStoreError:
                    if attempt == FORK_PUSH_ATTEMPTS - 1:
                        raise
                    time.sleep(FORK_PUSH_DELAY)
            head = f"{login}:{branch}"
        out = _gh_call(
            gh.run,
            "pr",
            "create",
            "--repo",
            proposal.repo,
            "--base",
            base,
            "--head",
            head,
            "--title",
            title,
            "--body",
            body,
        )
        links = [w for w in str(out).split() if w.startswith("http")]
        proposal.url = links[-1] if links else None
        proposal.number = _pr_number(proposal.url or "")
    write_proposals(root, [*read_proposals(root), proposal])
    return proposal


def refresh(root: Path) -> tuple[list[Proposal], str | None]:
    """Ask GitHub which recorded pull requests are still open; (open, error)."""
    from aifactory.library.remote import remote_url

    proposals = read_proposals(root)
    slug = github_repo(remote_url(root))
    if slug is None or not any(p.state == OPEN and p.url for p in proposals):
        return [p for p in proposals if p.state == OPEN], None
    gh = _gh(root)
    try:
        listed = gh.json(
            "pr",
            "list",
            "--repo",
            f"{slug[0]}/{slug[1]}",
            "--author",
            "@me",
            "--state",
            "open",
            "--json",
            "number,url",
            "--limit",
            "200",
        )
    except ProviderError as exc:
        return [p for p in proposals if p.state == OPEN], exc.message
    entries = listed if isinstance(listed, list) else []
    urls = {str(e.get("url")) for e in entries if isinstance(e, dict)}
    changed = False
    for p in proposals:
        if p.state == OPEN and p.url and p.url not in urls:
            p.state = CLOSED
            changed = True
    if changed:
        write_proposals(root, proposals)
    return [p for p in proposals if p.state == OPEN], None


def sync_state(
    remote: str | None, dirty: bool, unsent: int, ahead: int | None, behind: int | None
) -> str:
    """``unshared`` (no remote), ``local`` (changes not sent), ``pending`` (every local
    change waits in a pull request), ``behind`` (the remote has more) or ``synced``."""
    if remote is None:
        return "unshared"
    if dirty or unsent:
        return "local"
    if ahead:
        return "pending"
    if behind:
        return "behind"
    return "synced"
