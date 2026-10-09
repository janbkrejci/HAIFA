import { onBeforeUnmount, onMounted, ref } from 'vue'
import { getGlobal, postGlobal } from './api'
import { fetchCode } from './code'
import { errorText } from './format'

export interface UpdateState {
  status: 'checking' | 'current' | 'available' | 'error' | 'installing'
  current_version: string
  target_version?: string
  error?: string | null
}
export function useUpdates(options: { reload?: () => void; wait?: (ms: number) => Promise<void> } = {}) {
  const state = ref<UpdateState>({ status: 'checking', current_version: '' })
  let busy = false
  let disposed = false
  let timer: ReturnType<typeof setInterval> | null = null
  const wait = options.wait ?? ((ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms)))
  async function check(fresh = false) {
    if (busy || disposed) return
    busy = true
    state.value = { ...state.value, status: 'checking', error: null }
    try {
      const result = await getGlobal<UpdateState>(`/updates${fresh ? '?fresh=1' : ''}`)
      if (!result || !['current', 'available', 'error', 'installing'].includes(result.status)) throw new Error('Neplatná odpověď kontroly aktualizací.')
      if (!disposed) {
        state.value = result
        if (result.status === 'installing') await watchRestart((await fetchCode()).started, result.current_version)
      }
    } catch (error) { if (!disposed) state.value = { ...state.value, status: 'error', error: errorText(error) } }
    finally { busy = false }
  }
  async function install() {
    if (busy || disposed) return
    busy = true
    state.value = { ...state.value, status: 'installing', error: null }
    try {
      const before = await fetchCode()
      await postGlobal<UpdateState>('/updates/install')
      await watchRestart(before.started, state.value.current_version)
    } catch (error) { if (!disposed) state.value = { ...state.value, status: 'error', error: errorText(error) } }
    finally { busy = false }
  }
  async function watchRestart(started: string, currentVersion: string) {
      for (let elapsed = 0; elapsed < 300_000 && !disposed; elapsed += 1000) {
        await wait(1000)
        if (disposed) return
        let progress: UpdateState
        try {
          const code = await fetchCode()
          if (code.started !== started && !code.stale) {
            // Server startup runs fresh checks; the reloaded UI reads their results.
            ;(options.reload ?? (() => window.location.reload()))()
            return
          }
          progress = await getGlobal<UpdateState>('/updates')
        } catch {
          // The server may be unavailable while its process is replaced.
          continue
        }
        if (progress.current_version !== currentVersion) {
          ;(options.reload ?? (() => window.location.reload()))()
          return
        }
        if (progress.status === 'error') throw new Error(progress.error ?? 'Aktualizace selhala.')
      }
      if (!disposed) throw new Error('Aktualizace se do pěti minut nedokončila. Zkontroluj běžící dashboard.')
  }
  function activate() { if (state.value.status === 'available') void install(); else void check(true) }
  onMounted(() => { void check(); timer = setInterval(() => void check(), 30 * 60 * 1000) })
  onBeforeUnmount(() => { disposed = true; if (timer) clearInterval(timer) })
  return { state, check, install, activate }
}
