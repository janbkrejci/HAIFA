import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ApiError, getGlobal, postGlobal } from './api'
import { fetchCode } from './code'
import { errorText } from './format'

export type UpdateErrorCode = 'check_failed' | 'invalid_response' | 'install_failed' | 'restart_timeout' | 'runs_active' | 'update_busy'

export interface UpdateState {
  // 'waiting' is client-side only: the server refused to install while task runs are active.
  status: 'checking' | 'current' | 'available' | 'waiting' | 'error' | 'installing'
  current_version: string
  target_version?: string
  error_code?: UpdateErrorCode
  /** Original diagnostic only; never used as a user-facing instruction. */
  error?: string | null
}
function updateErrorCode(error: unknown, fallback: UpdateErrorCode): UpdateErrorCode {
  if (error instanceof ApiError && ['runs_active', 'update_busy', 'invalid_response', 'install_failed', 'restart_timeout'].includes(error.code)) return error.code as UpdateErrorCode
  return fallback
}

export function useUpdates(options: { reload?: () => void; wait?: (ms: number) => Promise<void>; migration?: boolean } = {}) {
  const state = ref<UpdateState>({ status: 'checking', current_version: '' })
  let busy = false
  let disposed = false
  let timer: ReturnType<typeof setInterval> | null = null
  const wait = options.wait ?? ((ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms)))
  async function check(fresh = false) {
    if (busy || disposed) return
    busy = true
    state.value = { ...state.value, status: 'checking', error: null, error_code: undefined }
    try {
      const result = await getGlobal<UpdateState>(`/updates${fresh ? '?fresh=1' : ''}`)
      if (!result || !['current', 'available', 'error', 'installing'].includes(result.status)) throw new ApiError('invalid_response', 'Invalid update check response')
      if (!disposed) {
        state.value = { ...result, error_code: result.status === 'error' ? (result.error_code ?? 'check_failed') : undefined }
        if (result.status === 'installing') await watchRestart((await fetchCode()).started, result.current_version)
      }
    } catch (error) { if (!disposed) state.value = { ...state.value, status: 'error', error_code: updateErrorCode(error, 'check_failed'), error: errorText(error) } }
    finally { busy = false }
  }
  async function install() {
    if (busy || disposed) return
    busy = true
    state.value = { ...state.value, status: 'installing', error: null, error_code: undefined }
    try {
      const before = await fetchCode()
      await postGlobal<UpdateState>(options.migration ? '/updates/migrate' : '/updates/install')
      await watchRestart(before.started, state.value.current_version)
    } catch (error) {
      if (!disposed) state.value = { ...state.value, status: error instanceof ApiError && ['runs_active', 'update_busy'].includes(error.code) ? 'waiting' : 'error', error_code: updateErrorCode(error, 'install_failed'), error: errorText(error) }
    }
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
        if (progress.status === 'error') throw new ApiError(progress.error_code ?? 'install_failed', progress.error ?? 'Update installation failed')
      }
      if (!disposed) throw new ApiError('restart_timeout', 'Dashboard restart was not detected within 300 seconds')
  }
  function activate() { if (state.value.status === 'available' || state.value.status === 'waiting') void install(); else void check(true) }
  onMounted(() => { void check(); timer = setInterval(() => void check(), 30 * 60 * 1000) })
  onBeforeUnmount(() => { disposed = true; if (timer) clearInterval(timer) })
  return { state, check, install, activate }
}
