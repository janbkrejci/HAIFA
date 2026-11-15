import { ApiError } from './api'
import { factoryErrorText, findingFix } from './factoryMessages'
import { t } from './i18n'
import { setupEn } from './i18n/setup'
import { CheckTimeout } from './machineProgress'

/** Protocol codes are independent of the language of the original diagnostic. */
export function setupErrorText(error: unknown): string {
  if (error instanceof CheckTimeout) return t('setup.checkTimeout', { seconds: error.seconds, step: error.step.detail ?? error.step.id })
  if (error instanceof ApiError && error.issues.some(issue => issue.id === 'port')) return t('setup.invalidPort')
  return factoryErrorText(error)
}

export function machineFixText(code: string): string {
  const key = `setup.fix.${code}` as keyof typeof setupEn
  return key in setupEn ? t(key) : findingFix(code)
}
