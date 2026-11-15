import { ApiError, DB_BUSY_CODE } from './api'
import { errorText } from './format'
import { t } from './i18n'
import type { MessageKey } from './i18n/catalogs'

/** API codes are UI state; the original server message remains diagnostic content. */
export function runError(error: unknown): string {
  if (!(error instanceof ApiError)) return errorText(error)
  const keys: Record<string, MessageKey> = {
    [DB_BUSY_CODE]: 'runs.apiBusy',
    request_timeout: 'runs.apiTimeout',
    unknown_run: 'runs.apiUnknownRun',
    unknown_phase: 'runs.apiUnknownPhase',
    remote_run: 'runs.apiRemote',
    task_busy: 'runs.apiTaskBusy',
    already_running: 'runs.apiTaskBusy',
    invalid_state: 'runs.apiInvalidState',
    run_not_running: 'runs.apiInvalidState',
    run_running: 'runs.apiInvalidState',
  }
  return t(keys[error.code] ?? 'runs.apiFailure', { code: error.code })
}
