import { ApiError } from './api'
import { errorText } from './format'
import { t } from './i18n'
import { runError } from './runMessages'

/** Translate stable API codes without interpreting provider or agent prose. */
export function reviewError(error: unknown): string {
  if (!(error instanceof ApiError)) return errorText(error)
  switch (error.code) {
    case 'conflict': return t('review.apiConflict')
    case 'no_pr': return t('review.apiNoPr')
    case 'missing_note': return t('review.apiMissingNote')
    case 'pr_not_open': return t('review.apiNotOpen')
    case 'trace_db_locked':
    case 'request_timeout':
    case 'task_busy':
    case 'already_running':
    case 'run_running': return runError(error)
    default: return t('review.apiFailure', { code: error.code })
  }
}
