// The AI guide panel: its API (/api/assistant/…), the conversation state shared by every
// screen, the screen context sent with a message, the suggested questions of an empty thread
// and the dashboard links in an answer.
//
// The state lives at module level, so the open thread survives every screen change; the id of
// the open thread and whether the panel is open are kept for the tab (sessionStorage).
import { reactive } from 'vue'
import { ApiError, deleteGlobal, getApi, getGlobal, postGlobal } from './api'
import { errorText } from './format'
import { GRAPH, NEW_CONTAINER, NEW_STEP, NEW_TASK, type Page, type Screen } from './router'

// ── API ──────────────────────────────────────────────────────────────────────────────────

/** The screen the user is looking at, sent with a message (`screen` of the API). */
export interface ScreenContext {
  repo?: string
  task?: string
  run?: string
}

export type ActionKind =
  | 'create_task'
  | 'edit_task'
  | 'run_task'
  | 'retry_run'
  | 'approve_pr'
  | 'cancel_task'
  | 'follow_up'
export type ActionStatus = 'proposed' | 'done' | 'failed' | 'dismissed'

/** An action the guide proposed; nothing happens until the user executes it in the panel. */
export interface ProposedAction {
  id: string
  kind: ActionKind
  repo: string
  task?: string
  /** `retry_run`: the run id; `follow_up`: commit the backlog and start the new task at once. */
  run?: string | boolean
  step?: string
  title?: string
  body?: string
  writes?: string[]
  workflow?: string
  depends_on?: string[]
  note?: string
  reason?: string
  status: ActionStatus
  outcome?: { message: string; at: string }
}

export interface AssistantMessage {
  id: string
  /** `action`: the outcome of a proposed action, recorded by the panel. */
  role: 'user' | 'assistant' | 'action'
  text: string
  screen?: ScreenContext
  at?: string
  error?: string
  usage?: { tokens: number; cost_usd: number }
  actions?: ProposedAction[]
  action_id?: string
  status?: ActionStatus
}

export interface ThreadSummary {
  id: string
  title: string
  harness: string
  model: string
  created_at: string
  updated_at: string
  messages: number
  busy: boolean
}

export interface ThreadDetail extends Omit<ThreadSummary, 'messages'> {
  messages: AssistantMessage[]
  seq: number
}

interface SendResult {
  thread: ThreadSummary
  message: AssistantMessage
  seq: number
}

const THREADS = '/assistant/threads'

export async function fetchThreads(): Promise<ThreadSummary[]> {
  const data = await getGlobal<{ threads?: ThreadSummary[] }>(THREADS)
  return Array.isArray(data.threads) ? data.threads : []
}

export function fetchThread(id: string): Promise<ThreadDetail> {
  return getGlobal<ThreadDetail>(`${THREADS}/${encodeURIComponent(id)}`)
}

export function createThread(): Promise<ThreadDetail> {
  return postGlobal<ThreadDetail>(THREADS, {})
}

/** Delete a thread for good (HTTP 409 `busy` while the guide answers in it). */
export function deleteThreadRequest(id: string): Promise<{ deleted: string }> {
  return deleteGlobal<{ deleted: string }>(`${THREADS}/${encodeURIComponent(id)}`)
}

export function sendMessage(id: string, text: string, screen: ScreenContext | null): Promise<SendResult> {
  const body: { text: string; screen?: ScreenContext } = { text }
  if (screen && Object.keys(screen).length) body.screen = screen
  return postGlobal<SendResult>(`${THREADS}/${encodeURIComponent(id)}/messages`, body)
}

export function streamUrl(id: string, after: number): string {
  return `/api${THREADS}/${encodeURIComponent(id)}/stream?after=${after}`
}

// ── proposed actions ─────────────────────────────────────────────────────────────────────

const ACTION_TITLES: Record<ActionKind, string> = {
  create_task: 'Založit task',
  edit_task: 'Upravit task',
  run_task: 'Spustit task',
  retry_run: 'Zopakovat běh',
  approve_pr: 'Schválit PR',
  cancel_task: 'Zrušit task',
  follow_up: 'Navázat follow-upem na',
}

