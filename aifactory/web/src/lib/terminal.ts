import { ApiError, type Envelope } from './api'

async function readEnvelope<T>(response: Response): Promise<T> {
  const envelope = await response.json() as Envelope<T>
  if (!response.ok || !envelope.ok || envelope.data === null) {
    throw new ApiError(envelope.error?.code ?? 'terminal_error', envelope.error?.message ?? `Terminál: HTTP ${response.status}`)
  }
  return envelope.data
}

export interface TerminalInfo { enabled: boolean; cwd: string; shell: string }
export type TerminalEvent =
  | { type: 'out'; stream: 'stdout' | 'stderr'; text: string }
  | { type: 'exit'; code: number; cwd: string }

export async function fetchTerminal(signal?: AbortSignal): Promise<TerminalInfo> {
  return readEnvelope<TerminalInfo>(await fetch('/api/terminal', { signal }))
}

/** The caller owns the controller so closing the overlay also disconnects the process. */
export async function execTerminal(
  command: string, cwd: string, signal: AbortSignal, onEvent: (event: TerminalEvent) => void,
): Promise<void> {
  const response = await fetch('/api/terminal/exec', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command, cwd }), signal,
  })
  if (!response.ok) {
    await readEnvelope(response)
    throw new Error(`Terminál: HTTP ${response.status}`)
  }
  if (!response.body) throw new Error('Terminál neposlal výstupní stream.')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let pending = ''
  let exited = false
  function line(text: string) {
    if (!text.trim()) return
    const event = JSON.parse(text) as TerminalEvent
    if (event.type === 'exit') exited = true
    onEvent(event)
  }
  try {
    while (true) {
      const { done, value } = await reader.read()
      pending += decoder.decode(value, { stream: !done })
      let end: number
      while ((end = pending.indexOf('\n')) !== -1) {
        line(pending.slice(0, end))
        pending = pending.slice(end + 1)
      }
      if (done) break
    }
    line(pending)
    if (!exited) throw new Error('Spojení s terminálem skončilo bez návratového kódu.')
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
