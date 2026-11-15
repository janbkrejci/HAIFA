import { ApiError, type ApiIssue } from './api'
import { t } from './i18n'
import { factoryEn } from './i18n/factory'
import { findingTitle } from './dashboardMessages'
import { planCodeText } from './factory'

/** Interpret protocol codes only; original diagnostics remain available alongside these labels. */
export function findingText(code: string): string {
  const key = `factoryUi.finding.${code}` as keyof typeof factoryEn
  return key in factoryEn ? t(key) : findingTitle(code)
}

export function findingFix(code: string): string {
  const key = `factoryUi.findingFix.${code}` as keyof typeof factoryEn
  return key in factoryEn ? t(key) : t('factoryUi.fixUnknown')
}

export function factoryErrorText(error: unknown): string {
  if (!(error instanceof ApiError)) return error instanceof Error ? error.message : String(error ?? '')
  if (error.code === 'plan_changed') return t('factoryUi.planChanged')
  const key = `factoryUi.${error.code}` as keyof typeof factoryEn
  if (key in factoryEn) return t(key)
  const label = planCodeText(error.code)
  return label === error.code ? t('factoryUi.errorUnknown', { code: error.code }) : label
}

export function settingsIssueText(issue: ApiIssue): string {
  const key = `factoryUi.validation.${issue.message_code}` as keyof typeof factoryEn
  return key in factoryEn ? t(key, issue.params ?? {}) : t('factoryUi.invalidSetting', { field: issue.id ?? issue.path ?? '' })
}

export function factoryDiagnostic(error: unknown): string {
  return error instanceof Error ? error.message : String(error ?? '')
}