/** The run id of a `retry_run` (`run` of a `follow_up` is a flag). */
function runOf(action: ProposedAction): string | undefined {
  return typeof action.run === 'string' ? action.run : undefined
}

/** `Upravit task P01-S01-T01`: the card's heading. */
export function actionTitle(action: ProposedAction): string {
  const target = action.task ?? runOf(action) ?? action.title ?? ''
  return `${ACTION_TITLES[action.kind] ?? action.kind} ${target}`.trim()
}

/** The dashboard screen of the action's object. */
export function actionHref(action: ProposedAction): string | null {
  const repo = encodeURIComponent(action.repo)
  const run = runOf(action)
  if (action.kind === 'retry_run' && run) return `#/r/${repo}/runs/${encodeURIComponent(run)}`
  if (action.kind === 'approve_pr' && action.task) return `#/r/${repo}/review/${encodeURIComponent(action.task)}`
  if (action.task) return `#/r/${repo}/backlog/${encodeURIComponent(action.task)}`
  if (action.step) return `#/r/${repo}/backlog`
  return null
}

/** What the task looks like now, for the preview of an edit. */
export interface TaskNow {
  title: string
  body: string
  writes: string[]
  workflow: string | null
  status: string
  /** The task's own writes and workflow: a follow-up takes these over. */
  own_writes: string[]
  own_workflow: string | null
}

/** One line of the preview: a field, its value now (when known) and after the action. */
export interface PreviewRow {
  label: string
  before: string | null
  after: string
}

function list(values: readonly string[] | undefined): string {
  return values && values.length ? values.join(', ') : '—'
}

/** The preview of the change: field by field, with the current value of an edited task. */
export function actionPreview(action: ProposedAction, now: TaskNow | null = null): PreviewRow[] {
  const rows: PreviewRow[] = [{ label: 'Repo', before: null, after: action.repo }]
  const field = (label: string, after: string | undefined, before: string | null = null) => {
    if (after !== undefined) rows.push({ label, before, after })
  }
  switch (action.kind) {
    case 'create_task':
      field('Krok', action.step)
      field('Název', action.title)
      field('Writes', action.writes ? list(action.writes) : undefined)
      field('Workflow', action.workflow)
      field('Závisí na', action.depends_on ? list(action.depends_on) : undefined)
      field('Zadání', action.body)
      break
    case 'edit_task':
      field('Task', action.task)
      field('Název', action.title, now ? now.title : null)
      field('Writes', action.writes ? list(action.writes) : undefined, now ? list(now.writes) : null)
      field('Workflow', action.workflow, now ? (now.workflow ?? '—') : null)
      field('Zadání', action.body, now ? now.body : null)
      break
    case 'run_task':
    case 'approve_pr':
      field('Task', action.task)
      field('Poznámka', action.note)
      break
    case 'retry_run':
      field('Běh', runOf(action))
      field('Poznámka', action.note)
      break
    case 'cancel_task':
      field('Task', action.task)
      field('Stav', 'cancelled', now ? now.status : null)
      break
    case 'follow_up': {
      const inherited = 'zdědí z kroku'
      field('Navazuje na', action.task)
      if (now && now.status !== 'done') field('Stav', `${now.status || 'bez stavu'} (jen hotový task jde navázat)`)
      field('Název', action.title ?? (now ? `Navazuje na ${action.task}: ${now.title}` : `Navazuje na ${action.task}: …`))
      field('Writes', now ? (now.own_writes.length ? list(now.own_writes) : inherited) : `převezme z ${action.task}`)
      field('Workflow', now ? (now.own_workflow ?? inherited) : `převezme z ${action.task}`)
      field('Zadání', action.body)
      field('Po založení', action.run === true ? 'commitnout backlog a spustit' : 'jen založit (backlog necommitovaný)')
      break
    }
  }
  return rows
}

