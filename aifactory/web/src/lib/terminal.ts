import { ApiError, type Envelope } from './api'

async function readEnvelope<T>(response: Response): Promise<T> {
  const envelope = await response.json() as Envelope<T>
  if (!response.ok || !envelope.ok || envelope.data === null) {
    throw new ApiError(envelope.error?.code ?? 'terminal_error', envelope.error?.message ?? `Terminál: HTTP ${response.status}`)
  }
  return envelope.data
}

export interface TerminalInfo { enabled: boolean; cwd: string; shell: string; pty: boolean }
export interface TerminalSize { cols: number; rows: number }
const sessions = '/api/terminal/sessions'
const sessionUrl = (id: string) => `${sessions}/${encodeURIComponent(id)}`

export async function fetchTerminal(signal?: AbortSignal): Promise<TerminalInfo> {
  return readEnvelope<TerminalInfo>(await fetch('/api/terminal', { signal }))
}

export async function createTerminalSession(size: TerminalSize, cwd: string): Promise<{ id: string }> {
  // Do not abort creation: even a late response must be deleted by the owner.
  return readEnvelope(await fetch(sessions, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...size, cwd }), keepalive: true,
  }))
}

export async function inputTerminal(id: string, data: string, signal?: AbortSignal): Promise<void> {
  await readEnvelope(await fetch(`${sessionUrl(id)}/input`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data }), signal,
  }))
}

export async function resizeTerminal(id: string, size: TerminalSize, signal?: AbortSignal): Promise<void> {
  await readEnvelope(await fetch(`${sessionUrl(id)}/resize`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(size), signal,
  }))
}

export async function deleteTerminalSession(id: string): Promise<void> {
  await readEnvelope(await fetch(sessionUrl(id), { method: 'DELETE', keepalive: true }))
}

/** Preserve raw UTF-8/VT bytes, including sequences split between chunks. */
export async function streamTerminal(
  id: string, signal: AbortSignal, onBytes: (bytes: Uint8Array) => void,
): Promise<void> {
  const response = await fetch(`${sessionUrl(id)}/stream`, { signal })
  if (!response.ok) {
    await readEnvelope(response)
    throw new Error(`Terminál: HTTP ${response.status}`)
  }
  if (!response.body) throw new Error('Terminál neposlal výstupní stream.')
  const reader = response.body.getReader()
  const cancel = () => { void reader.cancel().catch(() => {}) }
  signal.addEventListener('abort', cancel, { once: true })
  try {
    while (!signal.aborted) {
      const { done, value } = await reader.read()
      if (done || signal.aborted) break
      onBytes(value)
    }
  } finally {
    signal.removeEventListener('abort', cancel)
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
