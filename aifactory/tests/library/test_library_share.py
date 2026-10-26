"""The default library and library changes as pull requests only (HAIFA-S05-T17).

No network: the GitHub URLs of the library and of the fork are mapped onto bare repos on
disk with ``url.<path>.insteadOf`` and ``gh`` is a fake that logs its calls. The bare
library repo rejects every push to ``main`` and logs every updated ref, so a direct push
would fail the test twice.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from library_tree import put, skill_files

from aifactory.library import share, store
from cli_json import run_json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "providers"))

from gh_fake import GhLog, install_fake_gh, prepare_shared_gh, reply  # noqa: E402

Capsys = pytest.CaptureFixture[str]
UPSTREAM = "https://github.com/janbkrejci/HAIFA-LIBRARY.git"
FORK = "https://github.com/ada/HAIFA-LIBRARY.git"
PR_URL = "https://github.com/janbkrejci/HAIFA-LIBRARY/pull/7"
HOOK = """#!/bin/sh
echo "$1" >> "{log}"
if [ "$1" = "refs/heads/main" ]; then
    echo "direct push to main" >&2
    exit 1
fi
"""


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, encoding="utf-8"
    )
    return out.stdout.strip()


@pytest.fixture(scope="module")
def _shared_gh(tmp_path_factory: pytest.TempPathFactory) -> None:
    prepare_shared_gh(tmp_path_factory.mktemp("ghwarm"))


class Env:
    def __init__(self, tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tmp = tmp
        self.mp = monkeypatch
        self.user = tmp / "home"
        self.user.mkdir()
        monkeypatch.setenv("HOME", str(self.user))
        monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
        monkeypatch.delenv("HAIFA_LIBRARY_URL", raising=False)
        monkeypatch.setattr(share, "FORK_PUSH_DELAY", 0.0)
        for kind in ("AUTHOR", "COMMITTER"):
            monkeypatch.setenv(f"GIT_{kind}_NAME", "Ada Tester")
            monkeypatch.setenv(f"GIT_{kind}_EMAIL", "ada@example.com")
        self.bare = tmp / "upstream.git"
        self.fork = tmp / "fork.git"
        for bare in (self.bare, self.fork):
            _git(tmp, "init", "--bare", "--quiet", "-b", "main", str(bare))
        monkeypatch.setenv("GIT_CONFIG_COUNT", "2")
        for n, (path, url) in enumerate(((self.bare, UPSTREAM), (self.fork, FORK))):
            monkeypatch.setenv(f"GIT_CONFIG_KEY_{n}", f"url.{path}.insteadOf")
            monkeypatch.setenv(f"GIT_CONFIG_VALUE_{n}", url)
        self.pushed = tmp / "pushed.log"

    def use(self, name: str) -> Path:
        home = self.user / name
        self.mp.setenv("HAIFA_HOME", str(home))
        return home / "library"

    def guard_main(self) -> None:
        """From now on the library repo refuses and logs a push to main."""
        hooks = self.tmp / "hooks"
        hooks.mkdir(exist_ok=True)
        hook = hooks / "update"
        hook.write_text(HOOK.format(log=self.pushed.as_posix()), encoding="utf-8", newline="\n")
        hook.chmod(0o755)
        _git(self.bare, "config", "core.hooksPath", str(hooks))

    def pushed_refs(self) -> list[str]:
        if not self.pushed.exists():
            return []
        return self.pushed.read_text(encoding="utf-8").split()

    def skill(self, name: str) -> list[str]:
        folder = self.user / "work" / name
        for rel, (data, executable) in skill_files(name).items():
            put(folder, rel, data, executable=executable)
        return ["library", "import", str(folder), "--type", "skill", "--json"]


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    return Env(tmp_path, monkeypatch)


def _ok(capsys: Capsys, argv: list[str]) -> dict[str, Any]:
    rc, obj = run_json(capsys, argv)
    assert rc == 0, obj
    data: dict[str, Any] = obj["data"]
    return data


def _fail(capsys: Capsys, argv: list[str]) -> dict[str, Any]:
    rc, obj = run_json(capsys, argv)
    assert rc == 2, obj
    error: dict[str, Any] = obj["error"]
    return error


def _published(env: Env, capsys: Capsys) -> Path:
    """The maintainer publishes the library to the upstream repo; the user clones it with
    the default URL. The user's library path."""
    env.use("maintainer")
    _ok(capsys, ["library", "init", "--name", "haifa", "--remote", str(env.bare), "--json"])
    env.guard_main()
    lib = env.use("user")
    cloned = _ok(capsys, ["library", "clone", "--json"])
    assert cloned["remote"] == UPSTREAM and cloned["sync_state"] == "synced"
    return lib


