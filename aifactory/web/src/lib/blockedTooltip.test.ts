import { describe, expect, it } from 'vitest'
import { blockedTooltip, unmetLine } from './backlog'

describe('Blokováno tooltip', () => {
  it.each([
    [{ id: 'M01-S01-T02', reason: 'not_done', missing: ['M01-S01-T02'] }, 'M01-S01-T02 – task není hotový'],
    [{ id: 'M01-S01-T02', reason: 'cancelled', missing: ['M01-S01-T02'] }, 'M01-S01-T02 – task je zrušený'],
    [{ id: 'X99', reason: 'unknown', missing: ['X99'] }, 'X99 – položka neexistuje'],
    [{ id: 'M01-S02', reason: 'empty', missing: [] }, 'M01-S02 – step je prázdný'],
    [{ id: 'M02', reason: 'empty', missing: [] }, 'M02 – projekt je prázdný'],
    [
      { id: 'M01-S01', reason: 'incomplete', missing: ['M01-S01-T02', 'M01-S01-T03'] },
      'M01-S01 – step má nehotové tasky: M01-S01-T02, M01-S01-T03',
    ],
    [{ id: 'M01', reason: 'incomplete', missing: ['M01-S01-T02'] }, 'M01 – projekt má nehotové tasky: M01-S01-T02'],
  ])('describes %o', (unmet, line) => {
    expect(unmetLine(unmet)).toBe(line)
  })

  it('lists every blocker under a heading, empty when nothing blocks', () => {
    expect(blockedTooltip([])).toBe('')
    expect(blockedTooltip(undefined)).toBe('')
    expect(
      blockedTooltip([
        { id: 'M01-S01-T02', reason: 'not_done', missing: ['M01-S01-T02'] },
        { id: 'X99', reason: 'unknown', missing: ['X99'] },
      ]),
    ).toBe('Blokuje:\nM01-S01-T02 – task není hotový\nX99 – položka neexistuje')
  })

  it('adds titles and the level from the names', () => {
    const names = {
      'M01-S01-T02': { title: 'Loader', level: 'task' },
      M01: { title: 'Core', level: 'module' },
      'M01-S02': { title: 'Web', level: 'step' },
    }
    expect(unmetLine({ id: 'M01-S01-T02', reason: 'not_done', missing: ['M01-S01-T02'] }, names)).toBe(
      'M01-S01-T02 (Loader) – task není hotový',
    )
    expect(unmetLine({ id: 'M01', reason: 'empty', missing: [] }, names)).toBe('M01 (Core) – modul je prázdný')
    expect(
      unmetLine({ id: 'M01-S02', reason: 'incomplete', missing: ['M01-S01-T02', 'X1'] }, names),
    ).toBe('M01-S02 (Web) – step má nehotové tasky: M01-S01-T02 (Loader), X1')
  })
})
