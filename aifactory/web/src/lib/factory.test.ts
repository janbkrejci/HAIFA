import { describe, expect, it } from 'vitest'
import { installPlan } from '@/test/factoryFixtures'
import { fileActionText, installOptions, planCodeText } from './factory'

describe('factory installation state', () => {
  it('takes base, provider and docs root from the plan, with empty Azure fields', () => {
    expect(installOptions(installPlan())).toEqual({ base: 'main', provider: 'local', docs_root: 'factory',
      azure: { organization: '', project: '', repository: '' } })
  })
  it('has no test command option', () => {
    expect(installOptions(installPlan())).not.toHaveProperty('test_command')
  })
  it('names plan codes and file actions in Czech, unknown ones as they are', () => {
    expect(planCodeText('plan_changed')).toBe('plán se mezitím změnil')
    expect(planCodeText('something_new')).toBe('something_new')
    expect(fileActionText('create')).toBe('nový')
  })
})
