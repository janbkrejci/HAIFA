import { t } from './i18n'
// Pure helpers of the Add repository page (#/repos/add): the path field's suggestions and
// the reasons a folder cannot be added.
import type { FsEntry, InspectResult, RepoProblem } from './api'

/** `~` → `home`, `~/x` → `home/x`; anything else unchanged. */
export function expandHome(value: string, home: string): string {
  const base = home.replace(/\/+$/, '')
  if (value === '~') return base
  if (value.startsWith('~/')) return `${base}/${value.slice(2)}`
  return value
}

/** The folder to list and the prefix to filter by, split after the last `/`; null without one. */
export function splitForSuggest(value: string): { dir: string; prefix: string } | null {
  const at = value.lastIndexOf('/')
  if (at < 0) return null
  return { dir: value.slice(0, at + 1), prefix: value.slice(at + 1) }
}

/** The entries whose name starts with `prefix` (any case), in the server's order. */
export function filterEntries(entries: readonly FsEntry[], prefix: string, limit = 12): FsEntry[] {
  const p = prefix.toLowerCase()
  return entries.filter((e) => e.name.toLowerCase().startsWith(p)).slice(0, limit)
}

type ProblemText = (problem: RepoProblem, inspect: InspectResult | null) => string

export const PROBLEM_TEXT: Record<string, ProblemText> = {
  path_not_found: () => t('helpers.path_not_found'),
  not_a_directory: () => t('helpers.not_a_directory'),
  not_git: () => t('helpers.not_git'),
  linked_worktree: (p) =>
    p.main_checkout
      ? t('helpers.linkedPath', { path: p.main_checkout })
      : t('helpers.linked_worktree'),
  run_worktree: () => t('helpers.run_worktree'),
  bare_repo: () => t('helpers.bare_repo'),
  no_commits: () => t('helpers.no_commits'),
  trace_db_shared: (p, inspect) =>
    t('helpers.trace_db_shared', { path: inspect?.trace_db ?? t('helpers.unknownDb'), repo: p.repo ?? t('helpers.unknownRepo') }),
}

/** Why the folder cannot be added, in the UI language; the server's message for an unknown code. */
export function problemText(problem: RepoProblem, inspect: InspectResult | null = null): string {
  const text = PROBLEM_TEXT[problem.code]
  return text ? text(problem, inspect) : problem.message
}

/** What a failed system folder dialog says. */
export function pickErrorText(code: string, message: string): string {
  if (code === 'picker_busy') return t('helpers.pickerBusy')
  return message
}
