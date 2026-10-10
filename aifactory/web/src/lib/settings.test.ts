import { describe, expect, it } from 'vitest'
import { SETTINGS } from '@/test/settingsFixtures'
import { fieldErrors, formValues, settingsDiff } from './settings'

describe('settingsDiff', () => {
  it('is empty without changes', () => {
    const values = formValues(SETTINGS)
    expect(settingsDiff(values, { ...values })).toEqual({})
  })

  it('sends only the changed fields per section', () => {
    const values = formValues(SETTINGS)
    const input = settingsDiff(values, { ...values, base: 'develop', trace_db: 'x.db' })
    expect(input).toEqual({ shared: { base: 'develop' }, local: { trace_db: 'x.db' } })
  })

  it('never sends a port: the dashboard port is in the registry', () => {
    const values = formValues(SETTINGS)
    expect(values).not.toHaveProperty('port')
    const changed = { ...values, port: '4801', trace_db: 'x.db' } as typeof values
    const input = settingsDiff(values, changed)
    expect(input.local).toEqual({ trace_db: 'x.db' })
    expect(input.local).not.toHaveProperty('port')
  })

  it('sends max_parallel_runs as a number, other text as it is', () => {
    const values = formValues(SETTINGS)
    expect(values.max_parallel_runs).toBe('1')
    expect(settingsDiff(values, { ...values, max_parallel_runs: ' 3 ' })).toEqual({
      shared: { max_parallel_runs: 3 },
    })
    expect(settingsDiff(values, { ...values, max_parallel_runs: 'dva' })).toEqual({
      shared: { max_parallel_runs: 'dva' },
    })
  })

  it('splits protected files into trimmed lines', () => {
    const values = formValues(SETTINGS)
    const input = settingsDiff(values, { ...values, protected_files: ' .factory/\n\njustfile \n' })
    expect(input).toEqual({ shared: { protected_files: ['.factory/', 'justfile'] } })
    expect(settingsDiff(values, { ...values, protected_files: '.factory/\n' })).toEqual({})
  })
})

describe('fieldErrors', () => {
  it('groups messages by field id', () => {
    const errors = fieldErrors([
      { code: 'invalid_value', message: 'must not be empty', path: 'x', id: 'base' },
      { code: 'invalid_value', message: 'bad', path: 'x', id: 'base' },
      { code: 'invalid_value', message: 'broken file', path: 'x', id: null },
    ])
    expect(errors).toEqual({ base: ['must not be empty', 'bad'], '': ['broken file'] })
  })
})
