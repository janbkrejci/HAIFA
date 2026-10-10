"""``factory init``: install factory into a repo from the library or the seed.

Writes ``.factory/config.yaml``, ``.factory/agents.yaml``, the prompts and workflows of the
chosen items, ``.factory/manifest.yaml`` with the origin and version of every item, the
backlog directory and the ``.gitignore`` lines. Items come from the HEAD of the library in
the home directory, or from the seed in the package when there is no library; the two are
never mixed. Nothing is committed and nothing is written to the library or ``$HAIFA_HOME``.

A repo whose manifest is committed (HEAD or base) is installed (``already_installed``); a
repo with factory or sssf configuration but no manifest needs onboarding
(``existing_config``). Existing files are skipped unless ``force`` is set.

``Selection``, ``project_settings``, ``build_manifest`` and ``render_files`` are shared
with ``library.install_commit`` (``factory init --dry-run`` and ``--commit``), which
plans the same files and installs them into base with one commit.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import ValidationError

from aifactory import __version__, harness
from aifactory.config.loader import SEED_FALLBACK_AGENTS
from aifactory.config.manifest import (
    MANIFEST_FILE,
    LibraryRef,
    Manifest,
    ManifestEntry,
    ManifestItems,
    Onboarding,
    dump_manifest,
)
from aifactory.config.settings import ProjectSettings
from aifactory.engine.role_registry import Issue, RoleRegistry, load_roles
from aifactory.harness.override import THINKING_LEVELS
from aifactory.library.agent import roster_entry
from aifactory.library.load import load_library_item
from aifactory.library.model import Item, ItemType, LibraryError, check_name
from aifactory.library.seed import (
    SEED_DIR,
    SEED_WORKFLOWS_ROOT,
    seed_agent_names,
    seed_workflow_names,
)
from aifactory.library.store import LibraryStoreError, library_root, read_meta
from aifactory.library.tree import read_items
from aifactory.providers import git
from aifactory.workflow.model import RoleStep, WorkflowError, walk
from aifactory.workflow.parse import parse_workflow

GITIGNORE_LINES = (
    ".factory/data/",
    ".factory/worktrees/",
    ".factory/local.yaml",
    ".factory/trace.db*",
)
DEFAULT_AGENTS = ("planner", "builder", "tester", "reviewer", "documenter")
DEFAULT_WORKFLOWS = ("simple-sdlc",)
SSSF_CONFIG_DIR = "adws/adw_sssf_config"
CONFIG_FILE = ".factory/config.yaml"
AGENTS_FILE = ".factory/agents.yaml"
EXISTING_CONFIG = (CONFIG_FILE, AGENTS_FILE)
_READ_ENV = {"GIT_OPTIONAL_LOCKS": "0"}
FileAction = Literal["created", "skipped", "overwritten"]


@dataclass(frozen=True)
class Binding:
    """One ``--bind AGENT=HARNESS[:MODEL[:THINKING]]``."""

    agent: str
    harness: str
    model: str | None = None
    thinking: str | None = None


def parse_binding(text: str) -> Binding:
    """The binding in ``text``; ``invalid_value`` on a bad form, harness or thinking level."""
    usage = "use AGENT=HARNESS[:MODEL[:THINKING]]"
    agent, sep, rest = text.partition("=")
    agent = agent.strip()
    if not sep or not agent or not rest.strip():
        raise LibraryStoreError("invalid_value", f"--bind {text!r}: {usage}")
    if not check_name(agent):
        raise LibraryStoreError("invalid_value", f"--bind {text!r}: invalid agent name {agent!r}")
    parts = [p.strip() for p in rest.split(":")]
    if len(parts) > 3:
        raise LibraryStoreError("invalid_value", f"--bind {text!r}: {usage}")
    parts += [""] * (3 - len(parts))
    try:
        name = harness.canonical(parts[0])
    except ValueError as exc:
        raise LibraryStoreError("invalid_value", f"--bind {text!r}: {exc}") from exc
    thinking = parts[2] or None
    if thinking is not None and thinking not in THINKING_LEVELS:
        raise LibraryStoreError(
            "invalid_value",
            f"--bind {text!r}: unknown thinking level {thinking!r}, "
            f"available: {list(THINKING_LEVELS)}",
        )
    return Binding(agent=agent, harness=name, model=parts[1] or None, thinking=thinking)


@dataclass(frozen=True)
class WrittenFile:
    path: str
    action: FileAction

    def to_json(self) -> dict[str, str]:
        return {"path": self.path, "action": self.action}


@dataclass(frozen=True)
class InitResult:
    repo: Path
    base: str
    provider: str
    source: Literal["library", "seed"]
    library: LibraryRef | None
    agents: list[str]
    workflows: list[str]
    added_agents: list[str]
    files: list[WrittenFile]
    gitignore_added: list[str]
    manifest: Manifest
    backlog_dir: str
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "repo": str(self.repo),
            "base": self.base,
            "provider": self.provider,
            "source": self.source,
            "library": self.library.model_dump(mode="json") if self.library else None,
            "agents": self.agents,
            "workflows": self.workflows,
            "added_agents": self.added_agents,
            "backlog_dir": self.backlog_dir,
            "files": [f.to_json() for f in self.files],
            "gitignore": {"path": ".gitignore", "added": self.gitignore_added},
            "manifest": self.manifest.to_json(),
        }


# ── git ───────────────────────────────────────────────────────────────────────


def _git_out(root: Path, *args: str) -> str | None:
    proc = git.run_bytes(root, list(args), env=_READ_ENV)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace").strip() or None


def _repo_root(path: Path) -> Path:
    if not path.is_dir():
        raise LibraryStoreError("not_a_repository", f"{path} is not a git repository")
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise LibraryStoreError("not_a_repository", f"{path} is not a git repository")
    return Path(proc.stdout.strip()).resolve()


def _committed(root: Path, ref: str, rel: str) -> bool:
    if git.rev_parse(root, ref) is None:
        return False
    return git.run_bytes(root, ["cat-file", "-e", f"{ref}:{rel}"], env=_READ_ENV).returncode == 0


# ── refusals and names ────────────────────────────────────────────────────────


def _refuse(root: Path, base: str) -> None:
    refs = ["HEAD"] if base == "HEAD" else ["HEAD", base]
    if any(_committed(root, ref, MANIFEST_FILE) for ref in refs):
        raise LibraryStoreError(
            "already_installed",
            f"{MANIFEST_FILE} is committed; the repo is installed, run factory update",
            data={"fix": "factory update"},
        )
    if (root / MANIFEST_FILE).exists():
        return
    found = [rel for rel in EXISTING_CONFIG if (root / rel).exists()]
    if (root / SSSF_CONFIG_DIR).is_dir():
        found.append(SSSF_CONFIG_DIR + "/")
    if found:
        raise LibraryStoreError(
            "existing_config",
            f"the repo has factory configuration without a manifest ({', '.join(found)}); "
            "run factory onboard",
            data={"fix": "factory onboard", "found": found},
        )


def _names(values: Sequence[str], what: str) -> list[str]:
    out: list[str] = []
    for name in values:
        if not check_name(name):
            raise LibraryStoreError("invalid_value", f"invalid {what} name {name!r}")
        if name not in out:
            out.append(name)
    return out


# ── items ─────────────────────────────────────────────────────────────────────


class _Source:
    """Where the items come from: the library HEAD or the seed."""

    def __init__(self, environ: Mapping[str, str] | None) -> None:
        root = library_root(environ)
        head = git.rev_parse(root, "HEAD") if (root / ".git").exists() else None
        self.root: Path | None = root if head is not None else None
        self.head = head
        self.library: LibraryRef | None = None
        if self.root is not None and head is not None:
            from aifactory.library.remote import remote_url

            meta = read_meta(self.root, head)
            if not meta.get("id") or not meta.get("name"):
                raise LibraryStoreError(
                    "invalid_library",
                    f"the library at {self.root} has no valid library.yaml (id, name)",
                )
            self.library = LibraryRef(
                id=str(meta["id"]), name=str(meta["name"]), remote=remote_url(self.root)
            )

    @property
    def kind(self) -> Literal["library", "seed"]:
        return "seed" if self.root is None else "library"

    def load(self, type: ItemType, names: Sequence[str]) -> dict[str, Item]:
        where = "the seed" if self.root is None else f"the library at {self.root}"
        if self.root is None or self.head is None:
            if type not in ("agent", "workflow"):
                missing = names[0] if names else ""
                raise LibraryStoreError("unknown_item", f"no {type} {missing!r} in {where}")
            known = seed_agent_names() if type == "agent" else seed_workflow_names()
            base = SEED_DIR if type == "agent" else SEED_WORKFLOWS_ROOT
            out: dict[str, Item] = {}
            for name in names:
                if name not in known:
                    raise LibraryStoreError("unknown_item", f"no {type} {name!r} in {where}")
                try:
                    out[name] = load_library_item(base, type, name)
                except LibraryError as exc:
                    raise LibraryStoreError(
                        "invalid_item", f"{type} {name!r} in {where} is invalid", issues=exc.issues
                    ) from exc
            return out
        found = read_items(self.root, self.head, [(type, n) for n in names])
        out = {}
        for name in names:
            item, issues, files = found[(type, name)]
            if not files and type == "agent" and name in SEED_FALLBACK_AGENTS:
                continue  # a library from before 3.0: the repo roster falls back to the seed's
            if not files:
                raise LibraryStoreError("unknown_item", f"no {type} {name!r} in {where}")
            if item is None or issues:
                raise LibraryStoreError(
                    "invalid_item", f"{type} {name!r} in {where} is invalid", issues=issues
                )
            out[name] = item
        return out


def _workflow_agents(item: Item, roles: RoleRegistry | None = None) -> list[str]:
    """Agents of the role steps of a workflow item, in step order.

    Roles come from `roles` (the registry of a repo) or the packaged registry; a step
    with ``agent:`` names its agent itself.
    """
    data = item.files[0].data
    try:
        raw = yaml.safe_load(data.decode("utf-8"))
        wf = parse_workflow(raw, roles or load_roles())
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        issue = Issue("invalid_yaml", str(exc), item.name)
        raise LibraryStoreError(
            "invalid_item", f"workflow {item.name!r} is invalid", issues=[issue]
        ) from exc
    except WorkflowError as exc:
        raise LibraryStoreError(
            "invalid_item", f"workflow {item.name!r} is invalid", issues=exc.issues
        ) from exc
    out: list[str] = []
    for step in walk(wf.steps):
        if isinstance(step, RoleStep) and step.role.agent not in out:
            out.append(step.role.agent)
    return out


# ── content ───────────────────────────────────────────────────────────────────


def _agent_entry(item: Item, settings: ProjectSettings, bind: Binding | None) -> dict[str, Any]:
    entry = roster_entry(item, settings)
    if bind is not None:
        changed = bind.harness != entry.get("harness")
        entry["harness"] = bind.harness
        for key, value in (("model", bind.model), ("thinking", bind.thinking)):
            if value is not None:
                entry[key] = value
            elif changed:
                entry.pop(key, None)
    first = ("name", "purpose", "harness", "model", "thinking")
    ordered = {k: entry[k] for k in first if k in entry}
    ordered.update({k: v for k, v in entry.items() if k not in ordered})
    return ordered


def _yaml(header: str, data: Mapping[str, Any]) -> bytes:
    # wide lines: the ruamel round trip of `factory config` (width 4096) rewrites nothing
    body = yaml.safe_dump(dict(data), sort_keys=False, allow_unicode=True, width=4096)
    return (header + body).encode("utf-8")


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gitignore(root: Path) -> list[str]:
    path = root / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    present = {line.strip() for line in text.splitlines()}
    added = [line for line in GITIGNORE_LINES if line not in present]
    if added:
        if text and not text.endswith("\n"):
            text += "\n"
        path.write_text(
            text + "".join(f"{line}\n" for line in added), encoding="utf-8", newline="\n"
        )
    return added


class Selection:
    """The chosen items: workflows add the agents of their steps; bindings per agent."""

    def __init__(
        self,
        source: _Source,
        agents: Sequence[str] | None,
        bindings: Sequence[Binding],
        workflows: Sequence[str] | None,
    ) -> None:
        agent_names = _names(DEFAULT_AGENTS if agents is None else agents, "agent")
        workflow_names = _names(DEFAULT_WORKFLOWS if workflows is None else workflows, "workflow")
        if not agent_names and not workflow_names:
            raise LibraryStoreError(
                "invalid_value", "nothing to install: no agents and no workflows"
            )
        self.source = source
        self.workflow_items = source.load("workflow", workflow_names)
        self.added: list[str] = []
        for name in workflow_names:
            for agent in _workflow_agents(self.workflow_items[name]):
                if agent not in agent_names:
                    agent_names.append(agent)
                    self.added.append(agent)
        self.agent_items = source.load("agent", agent_names)
        agent_names = [n for n in agent_names if n in self.agent_items]
        self.added = [n for n in self.added if n in self.agent_items]
        self.binds: dict[str, Binding] = {}
        for bind in bindings:
            if bind.agent not in agent_names:
                raise LibraryStoreError(
                    "invalid_value",
                    f"--bind {bind.agent}: no agent {bind.agent!r} in {', '.join(agent_names)}",
                )
            self.binds[bind.agent] = bind
        self.agents = agent_names
        self.workflows = workflow_names

    def roster(self, settings: ProjectSettings) -> list[dict[str, Any]]:
        """The ``agents.yaml`` entries, in order."""
        return [_agent_entry(self.agent_items[n], settings, self.binds.get(n)) for n in self.agents]


def project_settings(
    *,
    base: str,
    provider: str,
    azure: Mapping[str, str] | None = None,
    remote: str | None = None,
    backlog_dir: str | None = None,
    specs_dir: str | None = None,
    docs_dir: str | None = None,
) -> ProjectSettings:
    """The settings ``init`` writes; ``invalid_value`` when an option is not allowed."""
    values: dict[str, Any] = {"base": base, "git_provider": provider}
    for key, value in (
        ("remote", remote),
        ("backlog_dir", backlog_dir),
        ("specs_dir", specs_dir),
        ("docs_dir", docs_dir),
        ("azure", dict(azure) if azure is not None else None),
    ):
        if value is not None:
            values[key] = value
    try:
        return ProjectSettings.model_validate(values)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'settings'}: {err['msg']}"
            for err in exc.errors()
        )
        raise LibraryStoreError("invalid_value", f"invalid settings: {problems}") from exc


def build_manifest(root: Path, sel: Selection, at: str) -> Manifest:
    return Manifest(
        written_by=__version__,
        library=sel.source.library,
        onboarding=Onboarding(
            source="init",
            source_commit=git.rev_parse(root, "HEAD"),
            at=at,
            by=_git_out(root, "config", "user.name"),
            factory=__version__,
            library_commit=sel.source.head,
        ),
        items=ManifestItems(
            agents={
                n: ManifestEntry(item=n, version=sel.agent_items[n].version) for n in sel.agents
            },
            workflows={
                n: ManifestEntry(item=n, version=sel.workflow_items[n].version)
                for n in sel.workflows
            },
        ),
    )


def render_files(
    sel: Selection,
    settings: ProjectSettings,
    manifest: Manifest,
    *,
    write_remote: bool = False,
) -> dict[str, bytes]:
    """``.factory/`` as ``init`` writes it: config, roster, prompts, workflows, manifest."""
    config: dict[str, Any] = {"base": settings.base, "git_provider": settings.git_provider}
    if write_remote:
        config["remote"] = settings.remote
    config.update(
        {
            "backlog_dir": settings.backlog_dir,
            "specs_dir": settings.specs_dir,
            "docs_dir": settings.docs_dir,
        }
    )
    if settings.azure is not None:
        config["azure"] = settings.azure.model_dump(mode="json")
    files: dict[str, bytes] = {}
    files[CONFIG_FILE] = _yaml("# factory project settings, written by factory init\n", config)
    library = sel.source.library
    files[AGENTS_FILE] = _yaml(
        "# agents of this repo, written by factory init from "
        + ("the seed" if library is None else f"the library {library.name}")
        + "\n",
        {"agents": sel.roster(settings)},
    )
    for name in sel.agents:
        for prompt in ("system.md", "user.md"):
            found = sel.agent_items[name].file(prompt)
            files[f".factory/prompts/{name}/{prompt}"] = found.data if found else b""
    for name in sel.workflows:
        files[f".factory/workflows/{name}.yaml"] = sel.workflow_items[name].files[0].data
    files[MANIFEST_FILE] = dump_manifest(manifest).encode("utf-8")
    return files


def init_repo(
    path: Path,
    *,
    base: str | None = None,
    provider: Literal["local", "github", "azure"] = "local",
    azure: Mapping[str, str] | None = None,
    agents: Sequence[str] | None = None,
    bindings: Sequence[Binding] = (),
    workflows: Sequence[str] | None = None,
    backlog_dir: str | None = None,
    specs_dir: str | None = None,
    docs_dir: str | None = None,
    force: bool = False,
    environ: Mapping[str, str] | None = None,
) -> InitResult:
    """Install factory into the git repo at `path`; see the module docstring."""
    root = _repo_root(path)
    if base is None:
        base = _git_out(root, "symbolic-ref", "--quiet", "--short", "HEAD")
        if base is None:
            raise LibraryStoreError("invalid_value", "HEAD is detached; pass --base")
    elif not base.strip():
        raise LibraryStoreError("invalid_value", "--base must not be empty")
    _refuse(root, base)
    settings = project_settings(
        base=base,
        provider=provider,
        azure=azure,
        backlog_dir=backlog_dir,
        specs_dir=specs_dir,
        docs_dir=docs_dir,
    )
    sel = Selection(_Source(environ), agents, bindings, workflows)
    manifest = build_manifest(root, sel, _now())
    files = render_files(sel, settings, manifest)
    files[f"{settings.backlog_dir.rstrip('/')}/.gitkeep"] = b""

    written: list[WrittenFile] = []
    for rel, data in files.items():
        target = root / rel
        if target.exists() and not force:
            written.append(WrittenFile(rel, "skipped"))
            continue
        action: FileAction = "overwritten" if target.exists() else "created"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written.append(WrittenFile(rel, action))
    gitignore_added = _gitignore(root)

    skipped = sum(1 for f in written if f.action == "skipped")
    warnings = [f"{skipped} existing file(s) skipped; use --force to overwrite"] if skipped else []
    return InitResult(
        repo=root,
        base=base,
        provider=provider,
        source=sel.source.kind,
        library=sel.source.library,
        agents=sel.agents,
        workflows=sel.workflows,
        added_agents=sel.added,
        files=written,
        gitignore_added=gitignore_added,
        manifest=manifest,
        backlog_dir=settings.backlog_dir,
        warnings=warnings,
    )
