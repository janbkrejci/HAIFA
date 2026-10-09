import {
  factoryItemChoices, getGlobal, postGlobal,
  type CheckFinding, type FactoryFile, type FactoryItemOptions, type FactoryItemType, type FactoryResult, type PlanBlocker, type PlanItem,
  type PlanWarning, type RepoItem,
} from './api'

export const ITEM_TABS: readonly { type: FactoryItemType; label: string }[] = [
  { type: 'agent', label: 'Agenti' }, { type: 'workflow', label: 'Workflow' },
  { type: 'skill', label: 'Skilly' }, { type: 'extension', label: 'Rozšíření pi' },
]
export interface Usage { repo: RepoItem; slot: string | null; state: string; version: string | null }
export interface Revision { n: number; version: string; short_version: string; date: string; author: string }
export interface LibraryItem {
  type: FactoryItemType; name: string; version: string; short_version: string; n: number
  purpose: string | null; description: string | null; date: string; author: string; repos: Usage[]
}
export interface LibraryStatus {
  exists: boolean; library?: string; remote?: string | null; ahead?: number | null; behind?: number | null
  dirty?: boolean; items?: LibraryItem[]
}
export interface ItemDetail extends LibraryItem {
  files: { path: string; content: string | null; binary: boolean }[]; history: Revision[]
}
export type Blocker = PlanBlocker
export interface LibraryPlan { digest: string; library?: string | { name: string }; action?: string; apply_target?: 'base' | 'pr'; base?: string
  warnings?: PlanWarning[]; files: FactoryFile[]; items: PlanItem[]; blockers: Blocker[] }
export interface LibraryRequest { action: 'init' | 'clone' | 'import'; options: { url?: string; path?: string; type?: FactoryItemType } }
export interface RepoPlan extends LibraryPlan {
  action: 'add' | 'update'; apply_options: Record<string, unknown>; apply_target: 'base' | 'pr'
  update?: { items: { type: string; name: string; files: { file: string; diff: string | null; ours_diff: string | null; theirs_diff: string | null }[] }[] }
}
export interface RepoPlanRow { repo: RepoItem; status: string; plan: RepoPlan | null; error?: Blocker; result?: FactoryResult }
export function fetchLibrary(): Promise<LibraryStatus> { return getGlobal('/library') }
/** Status without the item list: cheap enough for the topbar readiness check. */
export function fetchLibrarySummary(): Promise<LibraryStatus> { return getGlobal('/library?items=0') }
export function fetchItem(type: FactoryItemType, name: string, version?: string): Promise<ItemDetail> {
  return getGlobal(`/library/items/${type}/${encodeURIComponent(name)}${version ? '?version=' + encodeURIComponent(version) : ''}`)
}
export function previewLibrary(body: LibraryRequest): Promise<LibraryPlan> { return postGlobal('/library/plan', body) }
export function applyLibrary(body: LibraryRequest, digest: string): Promise<{ commit?: string }> {
  return postGlobal('/library/apply', { action: body.action, options: body.options, digest })
}
/** Pulls the library from its remote, or pushes it there. */
export function syncLibrary(action: 'pull' | 'push'): Promise<unknown> { return postGlobal(`/library/${action}`) }
export function previewRepos(action: 'add' | 'update', item: LibraryItem, repos: string[], target: 'base' | 'pr') {
  return postGlobal<{ repos: RepoPlanRow[] }>('/library/repos-plan', { action, type: item.type, name: item.name, repos, options: { target } })
}
// Serialize only the server's validated plan choices and digest, never the returned files.
export function applyRepo(row: RepoPlanRow): Promise<FactoryResult> {
  const plan = row.plan!
  return postGlobal(`/repos/${encodeURIComponent(row.repo.id)}/factory/apply`, {
    action: plan.action, options: factoryItemChoices(plan.action, plan.apply_options as FactoryItemOptions), target: plan.apply_target, digest: plan.digest,
  })
}
export function findingGroup(f: CheckFinding): string {
  if (f.scope === 'library') return 'Knihovna'
  if (/harness|^pi_model_|^node_/.test(f.code)) return 'Harnessy'
  if (/^gh_|^az_|^azure_|^hosting_|^github_/.test(f.code)) return 'Hosting'
  if (/^git_|^uv_|^just_/.test(f.code)) return 'Nástroje'
  if (/factory|haifa|version/.test(f.code)) return 'HAIFA'
  return 'Prostředí'
}
export const FINDING_GROUPS = ['HAIFA', 'Nástroje', 'Harnessy', 'Hosting', 'Knihovna', 'Prostředí']
export function versionLabel(item: { n?: number; short_version?: string | null; version?: string | null }): string {
  const hash = item.short_version ?? item.version?.replace(/^sha256:/, '').slice(0, 8) ?? '—'
  return `${item.n ? 'v' + item.n + ' · ' : ''}${hash}`
}

/** States of an item in a repo (library and Factory tab), and of a repo plan row, in Czech. */
const STATE_TEXT: Record<string, string> = {
  local: 'lokální', missing: 'chybí', synced: 'synchronizováno', unknown: 'neznámá verze',
  outdated: 'zastaralé', modified: 'změněné', diverged: 'rozvětvené', repo_missing: 'repo chybí',
  planned: 'naplánováno', ok: 'hotovo', blocked: 'blokováno', repo_io_error: 'repo nejde přečíst',
}

export function stateText(state: string): string {
  return STATE_TEXT[state] ?? state
}
