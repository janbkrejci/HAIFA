// The AI guide panel: its API (/api/assistant/…), the conversation state shared by every
// screen, the screen context sent with a message, the suggested questions of an empty thread
// and the dashboard links in an answer.
//
// The state lives at module level, so the open thread survives every screen change; the id of
// the open thread and whether the panel is open are kept for the tab (sessionStorage).
import { reactive } from 'vue'
import { ApiError, getApi, getGlobal, postGlobal } from './api'
import { errorText } from './format'
import { GRAPH, NEW_CONTAINER, NEW_STEP, NEW_TASK, type Page, type Screen } from './router'

// ── API ──────────────────────────────────────────────────────────────────────────────────

/** The screen the user is looking at, sent with a message (`screen` of the API). */
export interface ScreenContext {
  repo?: string
  task?: string
  run?: string
}

export interface AssistantMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  screen?: ScreenContext
  at?: string
  error?: string
  usage?: { tokens: number; cost_usd: number }
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

export function sendMessage(id: string, text: string, screen: ScreenContext | null): Promise<SendResult> {
  const body: { text: string; screen?: ScreenContext } = { text }
  if (screen && Object.keys(screen).length) body.screen = screen
  return postGlobal<SendResult>(`${THREADS}/${encodeURIComponent(id)}/messages`, body)
}

export function streamUrl(id: string, after: number): string {
  return `/api${THREADS}/${encodeURIComponent(id)}/stream?after=${after}`
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
  })
  storage()?.removeItem(STORE_THREAD)
  storage()?.removeItem(STORE_OPEN)
}
