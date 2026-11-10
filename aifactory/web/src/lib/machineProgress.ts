// What a running check of this computer waits for, and how long it may take.
// The server bounds one machine check to its budget (web/machine.py CHECK_BUDGET, 60 s) and
// answers `check_timeout` past it; the page adds a margin for the follow-up requests
// (library, repositories, roster, backlog), so no step leaves the UI checking for ever.
import { fetchMachineProgress, type MachineProgress } from './api'
import { fmtAge, fmtTime } from './format'

/** The whole check as the page waits for it: the server budget plus the follow-up requests. */
export const CHECK_DEADLINE_MS = 75_000
/** How often the elapsed time and the server's step are refreshed. */
export const PROGRESS_TICK_MS = 1_000
/** From this many seconds on, the step and elapsed time are shown next to the spinner. */
export const PROGRESS_SHOWN_AFTER = 2

/** The check did not finish before the page's deadline; `step` is what it waited for. */
export class CheckTimeout extends Error {
  constructor(readonly step: string, readonly seconds: number) {
    super(`Kontrola nedoběhla do ${seconds} s; nedokončený krok: ${step}`)
    this.name = 'CheckTimeout'
  }
}

/** The server's step in words: "machine: logins (claude auth status)". */
export function serverStep(progress: MachineProgress | null | undefined): string | null {
  if (!progress) return null
  return progress.detail ? `${progress.step} (${progress.detail})` : progress.step
}

/** "z 10. 11. 2026 12:00:00 (před 5 min)" for a last known result, or null without one. */
export function lastKnown(checkedAt: string | null | undefined, now = Date.now()): string | null {
  if (!checkedAt) return null
  const at = new Date(checkedAt).getTime()
  if (!Number.isFinite(at)) return null
  return `z ${fmtTime(checkedAt)} (${fmtAge((now - at) / 1000)})`
}

/**
 * Follow a running check: `onTick` gets the elapsed seconds every second and the server's
 * step whenever `poll()` says the machine check is still pending. Returns the stop function.
 */
export function followProgress(
  onTick: (elapsed: number, step: string | null) => void,
  poll: () => boolean,
): () => void {
  let ticks = 0
  let stopped = false
  let timer: ReturnType<typeof setTimeout> | undefined
  let step: string | null = null
  let asking = false
  async function ask() {
    if (asking) return
    asking = true
    try {
      const { job } = await fetchMachineProgress()
      if (!stopped) step = serverStep(job)
    } catch {
      // The progress is a hint only; the check itself reports its failure.
    } finally { asking = false }
  }
  function tick() {
    if (stopped) return
    ticks += 1
    const elapsed = Math.round((ticks * PROGRESS_TICK_MS) / 1000)
    if (poll()) void ask()
    else step = null
    onTick(elapsed, step)
    timer = setTimeout(tick, PROGRESS_TICK_MS)
  }
  timer = setTimeout(tick, PROGRESS_TICK_MS)
  return () => { stopped = true; clearTimeout(timer) }
}

/** `promise`, or a CheckTimeout naming `step()` once `deadline` (Date.now() ms) passes. */
export function beforeDeadline<T>(promise: Promise<T>, deadline: number, step: () => string, seconds: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  const late = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new CheckTimeout(step(), seconds)), Math.max(0, deadline - Date.now()))
  })
  return Promise.race([promise, late]).finally(() => clearTimeout(timer))
}