/** The dashboard write API call of an action: the same endpoint as the manual action. */
export function actionRequest(action: ProposedAction): { path: string; body?: Record<string, unknown> } {
  const repo = `/repos/${encodeURIComponent(action.repo)}`
  const task = `${repo}/backlog/tasks/${encodeURIComponent(action.task ?? '')}`
  const pick = (...keys: (keyof ProposedAction)[]) => {
    const body: Record<string, unknown> = {}
    for (const key of keys) if (action[key] !== undefined) body[key] = action[key]
    return body
  }
  switch (action.kind) {
    case 'create_task':
      return { path: `${repo}/backlog/tasks`, body: pick('step', 'title', 'body', 'writes', 'workflow', 'depends_on') }
    case 'edit_task':
      return { path: `${task}/edit`, body: pick('title', 'body', 'writes', 'workflow') }
    case 'run_task':
      return { path: `${task}/run`, body: pick('note') }
    case 'retry_run':
      return { path: `${repo}/runs/${encodeURIComponent(runOf(action) ?? '')}/retry`, body: pick('note') }
    case 'approve_pr':
      return { path: `${repo}/review/${encodeURIComponent(action.task ?? '')}/approve` }
    case 'cancel_task':
      return { path: `${task}/edit`, body: { status: 'cancelled' } }
    case 'follow_up':
      return { path: `${task}/follow-up`, body: pick('body', 'title', 'run') }
  }
}

function runIdOf(data: Record<string, unknown>): string | null {
  const run = data.run as { run_id?: unknown } | null | undefined
  return run && typeof run.run_id === 'string' ? run.run_id : null
}

/** One sentence on what the executed action did, from the API's data. */
export function actionOutcome(action: ProposedAction, data: unknown): string {
  const result = (data ?? {}) as Record<string, unknown>
  switch (action.kind) {
    case 'create_task': {
      const task = result.task as { id?: unknown } | undefined
      return typeof task?.id === 'string' ? `Task ${task.id} založen.` : 'Task založen.'
    }
    case 'edit_task':
      return result.changed === false ? 'Task se nezměnil.' : 'Task upraven.'
    case 'cancel_task':
      return result.changed === false ? 'Task už byl zrušený.' : 'Task zrušen.'
    case 'run_task':
    case 'retry_run': {
      const run = runIdOf(result)
      return run ? `Běh ${run} spuštěn.` : 'Běh se spouští.'
    }
    case 'approve_pr':
      if (result.started) return 'Schválení běží na pozadí (čeká na CI).'
      return typeof result.merge_sha === 'string' ? `PR sloučen (${result.merge_sha.slice(0, 8)}).` : 'PR schválen.'
    case 'follow_up': {
      const task = result.task as { id?: unknown } | undefined
      const created = typeof task?.id === 'string' ? `Task ${task.id} založen.` : 'Task založen.'
      if (action.run !== true) return created
      const run = runIdOf(result)
      return `${created} ${run ? `Běh ${run} spuštěn.` : 'Běh se spouští.'}`
    }
  }
}

export const ACTION_STATES: Record<Exclude<ActionStatus, 'proposed'>, string> = {
  done: 'provedeno',
  failed: 'selhalo',
  dismissed: 'zahozeno',
}

/** The line of an outcome message (`role: action`) in the thread, in the dashboard's words. */
export function outcomeText(message: AssistantMessage, messages: readonly AssistantMessage[]): string {
  const action = messages.flatMap((m) => m.actions ?? []).find((a) => a.id === message.action_id)
  if (!action || !message.status || message.status === 'proposed') return message.text
  const detail = action.outcome?.message
  return `${actionTitle(action)}: ${ACTION_STATES[message.status]}${detail ? ` — ${detail}` : ''}`
}

function recordOutcome(threadId: string, actionId: string, status: Exclude<ActionStatus, 'proposed'>, message: string) {
  return postGlobal<{ action: ProposedAction; message: AssistantMessage }>(
    `${THREADS}/${encodeURIComponent(threadId)}/actions/${encodeURIComponent(actionId)}`,
    { status, message },
  )
}

