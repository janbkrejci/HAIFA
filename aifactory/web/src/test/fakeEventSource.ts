// A stand-in for the browser's EventSource (happy-dom has none): tests dispatch events.
export class FakeEventSource {
  static instances: FakeEventSource[] = []
  readonly url: string
  closed = false
  private listeners = new Map<string, ((event: Event) => void)[]>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: (event: Event) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener])
  }

  close() {
    this.closed = true
  }

  emit(type: string, data: unknown = {}) {
    const event = new MessageEvent(type, { data: JSON.stringify(data) })
    for (const listener of this.listeners.get(type) ?? []) listener(event)
  }

  static latest(): FakeEventSource {
    const last = FakeEventSource.instances[FakeEventSource.instances.length - 1]
    if (!last) throw new Error('no EventSource was opened')
    return last
  }

  static reset() {
    FakeEventSource.instances = []
  }
}

export function filesEvent(paths: string[], areas: string[] = ['backlog'], seq = 1) {
  return { seq, areas, paths, truncated: false }
}

export function traceEvent(fields: Record<string, unknown> = {}) {
  return { seq: 1, events: 0, phases: 0, run_ids: [], task_ids: [], runs_changed: false, ...fields }
}
