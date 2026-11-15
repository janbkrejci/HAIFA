import { ApiError } from './api'
import { dashboardError } from './dashboardMessages'
import { t } from './i18n'
import type { MessageKey } from './i18n/catalogs'
import type { IntentProgress } from './intent'

const errorKeys: Record<string, MessageKey> = {
  advice_invalid: 'backlog.error.advice_invalid',
  proposal_failed: 'backlog.error.proposal_failed',
  task_advice_failed: 'backlog.error.task_advice_failed',
  workflow_advice_failed: 'backlog.error.workflow_advice_failed',
  backlog_invalid: 'backlog.error.backlog_invalid',

  unmet_dependencies: 'backlog.error.unmet_dependencies',
  invalid_value: 'backlog.error.invalid_value',
  duplicate_id: 'backlog.error.duplicate_id',
  unknown_ref: 'backlog.error.unknown_ref',
  unknown_workflow: 'backlog.error.unknown_workflow',
  task_changed: 'backlog.error.task_changed',
  stale_revision: 'backlog.error.task_changed',
  follow_up_exists: 'backlog.error.follow_up_exists',
  not_in_base: 'backlog.error.not_in_base',
}

export function backlogError(error: { code?: string; message: string }): string {
  const key = errorKeys[error.code ?? '']
  if (key) return t(key)
  return error.code ? dashboardError(new ApiError(error.code, error.message)) : error.message
}

/** Structured progress metadata is UI; tool names and agent output remain verbatim. */
export function intentProgressText(item: IntentProgress): string {
  const params = item.params ?? {}
  switch (item.code) {
    case 'agent_start': return t('backlog.progress.agentStart', { name: params.name ?? '', model: params.model ? ` (${params.model})` : '' })
    case 'gate_fail': return t('backlog.progress.gateFail')
    case 'provider_backoff': return t('backlog.progress.backoff')
    case 'session_fallback': return t('backlog.progress.sessionFallback')
    case 'agent_end': return t('backlog.progress.agentEnd')
    case 'error': return t('backlog.progress.error', { error: params.error ?? '' })
    default: return item.text
  }
}

export function documentProblem(problem: string | null): string {
  switch (problem) {
    case 'file too large to show': return t('backlog.document.tooLarge')
    case 'outside the repository': return t('backlog.document.outside')
    case 'not a markdown file': return t('backlog.document.notMarkdown')
    default: return problem ?? ''
  }
}
