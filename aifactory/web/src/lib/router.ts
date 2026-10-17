import { ref, type Ref } from 'vue'
import { acceptHash, allowHashChange } from './leaveGuard'

// Hash routes of the multi-repo dashboard:
//   #/overview                       the registered repositories and getting started (default)
//   #/setup[/library]                this machine, its library section (#/library redirects)
//   #/repos/add                      add a repository
//   #/guide[/<chapter>[/<section>]]  the user and administrator guide
//   #/r/<id>/<screen>[/<params>]     a screen of repo <id>: backlog · runs · review · factory
// A screen may carry parameters: #/r/<id>/runs/<run_id>/<phase_id>, #/r/<id>/backlog/<task id>.
// The repo settings are a section of Factory: #/r/<id>/factory/settings (#/r/<id>/settings redirects).
// An unknown hash falls back to the overview.
// The repo lives only in the URL: currentRepoId() reads the hash at call time.
export type Screen = 'backlog' | 'runs' | 'review' | 'factory'
export type Page = 'overview' | 'repos-add' | 'setup' | 'problems' | 'guide' | 'repo'

export const SCREENS: readonly { id: Screen; label: string }[] = [
  { id: 'backlog', label: 'Backlog' },
  { id: 'runs', label: 'Běhy' },
  { id: 'review', label: 'Review' },
  { id: 'factory', label: 'Factory' },
]

export const SCREEN_LABELS: Readonly<Record<Screen, string>> = Object.fromEntries(
  SCREENS.map((s) => [s.id, s.label]),
) as Record<Screen, string>

const IDS: readonly string[] = SCREENS.map((s) => s.id)

export const OVERVIEW_HREF = '#/overview'
export const REPOS_ADD_HREF = '#/repos/add'
export const GUIDE_HREF = '#/guide'
/** This machine: its check, the library and the dashboard settings. */
export const SETUP_HREF = '#/setup'
/** The library section of this machine. */
export const LIBRARY_HREF = '#/setup/library'

/** Link to the guide, optionally to a chapter and a section of it. */
export function guideHref(chapter?: string | null, section?: string | null): string {
  if (!chapter) return GUIDE_HREF
  const parts = [GUIDE_HREF, encodeURIComponent(chapter)]
  if (section) parts.push(encodeURIComponent(section))
  return parts.join('/')
}

export interface Route {
  page: Page
  repo: string | null
  screen: Screen
  params: string[]
  /** The canonical hash when the given one differs (legacy, empty, `#/r/<id>`, unknown), else null. */
  redirect: string | null
}

function decode(part: string): string {
  try {
    return decodeURIComponent(part)
  } catch {
    return part
  }
}

function page(name: Exclude<Page, 'repo'>, redirect: string | null, params: string[] = []): Route {
  return { page: name, repo: null, screen: 'backlog', params, redirect }
}

export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  const [first, second, third] = parts
  if ((first === 'setup' || first === 'problems') && parts.length === 1) return page(first, null)
  if (first === 'setup' && second === 'library' && parts.length === 2) return page('setup', null, ['library'])
  if (first === 'library' && parts.length === 1) return page('setup', LIBRARY_HREF, ['library'])
  if (first === 'overview' && parts.length === 1) return page('overview', null)
  if (first === 'guide' && parts.length <= 3) return page('guide', null, parts.slice(1).map(decode))
  if (first === 'repos' && second === 'add' && parts.length === 2) return page('repos-add', null)
  if (first === 'r' && second !== undefined) {
    const repo = decode(second)
    if (third === 'settings') {
      return { page: 'repo', repo, screen: 'factory', params: ['settings'], redirect: repoSettingsHref(repo) }
    }
    if (third !== undefined && IDS.includes(third)) {
      return { page: 'repo', repo, screen: third as Screen, params: parts.slice(3).map(decode), redirect: null }
    }
    return { page: 'repo', repo, screen: 'backlog', params: [], redirect: repoHref(repo, 'backlog') }
  }
  return page('overview', OVERVIEW_HREF)
}

