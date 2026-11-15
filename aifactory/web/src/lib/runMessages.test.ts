import { afterEach, expect, it } from 'vitest'
import { ApiError, DB_BUSY_CODE } from './api'
import { setLocale } from './i18n'
import { runError } from './runMessages'

afterEach(() => setLocale('en'))

it.each([
  [DB_BUSY_CODE, 'The run database is busy.', 'Databáze běhů je právě obsazená.'],
  ['already_running', 'The task is already running.', 'Task už běží.'],
  ['request_timeout', 'Loading took too long.', 'Načítání trvá příliš dlouho.'],
  ['unknown_run', 'The run was not found.', 'Běh nebyl nalezen.'],
  ['future_code', 'Request failed (future_code).', 'Požadavek selhal (future_code).'],
])('renders %s from its code and leaves server diagnostics intact', (code, english, czech) => {
  const error = new ApiError(code, 'Původní serverová zpráva bez překladu')
  setLocale('en')
  expect(runError(error)).toContain(english)
  setLocale('cs')
  expect(runError(error)).toContain(czech)
  expect(error.message).toBe('Původní serverová zpráva bez překladu')
})
