import { t, locale } from './i18n'
import type { BoardState } from './backlog'
import { ApiError, type OverviewAutoAction, type OverviewWarning } from './api'

export function dashboardStateLabel(value: BoardState): string {
  switch (value) {
    case 'todo': return t('dashboard.state.todo')
    case 'ready': return t('dashboard.state.ready')
    case 'human': return t('dashboard.state.human')
    case 'blocked': return t('dashboard.state.blocked')
    case 'failed': return t('dashboard.state.failed')
    case 'running': return t('dashboard.state.running')
    case 'in review': return t('dashboard.state.in_review')
    case 'approved': return t('dashboard.state.approved')
    case 'awaiting merge': return t('dashboard.state.awaiting_merge')
    case 'done': return t('dashboard.state.done')
    case 'cancelled': return t('dashboard.state.cancelled')
    default: return value ?? ''
  }
}

export function dashboardFailureLabel(value: string | null | undefined): string {
  switch (value) {
    case 'accept_not_met': return t('dashboard.failure.accept_not_met')
    case 'nothing_to_do': return t('dashboard.failure.nothing_to_do')
    case 'needs_environment': return t('dashboard.failure.needs_environment')
    case 'quota': return t('dashboard.failure.quota')
    case 'writes_violation': return t('dashboard.failure.writes_violation')
    case 'writes_needed': return t('dashboard.failure.writes_needed')
    case 'invalid_output': return t('dashboard.failure.invalid_output')
    case 'process_gone': return t('dashboard.failure.process_gone')
    case 'stopped': return t('dashboard.failure.stopped')
    case 'blocked': return t('dashboard.failure.blocked')
    case 'other': return t('dashboard.failure.other')
    default: return value ?? ''
  }
}

export function autoActionText(action: OverviewAutoAction): string {
  const names: Record<string, string> = { claude: 'Claude Code', codex: 'Codex', pi: 'Pi' }
  const from = action.detail?.from?.harness
  const to = action.detail?.to?.harness
  const params = { run: action.run_id, task: action.task_id,
    from: locale.value === 'cs' && from === 'codex' ? 'Codexu' : names[from ?? ''] ?? from ?? '—',
    to: names[to ?? ''] ?? to ?? '—' }
  switch (action.action) {
    case 'fallback': return t(action.ok ? 'dashboard.fallbackOk' : 'dashboard.fallbackFailed', params)
    case 'retry': return t(action.ok ? 'dashboard.retryOk' : 'dashboard.retryFailed', params)
    case 'close': return t(action.ok ? 'dashboard.closeOk' : 'dashboard.closeFailed', params)
    default: return action.text
  }
}

/** Interpret stable protocol codes, never server prose or user-authored strings. */
export function findingTitle(code: string): string {
  switch (code) {
    case 'unsupported_platform': return t('dashboard.finding.unsupported_platform')
    case 'git_missing': return t('dashboard.finding.git_missing')
    case 'git_identity_missing': return t('dashboard.finding.git_identity_missing')
    case 'uv_missing': return t('dashboard.finding.uv_missing')
    case 'node_missing': return t('dashboard.finding.node_missing')
    case 'harness_missing': return t('dashboard.finding.harness_missing')
    case 'harness_test_failed': return t('dashboard.finding.harness_test_failed')
    case 'harness_login_missing': return t('dashboard.finding.harness_login_missing')
    case 'harness_login_failed': return t('dashboard.finding.harness_login_failed')
    case 'library_missing': return t('dashboard.finding.library_missing')
    case 'library_dirty': return t('dashboard.finding.library_dirty')
    case 'library_behind': return t('dashboard.finding.library_behind')
    case 'library_unpushed': return t('dashboard.finding.library_unpushed')
    case 'factory_outdated': return t('dashboard.finding.factory_outdated')
    case 'az_devops_missing': return t('dashboard.finding.az_devops_missing')
    case 'az_login': return t('dashboard.finding.az_login')
    case 'az_missing': return t('dashboard.finding.az_missing')
    case 'codex_not_isolated': return t('dashboard.finding.codex_not_isolated')
    case 'env_file_mode': return t('dashboard.finding.env_file_mode')
    case 'env_override': return t('dashboard.finding.env_override')
    case 'gh_login': return t('dashboard.finding.gh_login')
    case 'gh_missing': return t('dashboard.finding.gh_missing')
    case 'harness_login': return t('dashboard.finding.harness_login')
    case 'hosting_skipped': return t('dashboard.finding.hosting_skipped')
    case 'local_config_invalid': return t('dashboard.finding.local_config_invalid')
    case 'local_port_ignored': return t('dashboard.finding.local_port_ignored')
    case 'pi_model_unknown': return t('dashboard.finding.pi_model_unknown')
    case 'pi_not_isolated': return t('dashboard.finding.pi_not_isolated')
    case 'seed_update_available': return t('dashboard.finding.seed_update_available')
    default: return t('dashboard.findingUnknown', { code })
  }
}