function applyRecord(threadId: string, recorded: { action: ProposedAction; message: AssistantMessage }): void {
  const thread = assistant.thread
  if (!thread || thread.id !== threadId) return
  for (const message of thread.messages) {
    const action = message.actions?.find((a) => a.id === recorded.action.id)
    if (action) Object.assign(action, recorded.action)
  }
  if (!thread.messages.some((m) => m.id === recorded.message.id)) thread.messages.push(recorded.message)
}

/** Ids of the actions being executed (their button shows the spinner). */
export const running = reactive(new Set<string>())

/**
 * Execute a proposed action after the user's click: the dashboard's own write API (same
 * endpoint, same guards as the manual action), then its outcome is recorded in the thread.
 */
export async function executeAction(threadId: string, action: ProposedAction): Promise<void> {
  if (action.status !== 'proposed' || running.has(action.id)) return
  running.add(action.id)
  try {
    const call = actionRequest(action)
    let status: 'done' | 'failed'
    let message: string
    try {
      const data = await postGlobal<unknown>(call.path, call.body)
      status = 'done'
      message = actionOutcome(action, data)
    } catch (err) {
      status = 'failed'
      message = errorText(err)
    }
    applyRecord(threadId, await recordOutcome(threadId, action.id, status, message))
  } catch (err) {
    assistant.error = errorText(err)
  } finally {
    running.delete(action.id)
  }
}

/** The user does not want the proposal; the guide learns it with the next message. */
export async function dismissAction(threadId: string, action: ProposedAction): Promise<void> {
  if (action.status !== 'proposed' || running.has(action.id)) return
  running.add(action.id)
  try {
    applyRecord(threadId, await recordOutcome(threadId, action.id, 'dismissed', ''))
  } catch (err) {
    assistant.error = errorText(err)
  } finally {
    running.delete(action.id)
  }
}

/** The task as it is now (for the preview of an edit or cancel); null when unknown. */
export async function taskNow(repo: string, task: string): Promise<TaskNow | null> {
  try {
    const detail = await getGlobal<{ task?: Partial<TaskNow>; body?: string }>(
      `/repos/${encodeURIComponent(repo)}/backlog/tasks/${encodeURIComponent(task)}`,
    )
    const node = detail.task ?? {}
    return {
      title: node.title ?? '',
      body: detail.body ?? '',
      writes: Array.isArray(node.writes) ? node.writes : [],
      workflow: node.workflow ?? null,
      status: node.status ?? '',
      own_writes: Array.isArray(node.own_writes) ? node.own_writes : [],
      own_workflow: node.own_workflow ?? null,
    }
  } catch {
    return null
  }
}

// ── the screen ───────────────────────────────────────────────────────────────────────────

export type ScreenKind =
  | 'run'
  | 'task'
  | 'pr'
  | 'backlog'
  | 'runs'
  | 'review'
  | 'factory'
  | 'overview'
  | 'setup'
  | 'other'

export interface ScreenInfo {
  kind: ScreenKind
  /** What a message carries; null where the screen shows no repository. */
  context: ScreenContext | null
}

const NOT_TASKS: readonly string[] = [NEW_TASK, GRAPH, NEW_CONTAINER, NEW_STEP]

/** The screen of the route: its kind and the repository, task and run it shows. */
export function describeScreen(page: Page, repo: string | null, screen: Screen, params: readonly string[]): ScreenInfo {
  if (page !== 'repo' || !repo) {
    const kind: ScreenKind = page === 'overview' ? 'overview' : page === 'setup' ? 'setup' : 'other'
    return { kind, context: null }
  }
  const first = params[0]
  if (screen === 'runs' && first) return { kind: 'run', context: { repo, run: first } }
  if (screen === 'backlog' && first && !NOT_TASKS.includes(first)) return { kind: 'task', context: { repo, task: first } }
  if (screen === 'review' && first) return { kind: 'pr', context: { repo, task: first } }
  return { kind: screen, context: { repo } }
}

