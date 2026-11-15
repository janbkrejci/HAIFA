# First run

`factory obs` starts the dashboard at `http://127.0.0.1:4700` (choose a port with `--port N`). Keep the terminal open; runs survive stopping the server.

## Topbar <!-- section:horni-lista -->

- **HAIFA:** return to Overview.
- **Uncommitted backlog**, **Uncommitted configuration:** red icons with counts; tooltips describe files. Click to open the backlog panel or configuration commit preview.
- **Update chip:** icon with **System is up to date** / **Update available** tooltips.
- **Check chip:** checkmark/warning; **System OK** / **Problems found** tooltips. Click to repeat the check or open **Problems and solutions**.
- **Library chip:** library/warning; **Library OK** / **Create library** tooltips. Opens the **Library** page.
- **Harnesses:** limits, a spinner while loading, or a warning tooltip when none are available; click to open **Harnesses on this machine**.
- **AI assistant**: Claude/Codex (`README.md`), restricted tools; pi is unsupported. Before sending: **From settings** or a harness (model/thinking), only for a new thread; this does not change repository settings. Topbar: new thread; **Older threads**: history. Changes: **Apply**.
- Guide, theme and repository switcher.

## Problems and solutions <!-- section:problemy-a-reseni -->

Buttons for findings and remaining steps: **Check machine**, **Prepare library** and **Check harnesses** lead to Library; **Add repository** adds a repository; **Install factory**, **Commit configuration** and **Check agents** lead to the Factory tab; **Create project** leads to Backlog.

## Harnesses on this machine <!-- section:harnessy-tohoto-pocitace -->

Enable a harness, select **Default model** and **Default thinking level**, and run **Test**. After a successful test, select it as the **Default harness**, then **Save settings**.

Helpers inherit the object's harness, model and thinking: task, step, project, then repository. Repository helpers and Overview use machine settings from the topbar.

## Adding a repository <!-- section:pridani-repa -->

**Add repository**: enter a path (**Browse…**), **Check**, **Add**. This creates and commits `.factory/config.yaml` and updates `.gitignore`; existing factory installations are attached. Agents/workflows are inherited from the library. Protected base: **Base changes through pull requests**. CLI: `factory obs --repo PATH`, `factory init`.

## Overview and repository tabs <!-- section:prehled-a-zalozky-repa -->

Overview filters: **Running**, **Awaiting review**, **Approved, awaiting CI**, **Awaiting PR automerge**, **Failed**, **Problems**. Cards: **Start factory** (ready tasks), **Pause** / **Resume**, **Stop** (all runs). The ⋮ menu's **Remove repository** disconnects the repository and keeps its files.

Tabs: [**Backlog**](#/guide/backlog), [**Runs** and **Review**](#/guide/behy-a-review), [**Factory**](#/guide/konfigurace).

## From task to merge <!-- section:od-tasku-k-merge -->

1. In Backlog, create a project, step and task with a description and workflow.
2. Commit the backlog using the **Uncommitted backlog** icon.
3. In task details, click **Run**.
4. A successful task is **Awaiting review**: on the Review tab, **Approve** or **Return with a note**.
5. After approval: **Approved, awaiting CI**; after merge: **Done**.
