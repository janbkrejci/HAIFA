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
  dirty?: boolean; items?: LibraryItem[]; branch?: string; head?: string; last_fetch?: string | null; fetched?: boolean
  seed_update_available?: boolean; seed_updates?: string[]
}
/** A registered repo's own copy of a library item: it wins over the library (`same`: equal content). */
export interface LibraryOverride { repo: string; repo_name: string; type: FactoryItemType; name: string; same: boolean | null }
export interface LibraryOverrides { library: string | null; overrides: LibraryOverride[]; errors: { repo: string; repo_name: string; message: string }[] }
/** A seed plan item; `kept` (changed by the team) carries the diff the seed would make. */
export interface SeedPlanItem extends PlanItem { previous_version?: string | null; diff?: FactoryFile[] }
export interface ItemDetail extends LibraryItem {
  files: { path: string; content: string | null; binary: boolean }[]; history: Revision[]
}
export type Blocker = PlanBlocker
export interface LibraryPlan { digest: string; library?: string | { name: string }; action?: string; apply_target?: 'base' | 'pr'; base?: string
  warnings?: PlanWarning[]; files: FactoryFile[]; items: PlanItem[]; blockers: Blocker[] }
export interface LibraryRequest { action: 'init' | 'clone' | 'import' | 'seed'; options: { url?: string; path?: string; type?: FactoryItemType; take?: string[] } }
/** Status with the items; `fetch` fetches the remote first so ahead/behind are current. */
export function fetchLibrary(fresh = false): Promise<LibraryStatus> { return getGlobal(fresh ? '/library?fetch=1' : '/library') }
/** Which registered repos override library items with their own copy. */
export function fetchOverrides(): Promise<LibraryOverrides> { return getGlobal('/library/overrides') }
/** Shares a library without a remote through an empty git remote (pushes it there). */
export function connectRemote(url: string): Promise<unknown> { return postGlobal('/library/remote', { url }) }
/** The sync state of the library with its remote, in words. */
export function syncState(s: LibraryStatus): { text: string; tone: 'ok' | 'warning' | 'error' | 'dim' } {
  if (!s.exists) return { text: 'Knihovna není založená', tone: 'dim' }
  if (s.dirty) return { text: 'Knihovna má necommitnuté změny · synchronizace je zablokovaná', tone: 'error' }
  if (!s.remote) return { text: 'Bez remote · knihovna je jen na tomto počítači', tone: 'dim' }
  const ahead = s.ahead ?? 0, behind = s.behind ?? 0
  if (ahead && behind) return { text: `Rozcházejí se · ${ahead} commitů navíc, ${behind} chybí`, tone: 'error' }
  if (behind) return { text: `Pozadu o ${behind} · stáhni změny z remote`, tone: 'warning' }
  if (ahead) return { text: `Napřed o ${ahead} · odešli změny na remote`, tone: 'warning' }
  return { text: 'Synchronizováno s remote', tone: 'ok' }
}
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