/** The chip of the screen context: `repo haifa · task X`. */
export function contextLabel(context: ScreenContext): string {
  const parts: string[] = []
  if (context.repo) parts.push(`repo ${context.repo}`)
  if (context.task) parts.push(`task ${context.task}`)
  if (context.run) parts.push(`běh ${context.run}`)
  return parts.join(' · ')
}

export function sameContext(a: ScreenContext | null, b: ScreenContext | null): boolean {
  return (a?.repo ?? '') === (b?.repo ?? '') && (a?.task ?? '') === (b?.task ?? '') && (a?.run ?? '') === (b?.run ?? '')
}

/** Three questions an empty thread offers on the screen; `runState` is the shown run's state. */
export function suggestions(kind: ScreenKind, runState: string | null = null): string[] {
  switch (kind) {
    case 'run':
      if (runState === 'failed' || runState === 'aborted') {
        return ['Proč tenhle běh selhal?', 'Co mám změnit, aby task prošel?', 'Ve které fázi se běh zastavil?']
      }
      if (runState === 'running') {
        return ['Co tenhle běh právě dělá?', 'Jak dlouho ještě poběží?', 'Kolik zatím stál?']
      }
      return ['Co tenhle běh udělal?', 'Kolik běh stál a kde?', 'Které fáze trvaly nejdéle?']
    case 'task':
      return ['Co má tenhle task udělat?', 'Proč task neběží nebo na co čeká?', 'Jak dopadly běhy tohoto tasku?']
    case 'pr':
      return ['Co mění tenhle PR?', 'Prošly testy v běhu tohoto PR?', 'Na co se mám při review zaměřit?']
    case 'backlog':
      return ['Které tasky jsou připravené ke spuštění?', 'Co blokuje postup projektu?', 'Které tasky selhaly?']
    case 'runs':
      return ['Které běhy dnes selhaly a proč?', 'Kolik stály běhy za poslední týden?', 'Co právě běží?']
    case 'review':
      return ['Které PR čekají na review?', 'Který PR je nejstarší?', 'Které PR mají neúspěšné CI?']
    case 'factory':
      return ['Jaká workflow tohle repo používá?', 'Je konfigurace v pořádku?', 'Které agenty a modely repo používá?']
    case 'overview':
      return ['Co se teď ve factory děje?', 'Které repo potřebuje pozornost?', 'Co čeká na moje review?']
    case 'setup':
      return ['Je tenhle počítač připravený?', 'Co je v knihovně agentů?', 'Které harnessy jsou zapnuté?']
    default:
      return ['Jak HAIFA funguje?', 'Jak spustím první task?', 'Co se teď ve factory děje?']
  }
}

// ── links in an answer ───────────────────────────────────────────────────────────────────

