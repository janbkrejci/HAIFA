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
/** A library change sent for review: the branch and, on GitHub, the pull request (never merged by HAIFA). */
export interface LibraryPullRequest {
  branch: string; base: string; title: string; created: string; repo: string | null; head_repo: string | null
  url: string | null; number: number | null; state: string; fork: boolean
}
/** unshared: no remote · local: changes not sent · pending: waits in a PR · behind · synced. */
export type LibrarySyncState = 'unshared' | 'local' | 'pending' | 'behind' | 'synced'
export interface LibraryStatus {
  exists: boolean; library?: string; remote?: string | null; ahead?: number | null; behind?: number | null
  dirty?: boolean; items?: LibraryItem[]; branch?: string; head?: string; last_fetch?: string | null; fetched?: boolean
  seed_update_available?: boolean; seed_updates?: string[]
  unsent?: number; sync_state?: LibrarySyncState; pull_requests?: LibraryPullRequest[]; pull_requests_error?: string | null
  /** The team library cloned by default (HAIFA_LIBRARY_URL overrides it). */
  default_url?: string
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
  const unsent = s.unsent ?? ahead
  if (unsent && behind) return { text: `Rozcházejí se · ${unsent} lokálních změn, ${behind} commitů chybí · stáhni změny`, tone: 'error' }
  if (unsent) return { text: `Lokální změny · ${unsent} neodeslaných commitů · odešli je jako pull request`, tone: 'warning' }
  const open = s.pull_requests?.length ?? 0
  if (ahead) {
    const prs = open ? ` · ${open} otevřených PR` : ''
    return { text: `Čeká v PR${prs} · mergne správce knihovny${behind ? ', pak stáhni změny' : ''}`, tone: behind ? 'warning' : 'ok' }
  }
  if (behind) return { text: `Pozadu o ${behind} · stáhni změny z remote`, tone: 'warning' }
  return { text: 'Srovnáno s remote', tone: 'ok' }
}
/** Status without the item list: cheap enough for the topbar readiness check. */
export function fetchLibrarySummary(): Promise<LibraryStatus> { return getGlobal('/library?items=0') }
export function fetchItem(type: FactoryItemType, name: string, version?: string): Promise<ItemDetail> {
  return getGlobal(`/library/items/${type}/${encodeURIComponent(name)}${version ? '?version=' + encodeURIComponent(version) : ''}`)
}
export function previewLibrary(body: LibraryRequest): Promise<LibraryPlan> { return postGlobal('/library/plan', body) }
export function applyLibrary(body: LibraryRequest, digest: string): Promise<{ commit?: string; pull_request?: LibraryPullRequest | null }> {
  return postGlobal('/library/apply', { action: body.action, options: body.options, digest })
}
/** Pulls the library from its remote, or sends its local changes as a pull request. */
export function syncLibrary(action: 'pull' | 'push'): Promise<{ pull_request?: LibraryPullRequest | null; pushed?: number }> {
  return postGlobal(`/library/${action}`)
}
/** Where a sent change waits: the PR link, or the branch to open a PR from by hand. */
export function pullRequestText(pr: LibraryPullRequest): string {
  if (pr.url) return `PR #${pr.number ?? '?'}${pr.fork ? ' z forku ' + pr.head_repo : ''}`
  return `větev ${pr.branch} · pull request otevři ručně`
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
/** The groups of the machine findings on #/setup; library findings are in the library section. */
export const MACHINE_GROUPS = FINDING_GROUPS.filter(name => name !== 'Knihovna')
export function versionLabel(item: { n?: number; short_version?: string | null; version?: string | null }): string {
  const hash = item.short_version ?? item.version?.replace(/^sha256:/, '').slice(0, 8) ?? '—'
  return `${item.n ? 'v' + item.n + ' · ' : ''}${hash}`
}
