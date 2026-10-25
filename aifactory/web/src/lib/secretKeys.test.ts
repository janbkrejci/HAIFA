import { describe, expect, it } from 'vitest'
import { createSecretKeys } from './secretKeys'
const keys = ['Control', 'Shift', 'Control', 'Shift']
describe('secret keys', () => {
  it('detects the sequence repeatedly', () => {
    const detect = createSecretKeys()
    for (let cycle = 0; cycle < 2; cycle++) expect(keys.map(key => detect({ key, repeat: false }, 0))).toEqual([false, false, false, true])
  })
  it('resets on another key or a gap over one second', () => {
    for (const interruption of ['x', 'Alt', 'Enter']) {
      const detect = createSecretKeys()
      detect({ key: 'Control', repeat: false }, 0)
      detect({ key: interruption, repeat: false }, 10)
      expect(keys.slice(1).map(key => detect({ key, repeat: false }, 20))).not.toContain(true)
    }
    const detect = createSecretKeys()
    detect({ key: 'Control', repeat: false }, 0)
    expect(keys.slice(1).map(key => detect({ key, repeat: false }, 1001))).not.toContain(true)
  })
  it('ignores repeats and accepts exactly one second', () => {
    const detect = createSecretKeys()
    detect({ key: 'Control', repeat: false }, 0)
    expect(detect({ key: 'Shift', repeat: true }, 100)).toBe(false)
    detect({ key: 'Shift', repeat: false }, 1000)
    detect({ key: 'Control', repeat: false }, 2000)
    expect(detect({ key: 'Shift', repeat: false }, 3000)).toBe(true)
    detect({ key: 'Control', repeat: false }, 4000)
    detect({ key: 'Control', repeat: true }, 4900)
    expect(keys.slice(1).map(key => detect({ key, repeat: false }, 5100))).not.toContain(true)
  })
})
