"""The backlog: a tree of markdown files under ``backlog_dir`` (see ``docs/product-brief.md``).

The tree follows ``levels`` from ``.factory/config.yaml`` (default ``project -> step -> task``).
Every container directory has an ``index.md`` with defaults its tasks inherit; each task is a
markdown file with a YAML header. Reading lives in ``aifactory.backlog.loader`` and never
writes; ``ready``/``blocked`` and reverse links ("blocks") are computed in memory. Task files
and the ``index.md`` of projects and steps are written only by ``aifactory.backlog.edit``
(add/edit/link, validated before writing) and
``aifactory.backlog.taskfile`` (text edits of a single file); ``aifactory.backlog.commit``
commits them to ``base``.
"""

from aifactory.backlog.commit import BacklogCommit, backlog_changes, commit_backlog
from aifactory.backlog.derived import (
    blocks,
    derived_state,
    effective,
    effective_docs_dir,
    effective_sources,
    effective_specs_dir,
    effective_test,
    effective_test_timeout,
    effective_workflow,
    effective_writes,
    has_workflow,
    is_done,
    progress,
    unmet,
)
from aifactory.backlog.edit import (
    CONTAINER_KEYS,
    ContainerWriteResult,
    TaskEditError,
    WriteResult,
    add_container,
    add_task,
    edit_container,
    edit_task,
    find_container,
    find_task,
    link_task,
    load_for_edit,
    set_auto_continue,
    set_auto_merge,
    slugify,
)
from aifactory.backlog.frontmatter import FrontmatterError, parse_frontmatter
from aifactory.backlog.loader import (
    iter_containers,
    iter_nodes,
    iter_tasks,
    load_backlog,
    load_settings,
)
from aifactory.backlog.model import (
    FLAG_KEYS,
    INHERITED_KEYS,
    VALID_STATUSES,
    Backlog,
    Container,
    Issue,
    Node,
    Task,
    Unmet,
)
from aifactory.backlog.render import (
    STATUS_FILTERS,
    backlog_to_json,
    container_detail_json,
    counts,
    format_tree,
    issues_to_json,
    select_projects,
    task_matches,
    task_to_json,
    waits_for,
)
from aifactory.backlog.taskfile import remove_field, set_field
from aifactory.backlog.validate import check_backlog

__all__ = [
    "FLAG_KEYS",
    "INHERITED_KEYS",
    "STATUS_FILTERS",
    "VALID_STATUSES",
    "Backlog",
    "BacklogCommit",
    "Container",
    "FrontmatterError",
    "Issue",
    "Node",
    "Task",
    "TaskEditError",
    "Unmet",
    "WriteResult",
    "add_task",
    "backlog_to_json",
    "blocks",
    "check_backlog",
    "backlog_changes",
    "commit_backlog",
    "counts",
    "derived_state",
    "effective",
    "effective_docs_dir",
    "effective_specs_dir",
    "effective_test",
    "effective_test_timeout",
    "effective_workflow",
    "effective_writes",
    "format_tree",
    "has_workflow",
    "is_done",
    "issues_to_json",
    "iter_containers",
    "iter_nodes",
    "iter_tasks",
    "load_backlog",
    "load_settings",
    "parse_frontmatter",
    "progress",
    "select_projects",
    "unmet",
    "edit_task",
    "find_task",
    "link_task",
    "remove_field",
    "set_field",
    "slugify",
    "task_matches",
    "task_to_json",
    "waits_for",
    "load_for_edit",
    "set_auto_continue",
    "set_auto_merge",
    "ContainerWriteResult",
    "CONTAINER_KEYS",
    "add_container",
    "container_detail_json",
    "edit_container",
    "effective_sources",
    "find_container",
]
