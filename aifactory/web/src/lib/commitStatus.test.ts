import { describe, expect, it } from 'vitest'
import { toCommitStatus } from './commitStatus'

describe('toCommitStatus', () => {
  it('reads a full status', () => {
    expect(
      toCommitStatus({
        base: 'main',
        commit: 'abcdef1234',
        clean: false,
        changes: [{ path: '.factory/config.yaml', status: 'modified' }],
      }),
    ).toEqual({
      base: 'main',
      commit: 'abcdef1234',
      clean: false,
      changes: [{ path: '.factory/config.yaml', status: 'modified' }],
    })
  })

  it('tolerates incomplete data', () => {
    expect(toCommitStatus({ items: [] })).toEqual({ base: '', commit: '', clean: true, changes: [] })
    const partial = toCommitStatus({ changes: [{ path: 'a' }, 3, { status: 'x' }] })
    expect(partial?.clean).toBe(false)
    expect(partial?.changes).toEqual([{ path: 'a', status: '' }])
  })

  it('gives null for anything but an object', () => {
    expect(toCommitStatus(null)).toBeNull()
    expect(toCommitStatus([1])).toBeNull()
    expect(toCommitStatus('clean')).toBeNull()
  })
})
