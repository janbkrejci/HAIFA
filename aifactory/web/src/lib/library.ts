import {
  getGlobal, postGlobal,
  type CheckFinding, type FactoryFile, type FactoryItemType, type PlanBlocker, type PlanItem, type PlanWarning,
} from './api'

export const ITEM_TABS: readonly { type: FactoryItemType; label: string }[] = [
  { type: 'agent', label: 'Agenti' }, { type: 'workflow', label: 'Workflow' },
  { type: 'skill', label: 'Skilly' }, { type: 'extension', label: 'Rozšíření pi' },
]
export interface Revision { n: number; version: string; short_version: string; date: string; author: string }
export interface LibraryItem {
  type: FactoryItemType; name: string; version: string; short_version: string; n: number
  purpose: string | null; description: string | null; date: string; author: string
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