def _no_merge(log: GhLog) -> None:
    for argv in log.argvs():
        assert argv[:2] not in (["pr", "merge"], ["pr", "review"]), argv
        assert "--admin" not in argv and "--auto" not in argv, argv
        assert not (argv[:1] == ["api"] and any("merge" in a or "review" in a for a in argv))


def test_default_url_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAIFA_LIBRARY_URL", raising=False)
    assert share.default_library_url() == share.DEFAULT_LIBRARY_URL == UPSTREAM
    assert share.default_library_url({"HAIFA_LIBRARY_URL": " git@corp:t/lib.git "}) == (
        "git@corp:t/lib.git"
    )
    assert share.github_repo(UPSTREAM) == ("janbkrejci", "HAIFA-LIBRARY")
    assert share.github_repo("git@github.com:o/r.git") == ("o", "r")
    assert share.github_repo("https://dev.azure.com/o/p/_git/r") is None
    assert share.fork_url(UPSTREAM, "ada") == FORK
    assert share.fork_url("git@github.com:o/r.git", "ada") == "git@github.com:ada/r.git"


def test_clone_without_url_uses_the_default_library(env: Env, capsys: Capsys) -> None:
    lib = _published(env, capsys)
    assert _git(lib, "rev-parse", "HEAD") == _git(env.bare, "rev-parse", "main")
    assert _git(lib, "config", "--get", "remote.origin.url") == UPSTREAM
    assert _fail(capsys, ["library", "clone", "--seed-fallback", "--json"])["code"] == (
        "library_exists"
    )


def test_clone_url_from_the_environment(env: Env, capsys: Capsys) -> None:
    env.use("maintainer")
    _ok(capsys, ["library", "init", "--remote", str(env.bare), "--json"])
    env.mp.setenv("HAIFA_LIBRARY_URL", str(env.bare))
    env.use("user")
    assert _ok(capsys, ["library", "clone", "--json"])["remote"] == str(env.bare)


def test_seed_fallback_without_network(env: Env, capsys: Capsys) -> None:
    env.mp.setenv("HAIFA_LIBRARY_URL", str(env.tmp / "unreachable.git"))
    lib = env.use("offline")
    assert _fail(capsys, ["library", "clone", "--json"])["code"] == "clone_failed"
    assert not lib.exists()
    rc, obj = run_json(capsys, ["library", "clone", "--seed-fallback", "--json"])
    assert rc == 0, obj
    assert obj["data"]["fallback"] is True and obj["data"]["remote"] is None
    assert any("from the seed" in w for w in obj["warnings"])
    assert (lib / "library.yaml").is_file()
    head = _git(lib, "rev-parse", "HEAD")
    assert _fail(capsys, ["library", "clone", "--seed-fallback", "--json"])["code"] == (
        "library_exists"
    )
    assert _git(lib, "rev-parse", "HEAD") == head


@pytest.mark.usefixtures("_shared_gh")
def test_writer_sends_a_pull_request_from_a_branch(
    env: Env, capsys: Capsys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lib = _published(env, capsys)
    main = _git(env.bare, "rev-parse", "main")
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {
            "repo view": reply({"viewerPermission": "ADMIN"}),
            "pr create": reply(PR_URL + "\n"),
            "pr list": reply([{"number": 7, "url": PR_URL}]),
        },
    )
    data = _ok(capsys, env.skill("lint"))
    pr = data["pull_request"]
    assert pr["url"] == PR_URL and pr["number"] == 7 and pr["fork"] is False
    assert pr["repo"] == "janbkrejci/HAIFA-LIBRARY" and pr["base"] == "main"
    assert _git(env.bare, "rev-parse", pr["branch"]) == data["commit"]
    assert _git(env.bare, "rev-parse", "main") == main
    assert _git(lib, "rev-parse", "HEAD") == data["commit"]  # usable before the merge
    create = next(a for a in log.argvs() if a[:2] == ["pr", "create"])
    assert create[create.index("--repo") + 1] == "janbkrejci/HAIFA-LIBRARY"
    assert create[create.index("--base") + 1] == "main"
    assert create[create.index("--head") + 1] == pr["branch"]
    assert not any(a[:2] == ["repo", "fork"] for a in log.argvs())

    status = _ok(capsys, ["library", "status", "--fetch", "--json"])
    assert status["sync_state"] == "pending"
    assert [p["url"] for p in status["pull_requests"]] == [PR_URL]
    log.respond("pr list", reply([]))  # the maintainer closed it without merging
    status = _ok(capsys, ["library", "status", "--fetch", "--json"])
    assert status["sync_state"] == "local" and status["pull_requests"] == []
    _no_merge(log)
    assert "refs/heads/main" not in env.pushed_refs()


