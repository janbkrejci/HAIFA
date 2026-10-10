# HAIFA-S01-T37: New Step button

## Requirement

The dashboard backlog must offer step creation alongside the existing project and task creation actions.

## Behavior

- Show **Nový step** in the backlog header in both tree and kanban modes, using the configured child level name.
- Open the repo-scoped `#/r/<repo>/backlog/new-step` screen. Load available projects and require a parent selection before displaying the existing container form.
- Show project codes and titles, including projects without steps. Switching the parent resets the form to avoid carrying a code from another project.
- Submit the code, title, optional description and parent through the existing container creation API. Open the created step's graph on success; preserve form values and display validation errors on failure.
- Preserve the selected project's draft while the backlog list refreshes.
- Cancel returns to the backlog. An empty backlog offers project creation. Configurations where projects directly contain tasks do not offer step creation.
- Preserve creation from a project graph and existing project/task creation behavior.

## Verification

Focused Vitest coverage checks the header action, project selection, parent changes, submission, validation failure, cancellation, loading and empty states, configurations without steps, and repo-scoped routing. Type-check and build the production frontend, and run repository lint checks.
