"""What ``factory init`` finds in a repository before it plans anything (no network).

* remote: ``origin`` when it exists, else the first remote by name, else none;
* base: the branch ``refs/remotes/<remote>/HEAD`` points to (``base_source: remote_head``),
  else the current branch (``branch``), else none (a detached HEAD);
* provider from the remote URL (``parse_remote_url``): ``github`` for github.com in the
  https, ssh and scp forms; ``azure`` for dev.azure.com, ssh.dev.azure.com and
  ``*.visualstudio.com`` with organization, project and repository; ``local`` otherwise
  and without a remote;
* which harness CLIs are on PATH (they are not run).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

from aifactory import harness
from aifactory.harness.check import installed_path
from aifactory.providers import git

Provider = Literal["local", "github", "azure"]
_READ_ENV = {"GIT_OPTIONAL_LOCKS": "0"}
# user@host:path, but not a Windows drive (C:\x) and not a path with a slash before the colon
_SCP = re.compile(r"^(?:(?P<user>[^@/:]+)@)?(?P<host>[^@/:]+):(?P<path>[^\\].*)$")


@dataclass(frozen=True)
class RemoteInfo:
    """The hosting a remote URL points to."""

    provider: Provider
    github: dict[str, str] | None = None  # {owner, repo}
    azure: dict[str, str] | None = None  # {organization, project, repository}


_LOCAL = RemoteInfo("local")


def _host_path(url: str) -> tuple[str, str] | None:
    text = url.strip()
    if "://" in text:
        parts = urlsplit(text)
        if not parts.hostname:
            return None
        return parts.hostname.lower(), parts.path
    match = _SCP.match(text)
    if match is None or len(match.group("host")) < 2:
        return None
    return match.group("host").lower(), match.group("path")


def _segments(path: str) -> list[str]:
    return [unquote(s) for s in path.strip("/").split("/") if s]


def _azure(org: str, project: str, repo: str) -> RemoteInfo:
    if not (org and project and repo):
        return _LOCAL
    return RemoteInfo("azure", azure={"organization": org, "project": project, "repository": repo})


def parse_remote_url(url: str | None) -> RemoteInfo:
    """The provider of a remote URL; ``local`` for anything it does not recognise."""
    if not url:
        return _LOCAL
    found = _host_path(url)
    if found is None:
        return _LOCAL
    host, path = found
    segs = _segments(path)
    if host in ("github.com", "www.github.com"):
        if len(segs) != 2:
            return _LOCAL
        owner, repo = segs
        repo = repo.removesuffix(".git")
        return RemoteInfo("github", github={"owner": owner, "repo": repo}) if repo else _LOCAL
    if host == "dev.azure.com":
        if len(segs) == 4 and segs[2] == "_git":
            return _azure(segs[0], segs[1], segs[3])
        return _LOCAL
    if host == "ssh.dev.azure.com" or (host.startswith("vs-ssh.") and _visualstudio(host)):
        if len(segs) == 4 and segs[0] == "v3":
            return _azure(segs[1], segs[2], segs[3])
        return _LOCAL
    if _visualstudio(host):
        org = host.split(".", 1)[0]
        if len(segs) == 4 and segs[0].lower() == "defaultcollection":
            segs = segs[1:]
        if len(segs) == 3 and segs[1] == "_git":
            return _azure(org, segs[0], segs[2])
        return _LOCAL
    return _LOCAL


def _visualstudio(host: str) -> bool:
    return host.endswith(".visualstudio.com") and host.count(".") == 2


@dataclass(frozen=True)
class Detected:
    remote: str | None
    remote_url: str | None
    base: str | None
    base_source: Literal["remote_head", "branch"] | None
    info: RemoteInfo
    harnesses: dict[str, str | None] = field(default_factory=dict)

    @property
    def provider(self) -> Provider:
        return self.info.provider

    def to_json(self) -> dict[str, Any]:
        return {
            "remote": self.remote,
            "remote_url": git.redact_url(self.remote_url) if self.remote_url else None,
            "base": self.base,
            "base_source": self.base_source,
            "provider": self.info.provider,
            "github": self.info.github,
            "azure": self.info.azure,
            "harnesses": {
                name: {"installed": path is not None, "path": path}
                for name, path in self.harnesses.items()
            },
        }


def _out(root: Path, *args: str) -> str | None:
    proc = git.run_bytes(root, list(args), env=_READ_ENV)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace").strip() or None


def main_remote(root: Path) -> str | None:
    """``origin`` when it exists, else the first remote by name, else None."""
    names = sorted((_out(root, "remote") or "").split())
    if not names:
        return None
    return "origin" if "origin" in names else names[0]


def detect(root: Path) -> Detected:
    """Remote, base, provider and installed harnesses of the repo at `root`."""
    remote = main_remote(root)
    url = git.remote_url(root, remote) if remote else None
    base: str | None = None
    source: Literal["remote_head", "branch"] | None = None
    if remote is not None:
        head = _out(root, "symbolic-ref", "--quiet", f"refs/remotes/{remote}/HEAD")
        prefix = f"refs/remotes/{remote}/"
        if head and head.startswith(prefix) and head != prefix:
            base, source = head.removeprefix(prefix), "remote_head"
    if base is None:
        current = _out(root, "symbolic-ref", "--quiet", "--short", "HEAD")
        if current:
            base, source = current, "branch"
    return Detected(
        remote=remote,
        remote_url=url,
        base=base,
        base_source=source,
        info=parse_remote_url(url),
        harnesses={name: installed_path(name) for name in harness.CLI_BINARIES},
    )