export function dashboardError(error: unknown): string {
  if (!(error instanceof ApiError)) return error instanceof Error ? error.message : String(error)
  switch (error.code) {
    case 'run_in_progress': return t('dashboard.error.run_in_progress')
    case 'request_timeout': return t('dashboard.error.request_timeout')
    case 'no_harness': return t('dashboard.error.no_harness')
    case 'no_tested_harness': return t('dashboard.error.no_tested_harness')
    case 'unknown_repo': return t('dashboard.error.unknown_repo')
    case 'no_ready_tasks': return t('dashboard.error.no_ready_tasks')
    case 'trace_db_locked': return t('dashboard.error.trace_db_locked')
    case 'remote_run': return t('dashboard.error.remote_run')
    case 'task_busy': return t('dashboard.error.task_busy')
    case 'repo_settings_invalid': return t('dashboard.error.repo_settings_invalid')
    case 'repo_settings_io': return t('dashboard.error.repo_settings_io')
    default: return `${t('dashboard.requestFailed', { code: error.code })} ${error.message}`
  }
}

export function deferredError(error: unknown): string | (() => string) {
  return error instanceof ApiError ? () => dashboardError(error) : dashboardError(error)
}

export function skipReason(code: string): string {
  switch (code) {
    case 'needs_environment': return t('dashboard.skip.needs_environment')
    case 'human_task': return t('dashboard.skip.human_task')
    case 'no_workflow': return t('dashboard.skip.no_workflow')
    case 'waits_on_pr': return t('dashboard.skip.waits_on_pr')
    case 'blocked': return t('dashboard.skip.blocked')
    case 'in_review': return t('dashboard.skip.in_review')
    case 'merged_outside': return t('dashboard.skip.merged_outside')
    case 'running': return t('dashboard.skip.running')
    case 'cannot_start': return t('dashboard.skip.cannot_start')
    case 'writes_overlap': return t('dashboard.skip.writes_overlap')
    case 'exclusive': return t('dashboard.skip.exclusive')
    case 'excluded': return t('dashboard.skip.excluded')
    case 'no_slot': return t('dashboard.skip.no_slot')
    default: return code
  }
}

export function overviewWarningText(warning: OverviewWarning): string {
  switch (warning.code) {
    case 'trace_unreadable': return t('dashboard.warning.trace_unreadable', warning.params)
    case 'config_state_unavailable': return t('dashboard.warning.config_state_unavailable', warning.params)
    case 'config_changes_unavailable': return t('dashboard.warning.config_changes_unavailable', warning.params)
    case 'task_titles_unavailable': return t('dashboard.warning.task_titles_unavailable', warning.params)
    case 'folder_missing': return t('dashboard.warning.folder_missing', warning.params)
    case 'not_git': return t('dashboard.warning.not_git', warning.params)
    case 'local_settings_unavailable': return t('dashboard.warning.local_settings_unavailable', warning.params)
    case 'repo_timeout': return t('dashboard.warning.repo_timeout', warning.params)
    case 'repo_error': return t('dashboard.warning.repo_error', warning.params)
    default: return t('dashboard.warning.unknown')
  }
}
