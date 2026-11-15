import { afterEach, expect, it } from 'vitest'
import { ApiError } from './api'
import { setLocale } from './i18n'
import { CheckTimeout } from './machineProgress'
import { machineFixText, setupErrorText } from './setupMessages'

afterEach(() => setLocale('en'))

it.each(['en', 'cs'] as const)('renders protocol errors and repairs in %s without parsing diagnostics', language => {
  setLocale(language)
  const error = new ApiError('library_dirty', 'Náhodná česká věta bez známé struktury.')
  expect(setupErrorText(error)).toBe(language === 'en' ? 'library has uncommitted changes' : 'knihovna má necommitnuté změny')
  expect(machineFixText('harness_test_failed')).toContain(language === 'en' ? 'Fix sign-in' : 'oprav přihlášení')
  expect(setupErrorText(new ApiError('unrecognized', 'Do not parse this.'))).toContain('unrecognized')
  expect(setupErrorText(new CheckTimeout({ id: 'machine', detail: 'codex login status' }, 75)))
    .toContain(language === 'en' ? 'within 75 s' : 'do 75 s')
  expect(error.message).toBe('Náhodná česká věta bez známé struktury.')
})
