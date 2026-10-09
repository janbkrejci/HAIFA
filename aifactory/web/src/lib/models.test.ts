import { describe, expect, it } from 'vitest'
import { modelIcon, modelName } from './models'

describe('models', () => {
  it('maps a model to its provider icon', () => {
    expect(modelIcon('claude-opus')).toBe('/models/claude.png')
    expect(modelIcon('gpt-5')).toBe('/models/openai.png')
    expect(modelIcon('openrouter/z-ai/glm-4.6')).toBe('/models/zai.png')
    expect(modelIcon('mystery-model')).toBeNull()
    expect(modelIcon(null)).toBeNull()
  })

  it('shortens provider-qualified ids', () => {
    expect(modelName('openrouter/z-ai/glm-4.6')).toBe('glm-4.6')
    expect(modelName('claude-opus')).toBe('claude-opus')
    expect(modelName(null)).toBe('')
  })
})
