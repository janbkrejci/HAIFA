"""Local fixtures and a remote publication proof for the two-machine team flow."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

from fake_exe import make_executable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "onboard"))
from onboard_repo import (  # noqa: E402
    SSSF_PROMPTS,
    SSSF_QUALITY,
    commit_all,
    git,
    patch_omnibus,
    sssf_repo,
    write,
)

__all__ = [
    "EXPORT_MARKER",
    "SKILL_DESCRIPTION",
    "TASK",
    "commit_all",
    "git",
    "publication_hook",
    "team_repo",
    "team_script",
    "write",
]

TASK = "P-S01-T01"
SKILL_DESCRIPTION = "Check the team's deterministic acceptance rules."
ONBOARD_MARKER = "Team onboarding acceptance rule: preserve shared contracts."
EXPORT_MARKER = "Team version from machine B: verify handover contracts."


def team_repo(root: Path) -> Path:
    repo = sssf_repo(root, "legacy", origin=True)
    patch_omnibus(repo)
    prompt = repo / SSSF_PROMPTS / "builder/system.md"
    prompt.write_text(prompt.read_text(encoding="utf-8") + "\n" + ONBOARD_MARKER + "\n")
    quality = repo / SSSF_QUALITY
    text = quality.read_text(encoding="utf-8")
    quality.write_text(
        text.replace('argv=["just", "test"],', f"argv={[sys.executable, '-c', 'pass']!r},")
    )
    write(repo, "backlog/P/index.md", "---\nid: P\ntitle: Team\n---\n")
    write(repo, "backlog/P/S01/index.md", "---\nid: P-S01\ntitle: Handover\n---\n")
    write(
        repo,
        "backlog/P/S01/P-S01-T01-team.md",
        f"---\nid: {TASK}\ntitle: Team feature\nstatus: todo\nworkflow: simple-sdlc\n"
        "writes: [src/app/]\n---\n"
        "\n## Zadání\nAdd src/app/team.py. Allowed paths: src/app/, specs/, app_docs/.\n",
    )
    commit_all(repo, "Prepare team fixture")
    git(repo, "push", "origin", "main")
    return repo


def team_script(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "agents": {
                    "planner": [
                        {
                            "edits": [{"path": "@output", "write": "# Team plan\nAdd team.py.\n"}],
                            "envelope": {
                                "status": "success",
                                "summary": "Plan team feature",
                                "artifacts": ["@output"],
                                "plan_path": "@output",
                            },
                        }
                    ],
                    "reviewer": [
                        {
                            "envelope": {
                                "status": "success",
                                "summary": "Team feature matches plan",
                                "approved": True,
                                "findings": [
                                    {
                                        "requirement": "Team feature",
                                        "met": True,
                                        "evidence": "src/app/team.py",
                                    }
                                ],
                                "blocking": [],
                            }
                        }
                    ],
                    "documenter": [
                        {
                            "edits": [
                                {"path": "@output", "write": "# Team feature\nAdded team.py.\n"}
                            ],
                            "envelope": {
                                "status": "success",
                                "summary": "Document team feature",
                                "artifacts": ["@output"],
                                "document_path": "@output",
                                "commit_message": "Document team feature",
                            },
                        }
                    ],
                    "builder": [
                        {
                            "edits": [{"path": "src/app/team.py", "write": "TEAM = True\n"}],
                            "envelope": {
                                "status": "success",
                                "summary": "Build team feature",
                                "changed_files": ["src/app/team.py"],
                                "artifacts": [],
                                "commit_message": "Add team feature",
                            },
                        }
                    ],
                }
            },
        ),
        encoding="utf-8",
    )
    return path


def publication_hook(remote: Path, library: Path, proof: Path) -> Path:
    """Reject the onboarding push unless its builder is already in library remote main."""
    baseline = git(library, "rev-parse", "main")
    script = remote.parent / "publication-proof.py"
    script.write_text(
        "import json, os, subprocess, sys\nfrom pathlib import Path\nimport yaml\n"
        "from aifactory.library.model import Item, ItemFile\n"
        "def repo_git(*args):\n"
        "    return subprocess.check_output(['git', *args], text=True).strip()\n"
        "env = {k:v for k,v in os.environ.items() if not k.startswith('GIT_')\n"
        "       or k in ('GIT_CONFIG_GLOBAL', 'GIT_CONFIG_NOSYSTEM')}\n"
        f"library = {str(library)!r}\n"
        "def lib_git(*args):\n"
        "    return subprocess.check_output(['git', '--git-dir', library, *args], env=env)\n"
        "for line in sys.stdin:\n"
        "    old, new, ref = line.split()\n"
        "    if ref != 'refs/heads/main': continue\n"
        "    manifest = yaml.safe_load(repo_git('show', new + ':.factory/manifest.yaml'))\n"
        "    if manifest['onboarding']['source_commit'] != old: continue\n"
        "    head = lib_git('rev-parse', 'main').decode().strip()\n"
        f"    assert head != {baseline!r}, 'library was not published first'\n"
        "    entry = manifest['items']['agents']['builder']\n"
        "    prefix = 'agents/' + entry['item'] + '/'\n"
        "    files = []\n"
        "    for row in lib_git('ls-tree', '-r', head, prefix).decode().splitlines():\n"
        "        meta, path = row.split('\\t'); mode, kind, oid = meta.split()\n"
        "        data = lib_git('cat-file', 'blob', oid)\n"
        "        files.append(ItemFile(path[len(prefix):], mode == '100755', data))\n"
        "    agent = next(f.data for f in files if f.path == 'agent.yaml')\n"
        "    purpose = yaml.safe_load(agent)['purpose']\n"
        "    item = Item('agent', entry['item'], tuple(files), purpose)\n"
        "    assert item.version == entry['version'], 'builder version not yet published'\n"
        f"    assert {ONBOARD_MARKER.encode()!r} in item.file('system.md').data\n"
        "    evidence = {'repo': new, 'library': head, 'entry': entry}\n"
        f"    Path({str(proof)!r}).write_text(json.dumps(evidence))\n",
        encoding="utf-8",
    )
    hook = remote / "hooks/pre-receive"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(
        f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(script))}\n",
        encoding="utf-8",
    )
    return make_executable(hook)