/** The repo id of the current hash (read at call time), null off a repo page. */
export function currentRepoId(): string | null {
  return parseRoute(window.location.hash).repo
}

/** Link to a screen of repo `id`, with optional parameters. */
export function repoHref(id: string, screen: Screen = 'backlog', ...params: string[]): string {
  return [`#/r/${encodeURIComponent(id)}/${screen}`, ...params.map(encodeURIComponent)].join('/')
}

/** Link to the settings section of repo `id` on its Factory screen. */
export function repoSettingsHref(id: string): string {
  return repoHref(id, 'factory', 'settings')
}

/** Link to a screen of the current repo; the overview without one. */
export function here(screen: Screen, ...params: string[]): string {
  const id = currentRepoId()
  return id === null ? OVERVIEW_HREF : repoHref(id, screen, ...params)
}

/** Link to a run's detail, optionally with a phase selected. */
export function runHref(runId: string, phaseId?: string | null): string {
  return phaseId ? here('runs', runId, phaseId) : here('runs', runId)
}

const route = ref<Screen>('backlog')
const params = ref<string[]>([])
const currentPage = ref<Page>('overview')
const repoId = ref<string | null>(null)

function sync(): void {
  const parsed = parseRoute(window.location.hash)
  if (parsed.redirect !== null) window.history.replaceState(null, '', parsed.redirect)
  route.value = parsed.screen
  params.value = parsed.params
  currentPage.value = parsed.page
  repoId.value = parsed.repo
  acceptHash()
}

/** A hash change leaving a form with unsaved changes waits for the user's answer. */
function onHashChange(): void {
  if (allowHashChange()) sync()
}

sync()
window.addEventListener('hashchange', onHashChange)

/** The screen of the repo page (`backlog` off a repo page). */
export function useRoute(): Ref<Screen> {
  return route
}

export function useRouteParams(): Ref<string[]> {
  return params
}

export function usePage(): Ref<Page> {
  return currentPage
}

export function useRepoId(): Ref<string | null> {
  return repoId
}

/** `#/r/<id>/backlog/new[/<step id>]`: the form for a new task, its step preselected. */
export const NEW_TASK = 'new'

/** Link to the form for a new task, optionally with its step preselected. */
export function newTaskHref(stepId?: string | null): string {
  return stepId ? here('backlog', NEW_TASK, stepId) : here('backlog', NEW_TASK)
}

/** Link to a task's detail on the Backlog screen. */
export function taskHref(taskId: string): string {
  return here('backlog', taskId)
}

/** `#/r/<id>/backlog/graph/<id>`: the dependency graph of a module or step. */
export const GRAPH = 'graph'

/** Link to the dependency graph of a module or step. */
export function graphHref(containerId: string): string {
  return here('backlog', GRAPH, containerId)
}

/** Link to a task's pull request on the Review screen. */
export function reviewHref(taskId: string): string {
  return here('review', taskId)
}

/** `#/r/<id>/backlog/new-container[/<parent id>]`: the form for a new project or step. */
export const NEW_CONTAINER = 'new-container'

/** `#/r/<id>/backlog/intent[/<project or step id>]`: the Nový záměr dialog. */
export const NEW_INTENT = 'intent'

export function intentHref(containerId?: string | null): string {
  return containerId ? here('backlog', NEW_INTENT, containerId) : here('backlog', NEW_INTENT)
}

/** `#/r/<id>/backlog/new-step`: choose a project and create its step. */
export const NEW_STEP = 'new-step'

export function newStepHref(): string {
  return here('backlog', NEW_STEP)
}

/** Link to the form for a new project (no parent) or a step of `parentId`. */
export function newContainerHref(parentId?: string | null): string {
  return parentId ? here('backlog', NEW_CONTAINER, parentId) : here('backlog', NEW_CONTAINER)
}
