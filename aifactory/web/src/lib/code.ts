// HAIFA builds itself: a merge into this repo can change the aifactory package under the running
// dashboard. /api/code says whether the code on disk differs from the one the server started
// with; /api/restart replaces the server process. Writes are refused (409 stale_code) meanwhile.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { getGlobal, postGlobal } from './api'
import { t } from './i18n'
import { errorText } from './format'

export interface CodeState {
  stale: boolean
  started: string
  current: string
}

export function fetchCode(): Promise<CodeState> {
  return getGlobal<CodeState>('/code')
}

export function restartDashboard(): Promise<{ restarting: boolean }> {
  return postGlobal<{ restarting: boolean }>('/restart')
}

export const CODE_POLL_MS = 15_000
export const RESTART_POLL_MS = 1_000
export const RESTART_TIMEOUT_MS = 60_000

export interface CodeStateOptions {
  /** Reloads the page once the restarted server answers (default: `location.reload`). */
  reload?: () => void
  /** Waits between checks of the restarted server (default: a timer). */
  wait?: (ms: number) => Promise<void>
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

/** Polls /api/code; `restart()` restarts the server and reloads the page when it is back. */
export function useCodeState(options: CodeStateOptions = {}) {
  const stale = ref(false)
  const restarting = ref(false)
  const restartError = ref<string | null>(null)
  const timedOut = ref(false)
  const error = computed(() => timedOut.value ? t('code.timeout') : restartError.value === null ? null : t('code.failed', { error: restartError.value }))
  let started: string | null = null
  let timer: ReturnType<typeof setInterval> | null = null

  async function check(): Promise<void> {
    try {
      const state = await fetchCode()
      started ??= state.started
      stale.value = state.stale === true
    } catch {
      // a restarting or stopped server: keep the last known state
    }
  }

  async function restart(): Promise<void> {
    restarting.value = true
    restartError.value = null
    timedOut.value = false
    const before = started
    try {
      await restartDashboard()
    } catch (e) {
      restarting.value = false
      restartError.value = errorText(e)
      return
    }
    const wait = options.wait ?? sleep
    for (let waited = 0; waited < RESTART_TIMEOUT_MS; waited += RESTART_POLL_MS) {
      await wait(RESTART_POLL_MS)
      try {
        const state = await fetchCode()
        if (state.started !== before && !state.stale) {
          ;(options.reload ?? (() => window.location.reload()))()
          return
        }
      } catch {
        // the new server is not listening yet
      }
    }
    restarting.value = false
    timedOut.value = true
  }

  const onFocus = () => void check()
  onMounted(() => {
    void check()
    timer = setInterval(() => void check(), CODE_POLL_MS)
    window.addEventListener('focus', onFocus)
  })
  onBeforeUnmount(() => {
    if (timer !== null) clearInterval(timer)
    window.removeEventListener('focus', onFocus)
  })

  return { stale, restarting, error, check, restart }
}