const LINK = /\[[^\]\n]*\]\([^)\n]*\)/g
const TASK_ID = /\b([A-Z][A-Za-z0-9_.]*(?:-[A-Za-z0-9_.]+)*-T\d+)\b/g
const TASK_ONLY = /^[A-Z][A-Za-z0-9_.]*(?:-[A-Za-z0-9_.]+)*-T\d+$/
const RUN_ID = /^[0-9a-f]{8}$/
const RUN_WORD = /(?:^|[^\p{L}])(?:běh|run)\p{L}*\s*$/iu
const RUN_PLAIN = /(?<=(?:^|[^\p{L}])(?:běh|run)\p{L}*\s+)([0-9a-f]{8})\b/giu
const PR_PLAIN = /\b(PR\s+#?\d+)\b/g

function href(repo: string, screen: Screen, id?: string): string {
  const base = `#/r/${encodeURIComponent(repo)}/${screen}`
  return id ? `${base}/${encodeURIComponent(id)}` : base
}

function plain(text: string, repo: string): string {
  return text
    .replace(TASK_ID, (id: string) => `[${id}](${href(repo, 'backlog', id)})`)
    .replace(RUN_PLAIN, (id: string) => `[${id}](${href(repo, 'runs', id)})`)
    .replace(PR_PLAIN, (pr: string) => `[${pr}](${href(repo, 'review')})`)
}

function line(text: string, repo: string): string {
  let out = ''
  let rest = text
  while (rest) {
    const link = new RegExp(LINK.source).exec(rest)
    const code = /`([^`\n]+)`/.exec(rest)
    const next = [link, code].filter((m): m is RegExpExecArray => m !== null).sort((a, b) => a.index - b.index)[0]
    if (!next) {
      out += plain(rest, repo)
      break
    }
    const before = rest.slice(0, next.index)
    out += plain(before, repo)
    const token = next[0]
    if (next === code && code[1] !== undefined) {
      const inner = code[1]
      if (TASK_ONLY.test(inner)) out += `[${inner}](${href(repo, 'backlog', inner)})`
      else if (RUN_ID.test(inner) && RUN_WORD.test(out)) out += `[${inner}](${href(repo, 'runs', inner)})`
      else out += token
    } else {
      out += token
    }
    rest = rest.slice(next.index + token.length)
  }
  return out
}

/**
 * Markdown with dashboard links for the tasks (`P01-S01-T01`), runs (`běh 740183f7`) and
 * PRs (`PR #12`) it mentions, in repository `repo`. Fenced code and existing links stay as
 * they are; without a repository the text is unchanged.
 */
export function linkify(markdown: string, repo: string | null): string {
  if (!repo) return markdown
  let fenced = false
  return markdown
    .split('\n')
    .map((text) => {
      if (/^\s*```/.test(text)) {
        fenced = !fenced
        return text
      }
      return fenced ? text : line(text, repo)
    })
    .join('\n')
}

const ACTION_OPEN = '```haifa-action'

export interface StreamedAnswer {
  /** The streamed text without its `haifa-action` blocks. */
  text: string
  /** How many proposals the text holds so far; each shows as a placeholder card. */
  pending: number
}

/**
 * A streamed answer split for rendering: the `haifa-action` blocks, closed or still being
 * written, leave the text and count as pending proposals. Their cards come with the finished
 * message. A last line that may still grow into the block's opening fence is held back too.
 */
export function streamedAnswer(text: string): StreamedAnswer {
  const kept: string[] = []
  let pending = 0
  let inAction = false
  const lines = text.split('\n')
  lines.forEach((row, index) => {
    if (inAction) {
      if (/^```[ \t]*\r?$/.test(row)) inAction = false
      return
    }
    if (/^```haifa-action[ \t]*\r?$/.test(row)) {
      inAction = true
      pending += 1
      return
    }
    // a bare fence stays: it opens or closes any other code block
    if (index === lines.length - 1 && row.length > 3 && ACTION_OPEN.startsWith(row)) return
    kept.push(row)
  })
  return { text: kept.join('\n'), pending }
}

// ── the conversation state ───────────────────────────────────────────────────────────────

const STORE_THREAD = 'haifa.assistant.thread'
const STORE_OPEN = 'haifa.assistant.open'
const RECONNECT_MS = 1500

export interface Streaming {
  text: string
  tools: string[]
}

export const assistant = reactive({
  open: false,
  /** The thread list instead of the conversation. */
  listing: false,
  threads: null as ThreadSummary[] | null,
  threadsError: null as string | null,
  /** The open thread; null for a new thread not created yet. */
  thread: null as ThreadDetail | null,
  loading: false,
  sending: false,
  /** The answer being written: its text so far and the commands the guide ran. */
  streaming: null as Streaming | null,
  error: null as string | null,
  /** The thread being deleted. */
  deleting: null as string | null,
})

let source: EventSource | null = null
let restored = false
let generation = 0
let reconnect: ReturnType<typeof setTimeout> | null = null

function storage(): Storage | null {
  try {
    return typeof sessionStorage === 'undefined' ? null : sessionStorage
  } catch {
    return null
  }
}

function remember(): void {
  const store = storage()
  if (!store) return
  if (assistant.thread) store.setItem(STORE_THREAD, assistant.thread.id)
  else store.removeItem(STORE_THREAD)
  store.setItem(STORE_OPEN, assistant.open ? '1' : '0')
}

function closeStream(): void {
  source?.close()
  source = null
  if (reconnect !== null) clearTimeout(reconnect)
  reconnect = null
}

function finish(threadId: string, message: AssistantMessage | undefined): void {
  closeStream()
  const thread = assistant.thread
  if (!thread || thread.id !== threadId) return
  if (message && !thread.messages.some((m) => m.id === message.id)) thread.messages.push(message)
  thread.busy = false
  assistant.streaming = null
  if (assistant.threads) void loadThreads()
}

function parse(event: Event): Record<string, unknown> | null {
  const data = (event as MessageEvent).data
  if (typeof data !== 'string' || !data) return null
  try {
    return JSON.parse(data) as Record<string, unknown>
  } catch {
    return null
  }
}

/** Follow the answer of thread `id` after event `after` until it is done. */
function listen(id: string, after: number): void {
  closeStream()
  if (typeof EventSource === 'undefined') return
  let last = after
  const es = new EventSource(streamUrl(id, after))
  source = es
  const seen = (data: Record<string, unknown>) => {
    if (typeof data.seq === 'number') last = Math.max(last, data.seq)
  }
  es.addEventListener('text', (event) => {
    const data = parse(event)
    if (!data || source !== es) return
    seen(data)
    const streaming = (assistant.streaming ??= { text: '', tools: [] })
    const text = typeof data.text === 'string' ? data.text : ''
    if (text) streaming.text = streaming.text ? `${streaming.text}\n\n${text}` : text
  })
  es.addEventListener('tool', (event) => {
    const data = parse(event)
    if (!data || source !== es) return
    seen(data)
    const streaming = (assistant.streaming ??= { text: '', tools: [] })
    if (typeof data.label === 'string') streaming.tools.push(data.label)
  })
  const end = (event: Event) => {
    const data = parse(event)
    if (source !== es) return
    if (data) {
      finish(id, data.message as AssistantMessage | undefined)
      return
    }
    // the connection broke (the browser would retry on its own): read the thread again
    closeStream()
    reconnect = setTimeout(() => void refresh(id, last), RECONNECT_MS)
  }
  es.addEventListener('done', end)
  es.addEventListener('error', end)
  es.addEventListener('idle', () => {
    if (source !== es) return
    closeStream()
    void refresh(id, last)
  })
}

/** Read thread `id` again; follow its answer when it still runs. */
async function refresh(id: string, after = 0): Promise<void> {
  try {
    const detail = await fetchThread(id)
    if (assistant.thread?.id !== id) return
    assistant.thread = detail
    if (detail.busy) {
      assistant.streaming ??= { text: '', tools: [] }
      listen(id, after)
    } else {
      assistant.streaming = null
    }
  } catch (err) {
    if (assistant.thread?.id === id) assistant.error = errorText(err)
  }
}

export async function loadThreads(): Promise<void> {
  try {
    assistant.threads = await fetchThreads()
    assistant.threadsError = null
  } catch (err) {
    assistant.threadsError = errorText(err)
  }
}

/** Open thread `id` (from the list or the tab's storage). */
export async function openThread(id: string): Promise<void> {
  const mine = ++generation
  closeStream()
  assistant.listing = false
  assistant.error = null
  assistant.streaming = null
  assistant.loading = true
  try {
    const detail = await fetchThread(id)
    if (mine !== generation) return
    assistant.thread = detail
    remember()
    if (detail.busy) {
      assistant.streaming = { text: '', tools: [] }
      // the events of the current answer are all kept: replay them from the start
      listen(id, 0)
    }
  } catch (err) {
    if (mine !== generation) return
    assistant.thread = null
    remember()
    if (!(err instanceof ApiError && err.code === 'unknown_thread')) assistant.error = errorText(err)
  } finally {
    if (mine === generation) assistant.loading = false
  }
}

/** A new, empty thread; it is created with its first message. */
export function newThread(): void {
  generation++
  closeStream()
  assistant.thread = null
  assistant.listing = false
  assistant.streaming = null
  assistant.error = null
  remember()
}

/**
 * Delete thread `id` for good. It leaves the list; when it is the open thread, the panel
 * shows a new, empty thread. A failure (e.g. 409 busy) shows in the thread list.
 */
export async function deleteThread(id: string): Promise<boolean> {
  if (assistant.deleting) return false
  assistant.deleting = id
  assistant.threadsError = null
  try {
    try {
      await deleteThreadRequest(id)
    } catch (err) {
      // deleted meanwhile (another tab): it is gone all the same
      if (!(err instanceof ApiError && err.code === 'unknown_thread')) throw err
    }
    if (assistant.threads) assistant.threads = assistant.threads.filter((t) => t.id !== id)
    if (assistant.thread?.id === id) {
      generation++
      closeStream()
      assistant.thread = null
      assistant.streaming = null
      assistant.error = null
      remember()
    }
    return true
  } catch (err) {
    assistant.threadsError = errorText(err)
    return false
  } finally {
    assistant.deleting = null
  }
}

export function showThreads(show = true): void {
  assistant.listing = show
  if (show) void loadThreads()
}

export function setOpen(open: boolean): void {
  assistant.open = open
  storage()?.setItem(STORE_OPEN, open ? '1' : '0')
  if (open && !restored) {
    restored = true
    const id = storage()?.getItem(STORE_THREAD)
    if (id && !assistant.thread) void openThread(id)
  }
}

export function toggleOpen(): void {
  setOpen(!assistant.open)
}

/** The panel was open in this tab before a reload. */
export function restoreOpen(): void {
  if (storage()?.getItem(STORE_OPEN) === '1') setOpen(true)
}

/** Send `text` with the screen context; creates the thread when it is new. */
export async function send(text: string, screen: ScreenContext | null): Promise<boolean> {
  const body = text.trim()
  if (!body || assistant.sending || assistant.thread?.busy) return false
  const mine = generation
  assistant.sending = true
  assistant.error = null
  try {
    if (!assistant.thread) {
      const created = await createThread()
      if (mine !== generation) return false
      assistant.thread = created
      remember()
    }
    const id = assistant.thread.id
    const result = await sendMessage(id, body, screen)
    // the reactive thread, unless the user opened another one meanwhile
    const thread = assistant.thread
    if (thread?.id !== id) return true
    const message = { ...result.message, screen: result.message.screen ?? screen ?? undefined }
    thread.messages.push(message)
    thread.title = result.thread.title
    thread.busy = true
    thread.seq = result.seq
    assistant.streaming = { text: '', tools: [] }
    listen(thread.id, result.seq)
    if (assistant.threads) void loadThreads()
    return true
  } catch (err) {
    assistant.error = errorText(err)
    return false
  } finally {
    assistant.sending = false
  }
}

/** The state of a run (`failed`, `running`, …) for the suggested questions; null when unknown. */
export async function runState(runId: string): Promise<string | null> {
  try {
    const detail = await getApi<{ run?: { state?: string } }>(`/runs/${encodeURIComponent(runId)}`)
    return detail.run?.state ?? null
  } catch {
    return null
  }
}

/** Test helper: an empty, closed panel without a stream. */
export function resetAssistantForTests(): void {
  closeStream()
  generation++
  restored = false
  Object.assign(assistant, {
    open: false,
    listing: false,
    threads: null,
    threadsError: null,
    thread: null,
    loading: false,
    sending: false,
    streaming: null,
    error: null,
    deleting: null,
  })
  running.clear()
  storage()?.removeItem(STORE_THREAD)
  storage()?.removeItem(STORE_OPEN)
}
