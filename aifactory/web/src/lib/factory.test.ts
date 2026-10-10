import { describe, expect, it } from 'vitest'
import { installPlan } from '@/test/factoryFixtures'
import { fileActionText, installOptions, planCodeText } from './factory'

describe('factory installation state', () => {
  it('copies all four default bindings and keeps the server defaults independent', () => {
    const plan = installPlan()
    const options = installOptions(plan)
    expect(options).toMatchObject({ base: 'main', provider: 'local', backlog_dir: 'backlog', specs_dir: 'specs', docs_dir: 'docs', agents: ['planner', 'builder', 'reviewer', 'documenter'], workflows: ['simple-sdlc'] })
    for (const name of options.agents!) expect(options.bind![name]).toEqual({ harness: 'claude', model: 'sonnet', thinking: 'medium' })
    options.bind!.builder!.thinking = null
    options.agents!.pop()
    expect(plan.bindings!.builder!.thinking).toBe('medium')
    expect(plan.agents).toHaveLength(4)
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
