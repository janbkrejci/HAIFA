// Live updates from GET /api/repos/<id>/live (Server-Sent Events, aifactory/web/live.py).
// One shared EventSource per tab for the repo in the URL, opened while someone listens and the
// tab is visible; a hidden tab holds no connection, a visible one reconnects and resyncs.
import { onBeforeUnmount, onMounted } from 'vue'
import { apiBase } from './api'
import { currentRepoId } from './router'

export type LiveArea = 'backlog' | 'factory'

export interface LiveFilesEvent {
  seq: number
  areas: LiveArea[]
  paths: string[]
  truncated: boolean
}

export interface LiveTraceEvent {
  seq: number
  events: number
  phases: number
  run_ids: string[]
  task_ids: string[]
  runs_changed: boolean
}

export interface LiveHandlers {
  files?: (event: LiveFilesEvent) => void
  trace?: (event: LiveTraceEvent) => void
  /** Events may have been missed (reconnect, slow client): reload the screen. */
  resync?: () => void
}

/** Events closer together than this are merged into one call of a handler. */
export const LIVE_DEBOUNCE_MS = 300

interface Subscriber {
  handlers: LiveHandlers
  files: LiveFilesEvent | null
  trace: LiveTraceEvent | null
  resync: boolean
  timer: ReturnType<typeof setTimeout> | null
}

const subscribers = new Set<Subscriber>()
let source: EventSource | null = null
let openRepo: string | null = null
let hellos = 0
let visibilityHooked = false

function mergeFiles(a: LiveFilesEvent | null, b: LiveFilesEvent): LiveFilesEvent {
  if (!a) return b
  return {
    seq: Math.max(a.seq, b.seq),
    areas: [...new Set([...a.areas, ...b.areas])].sort(),
    paths: [...new Set([...a.paths, ...b.paths])].sort(),
    truncated: a.truncated || b.truncated,
  }
}

function mergeTrace(a: LiveTraceEvent | null, b: LiveTraceEvent): LiveTraceEvent {
  if (!a) return b
  return {
    seq: Math.max(a.seq, b.seq),
    events: Math.max(a.events, b.events),
    phases: Math.max(a.phases, b.phases),
    run_ids: [...new Set([...a.run_ids, ...b.run_ids])].sort(),
    task_ids: [...new Set([...a.task_ids, ...b.task_ids])].sort(),
    runs_changed: a.runs_changed || b.runs_changed,
  }
}

function flush(sub: Subscriber) {
  sub.timer = null
  const { files, trace, resync } = sub
  sub.files = null
  sub.trace = null
  sub.resync = false
  if (resync) {
    sub.handlers.resync?.()
    return
  }
  if (files) sub.handlers.files?.(files)
  if (trace) sub.handlers.trace?.(trace)
}

function schedule(sub: Subscriber) {
  if (sub.timer === null) sub.timer = setTimeout(() => flush(sub), LIVE_DEBOUNCE_MS)
}

function parse(event: Event): Record<string, unknown> | null {
  const raw = (event as MessageEvent).data
  if (typeof raw !== 'string') return null
  try {
    const data: unknown = JSON.parse(raw)
    return typeof data === 'object' && data !== null ? (data as Record<string, unknown>) : null
  } catch {
    return null
  }
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
}

function num(value: unknown): number {
  return typeof value === 'number' ? value : 0
}

function toFiles(data: Record<string, unknown>): LiveFilesEvent {
  return {
    seq: num(data.seq),
    areas: strings(data.areas).filter((a): a is LiveArea => a === 'backlog' || a === 'factory'),
    paths: strings(data.paths),
    truncated: data.truncated === true,
  }
}

function toTrace(data: Record<string, unknown>): LiveTraceEvent {
  return {
    seq: num(data.seq),
    events: num(data.events),
    phases: num(data.phases),
    run_ids: strings(data.run_ids),
    task_ids: strings(data.task_ids),
    runs_changed: data.runs_changed === true,
  }
}

function resyncAll() {
  for (const sub of subscribers) {
    sub.resync = true
    schedule(sub)
  }
}

function hidden(): boolean {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden'
}

function open() {
  // a source of another repo never serves this one (the repo screen normally remounts anyway)
  if (source && openRepo !== currentRepoId()) close()
  if (source || typeof EventSource === 'undefined' || hidden()) return
  const repo = currentRepoId()
  if (repo === null) return
  hellos = 0
  const es = new EventSource(`${apiBase()}/live`)
  openRepo = repo
  es.addEventListener('hello', () => {
    // a second hello means the browser reconnected: events may have been missed
    hellos += 1
    if (hellos > 1) resyncAll()
  })
  es.addEventListener('files', (event) => {
    const data = parse(event)
    if (!data) return
    const files = toFiles(data)
    for (const sub of subscribers) {
      sub.files = mergeFiles(sub.files, files)
      schedule(sub)
    }
  })
  es.addEventListener('trace', (event) => {
    const data = parse(event)
    if (!data) return
    const trace = toTrace(data)
    for (const sub of subscribers) {
      sub.trace = mergeTrace(sub.trace, trace)
      schedule(sub)
    }
  })
  es.addEventListener('resync', () => resyncAll())
  source = es
}

function close() {
  source?.close()
  source = null
  openRepo = null
}

function onVisibility() {
  if (hidden()) {
    close()
  } else if (subscribers.size > 0 && !source) {
    open()
    resyncAll()
  }
}

function hookVisibility() {
  if (visibilityHooked || typeof document === 'undefined') return
  visibilityHooked = true
  document.addEventListener('visibilitychange', onVisibility)
}

/** Listen to live updates; returns the unsubscribe function. */
export function onLive(handlers: LiveHandlers): () => void {
  const sub: Subscriber = { handlers, files: null, trace: null, resync: false, timer: null }
  subscribers.add(sub)
  hookVisibility()
  open()
  return () => {
    if (sub.timer !== null) clearTimeout(sub.timer)
    subscribers.delete(sub)
    if (subscribers.size === 0) close()
  }
}

/** `onLive` for the lifetime of a component. */
export function useLive(handlers: LiveHandlers): void {
  let off: (() => void) | null = null
  onMounted(() => {
    off = onLive(handlers)
  })
  onBeforeUnmount(() => {
    off?.()
    off = null
  })
}

function basename(path: string): string {
  const parts = path.split('/')
  return parts[parts.length - 1] ?? ''
}

/** Some path is the file of task `taskId` (`<id>-<slug>.md` or `<id>.md`). */
export function touchesTask(paths: string[], taskId: string): boolean {
  return paths.some((p) => {
    const name = basename(p)
    return name === `${taskId}.md` || name.startsWith(`${taskId}-`)
  })
}

/** Some path lies in (or is the index of) module/step `containerId`. */
export function touchesContainer(paths: string[], containerId: string): boolean {
  return paths.some((p) =>
    p.split('/').some((seg) => seg === containerId || seg.startsWith(`${containerId}-`)),
  )
}

/** Some path is a workflow or the shared config (the backlog's workflows and steps). */
export function touchesWorkflows(paths: string[]): boolean {
  return paths.some((p) => p.startsWith('.factory/workflows/') || p === '.factory/config.yaml')
}

/** Test helper: forget the shared EventSource and every subscriber. */
export function resetLiveForTests(): void {
  for (const sub of subscribers) if (sub.timer !== null) clearTimeout(sub.timer)
  subscribers.clear()
  close()
  hellos = 0
}