@pytest.mark.usefixtures("_shared_gh")
def test_reader_sends_a_pull_request_from_a_fork(
    env: Env, capsys: Capsys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _published(env, capsys)
    main = _git(env.bare, "rev-parse", "main")
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {
            "repo view": reply({"viewerPermission": "READ"}),
            "repo fork": reply(""),
            "api user": reply("ada\n"),
            "pr create": reply(PR_URL + "\n"),
        },
    )
    data = _ok(capsys, env.skill("lint"))
    pr = data["pull_request"]
    assert pr["fork"] is True and pr["head_repo"] == "ada/HAIFA-LIBRARY"
    assert _git(env.fork, "rev-parse", pr["branch"]) == data["commit"]
    assert _git(env.bare, "for-each-ref", "refs/heads/haifa-library/") == ""
    assert _git(env.bare, "rev-parse", "main") == main
    fork = next(a for a in log.argvs() if a[:2] == ["repo", "fork"])
    assert fork[2] == "janbkrejci/HAIFA-LIBRARY" and "--clone=false" in fork
    assert not any(arg.startswith("--remote") for arg in fork), fork
    create = next(a for a in log.argvs() if a[:2] == ["pr", "create"])
    assert create[create.index("--head") + 1] == f"ada:{pr['branch']}"
    assert create[create.index("--repo") + 1] == "janbkrejci/HAIFA-LIBRARY"
    _no_merge(log)
    assert env.pushed_refs() == []


@pytest.mark.usefixtures("_shared_gh")
def test_main_of_the_library_is_never_pushed(
    env: Env, capsys: Capsys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lib = _published(env, capsys)
    main = _git(env.bare, "rev-parse", "main")
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {"repo view": reply({"viewerPermission": "WRITE"}), "pr create": reply(PR_URL)},
    )
    _ok(capsys, env.skill("lint"))
    put(lib, "notes.md", "local\n")
    _git(lib, "add", "notes.md")
    _git(lib, "commit", "--quiet", "-m", "local note")
    pushed = _ok(capsys, ["library", "push", "--json"])
    assert pushed["pushed"] == 1 and pushed["pull_request"]["url"] == PR_URL
    # the second pull request holds only the unsent commit
    branch = pushed["pull_request"]["branch"]
    files = _git(env.bare, "ls-tree", "-r", "--name-only", branch).split()
    assert "notes.md" in files and "skills/lint/SKILL.md" not in files
    assert _ok(capsys, ["library", "push", "--json"])["pull_request"] is None
    refs = env.pushed_refs()
    assert refs and all(r.startswith("refs/heads/haifa-library/") for r in refs)
    assert _git(env.bare, "rev-parse", "main") == main
    _no_merge(log)
    # the guard itself: a direct push to main is refused and logged
    direct = subprocess.run(["git", "push", "--quiet", "origin", "HEAD:main"], cwd=lib)
    assert direct.returncode != 0 and env.pushed_refs()[-1] == "refs/heads/main"


@pytest.mark.usefixtures("_shared_gh")
def test_failed_pull_request_changes_nothing(
    env: Env, capsys: Capsys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lib = _published(env, capsys)
    head = _git(lib, "rev-parse", "HEAD")
    install_fake_gh(
        tmp_path,
        monkeypatch,
        {
            "repo view": reply({"viewerPermission": "WRITE"}),
            "pr create": reply(exit=1, stderr="no auth"),
        },
    )
    error = _fail(capsys, env.skill("lint"))
    assert error["code"] == "pr_failed" and "no auth" in error["message"]
    assert _git(lib, "rev-parse", "HEAD") == head
    assert _git(lib, "status", "--porcelain") == ""
    assert "refs/heads/main" not in env.pushed_refs()


def test_push_branch_refuses_the_library_branch(env: Env) -> None:
    lib = env.tmp / "repo"
    _git(env.tmp, "init", "--quiet", "-b", "main", str(lib))
    with pytest.raises(store.LibraryStoreError) as exc:
        share.push_branch(lib, str(env.bare), "0" * 40, "main")
    assert exc.value.code == "push_failed"
