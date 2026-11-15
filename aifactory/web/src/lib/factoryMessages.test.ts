import { afterEach, expect, it } from 'vitest'
import { ApiError } from './api'
import { factoryErrorText, findingFix, findingText, settingsIssueText } from './factoryMessages'
import { setLocale, t } from './i18n'
import { factoryEn, factoryCs } from './i18n/factory'

afterEach(() => setLocale('en'))

it('uses stable codes for both locales and keeps unknown codes visible', () => {
  const error = new ApiError('invalid_config', 'arbitrary Czech or English server text')
  for (const language of ['en', 'cs'] as const) {
    setLocale(language)
    expect(factoryErrorText(error)).toBe(language === 'en' ? 'Invalid configuration' : 'Neplatná konfigurace')
    expect(findingText('config_uncommitted')).toBe(language === 'en' ? 'Uncommitted configuration' : 'Necommitnutá konfigurace')
    expect(findingFix('trace_db_shared')).toContain('trace_db')
    expect(findingFix('factory_missing')).toBe(language === 'en'
      ? 'Install factory and commit .factory/ into base.'
      : 'Nainstaluj factory a commitni .factory/ do base.')
    expect(findingText('new_code')).toContain('new_code')
    expect(factoryErrorText(new ApiError('new_error', 'diagnostic'))).toContain('new_error')
    expect(settingsIssueText({ code: 'invalid_value', message: 'raw', id: 'base', path: null })).toContain('base')
  }
})

it('uses EN and CS plural forms for run and lesson counts', () => {
  for (const [language, expected] of [['en', ['0 runs', '1 run', '2 runs', '5 runs']], ['cs', ['0 běhů', '1 běh', '2 běhy', '5 běhů']]] as const) {
    setLocale(language)
    expect([0, 1, 2, 5].map(count => t('factoryUi.runCount', { count }, count))).toEqual(expected)
  }
})


it('keeps catalog leaf keys separate from nested namespaces for vue-i18n flattening', () => {
  for (const catalog of [factoryEn, factoryCs]) {
    const keys = Object.keys(catalog)
    for (const key of keys) {
      expect(keys.filter(other => other.startsWith(`${key}.`)), key).toEqual([])
    }
  }
})
