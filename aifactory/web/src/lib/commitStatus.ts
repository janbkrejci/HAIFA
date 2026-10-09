// Files in the working tree not committed to base (D4): runs read base, so the backlog
// (GET /api/backlog/status) and the shared config (GET /api/config/status) both report
// what a commit would publish, in the same shape.

export interface CommitChange {
  path: string
  status: string
}

export interface CommitStatus {
  base: string
  commit: string
  clean: boolean
  changes: CommitChange[]
}

/**
 * A commit status from any JSON: missing parts get safe defaults (no `clean` = clean when
 * nothing changed, a change without status gets ''), non-objects give null.
 */
export function toCommitStatus(raw: unknown): CommitStatus | null {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return null
  const obj = raw as Record<string, unknown>
  const changes: CommitChange[] = Array.isArray(obj.changes)
    ? obj.changes
        .filter((c): c is Record<string, unknown> => typeof c === 'object' && c !== null)
        .filter((c) => typeof c.path === 'string')
        .map((c) => ({ path: c.path as string, status: typeof c.status === 'string' ? c.status : '' }))
    : []
  return {
    base: typeof obj.base === 'string' ? obj.base : '',
    commit: typeof obj.commit === 'string' ? obj.commit : '',
    clean: typeof obj.clean === 'boolean' ? obj.clean : changes.length === 0,
    changes,
  }
}
