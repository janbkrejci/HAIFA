# Backlog and tasks

The backlog is a markdown tree under `<docs_root>/backlog/`: **project**, **step**, **task** according to `levels`; container defaults live in `index.md`, task IDs use `<step>-<code>` (e.g. `WEB-S01-T01`).

## Tree and kanban <!-- section:strom-a-kanban -->

The project filter is shared by tree and kanban; the browser remembers it per repository.

**Archive**/**Restore** stores `archived: true/false` in front matter; this is committed. With no value, `cancelled` means archived and other statuses mean unarchived. The column toggle shows archived items.

**Tree**: projects, steps, task counts, dependency graph and **Settings** (sliders): `index.md` keys.

**Kanban** groups statuses; drag or use arrows to order **Ready** tasks for auto continue from top to bottom. **Deferred** (by dragging or **Exclude from auto continue**) removes a task from the queue; manual runs remain possible. Ordering and deferral are not committed.

## Task states <!-- section:stavy-tasku -->

**No workflow**, **Ready**, **For a person** (`assignee: human`), **Blocked** (unfinished dependency; **Waiting for a person** for a human task), **Failed**, **Running**, **Awaiting review**, **Approved, awaiting CI**, **Awaiting PR automerge**, **Done** and **Cancelled**.

The file stores only `status` (`todo`, `done`, `cancelled`). PR approval marks it done; for a human task, use **Done** in task details. Create one with `factory task add STEP TITLE --assignee human`.

## Details and form <!-- section:detail-a-formular -->

Task details: **Run**, **Edit**, **Cancel**, **Improve with agent** (and **Done** for a human task), plus **Description** (description and read-only documents), **Runs**, **PR**, **Settings** (workflow, writes) and **Relations** tabs.

Completed tasks cannot run again: **Continue with follow-up** (`factory task follow-up ID --body TEXT --run`) creates a task in the same step with `follows: ID`, its own writes and the original workflow; **Commit and run** starts it. Details show predecessors and follow-ups.

Form: **Title**, **Code**, **Description** (goal, context, completion criteria), **Workflow** and **Suggest workflow**. **More settings**: **Status**, **Writes** (allowed paths), **Depends on**, **Related** and test timeout. **Improve with agent** fills in the description, writes, relations and workflow. Both follow the [helper agent settings](#/guide/prvni-beh/harnessy-tohoto-pocitace).

**New intent** proposes a backlog for refinement and application. It uses the same local helper agent settings.

## Inheritance <!-- section:dedicnost -->

Empty values are inherited from the step, then project: `workflow`, `writes`, `test_timeout`, `auto_heal`, `assignee`. Explicit `null` stops inheritance. Edit projects and steps with **Settings** or `factory backlog edit`.

`depends_on` references a task, step or project (satisfied when all non-cancelled tasks are done).

## Committing the backlog <!-- section:commit-backlogu -->

Edits are written to the working tree, but **runs read the backlog from base**. Commit using the **Uncommitted backlog** icon or `factory backlog commit`. After manual file edits, run `factory backlog check`.

Legacy `auto_continue`, `auto_merge` and `harness/model/thinking` remain readable metadata. Ordinary editing preserves them; new tasks do not need them. The new Factory uses local repository choices on Overview for automations and the default harness.
