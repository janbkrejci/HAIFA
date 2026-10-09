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
  path_not_found: () => 'Složka neexistuje.',
  not_a_directory: () => 'Cesta nevede ke složce.',
  not_git: () => 'Složka není v git repozitáři. HAIFA nespouští git init.',
  linked_worktree: (p) =>
    p.main_checkout
      ? `Složka je propojený worktree. Přidej hlavní checkout ${p.main_checkout}.`
      : 'Složka je propojený worktree. Přidej hlavní checkout.',
  run_worktree: () => 'Složka je worktree běhu úkolu (.factory/worktrees/), ne repozitář.',
  bare_repo: () => 'Holé repo bez pracovního stromu nejde přidat.',
  no_commits: () => 'Repo ještě nemá žádný commit. Nejdřív něco commitni.',
  trace_db_shared: (p, inspect) =>
    `Trace DB ${inspect?.trace_db ?? '(neznámá)'} už používá registrované repo ${p.repo ?? '(neznámé)'}.`,
}

/** Why the folder cannot be added, in Czech; the server's message for an unknown code. */
export function problemText(problem: RepoProblem, inspect: InspectResult | null = null): string {
  const text = PROBLEM_TEXT[problem.code]
  return text ? text(problem, inspect) : problem.message
}

/** What a `usage_error` of inspect (e.g. a relative path) says. */
export const USAGE_ERROR_TEXT = 'Zadej absolutní cestu nebo cestu začínající ~.'

/** What a failed system folder dialog says. */
export function pickErrorText(code: string, message: string): string {
  if (code === 'picker_busy') return 'Dialog výběru složky už je otevřený.'
  return message
}
