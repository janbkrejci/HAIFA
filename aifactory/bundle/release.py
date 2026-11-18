"""Stamp a unique CI build version into the wheel before building its bundle."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from bundle.build import PROJECT, version


def check_transition() -> None:
    """Fail closed on the preserved HAIFA source, before build and before publication."""
    env = os.environ
    if (
        env.get("GITHUB_REPOSITORY") != "janbkrejci/HAIFA"
        or env.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or env.get("GITHUB_REF") != "refs/tags/haifa-transition-acl-source"
        or not re.fullmatch(r"[0-9a-f]{40}", env.get("HAIFA_TRANSITION_HOTFIX_SHA", ""))
        or env.get("GITHUB_SHA") != env.get("HAIFA_TRANSITION_HOTFIX_SHA")
        or env.get("HAIFA_TRANSITION_HOTFIX_PUBLISHED") != "false"
    ):
        raise ValueError("Only the approved, unpublished HAIFA transition source may publish")
    # The ACL hotfix is a descendant of the retained, already published HAIFA.
    # Never reset the original publication marker to authorize a second release.
    original = env.get("HAIFA_TRANSITION_SHA", "")
    if (
        not re.fullmatch(r"[0-9a-f]{40}", original)
        or env.get("HAIFA_TRANSITION_PUBLISHED") != "true"
    ):
        raise ValueError("The original HAIFA transition release must remain published")
    subprocess.run(["git", "merge-base", "--is-ancestor", original, env["GITHUB_SHA"]], check=True)
    retained = subprocess.run(
        ["git", "ls-remote", "--tags", "origin", "refs/tags/haifa-transition-published"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    if retained != [original, "refs/tags/haifa-transition-published"]:
        raise ValueError("The original HAIFA publication marker must match its approved source")
    published = subprocess.run(
        ["git", "ls-remote", "--tags", "origin", "refs/tags/haifa-transition-acl-published"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if published:
        raise ValueError("The final HAIFA has already been published")
    release = json.loads(
        subprocess.run(
            ["gh", "api", "repos/janbkrejci/GIRO/releases/latest"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    tag = release.get("tag_name", "")
    if not re.fullmatch(r"v1\.\d+\.\d+", tag) or release.get("draft") or release.get("prerelease"):
        raise ValueError("A stable GIRO 1.x release must be available first")
    name = f"giro-{tag[1:]}.zip"
    url = f"https://github.com/janbkrejci/GIRO/releases/download/{tag}/{name}"
    if (
        sum(
            a.get("name") == name and a.get("browser_download_url") == url
            for a in release.get("assets", [])
        )
        != 1
    ):
        raise ValueError("The stable GIRO release must contain its canonical bundle")
    previous = json.loads(
        subprocess.run(
            ["gh", "api", "repos/janbkrejci/HAIFA/releases/latest"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )["tag_name"].removeprefix("v")
    target = f"0.1.{int(env['GITHUB_RUN_NUMBER'])}"

    def key(value: str) -> tuple[int, ...]:
        return tuple(int(n) for n in value.split("."))

    if not re.fullmatch(r"0\.1\.\d+", previous) or key(target) <= key(previous):
        raise ValueError("The final HAIFA version must exceed the previous HAIFA release")


def stamp(run_number: int, repository: str, project: Path = PROJECT) -> str:
    if run_number < 1:
        raise ValueError("CI run number must be positive")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("give the GitHub release repository as owner/name")
    major, minor, _ = version(project).split(".")
    target = f"{major}.{minor}.{run_number}"
    init = project / "src/aifactory/__init__.py"
    init.write_text(
        re.sub(r"^__version__ = .*$", f'__version__ = "{target}"', init.read_text(), flags=re.M),
        encoding="utf-8",
    )
    updates = project / "src/aifactory/web/updates.py"
    updates.write_text(
        re.sub(
            r"^UPDATE_REPOSITORY = .*$",
            f'UPDATE_REPOSITORY = "{repository}"',
            updates.read_text(),
            flags=re.M,
        ),
        encoding="utf-8",
    )
    return target


if __name__ == "__main__":
    if sys.argv[1:] == ["--check-transition"]:
        check_transition()
    else:
        print(stamp(int(os.environ["GITHUB_RUN_NUMBER"]), os.environ["GITHUB_REPOSITORY"]))
