import { afterEach, describe, expect, it, vi } from 'vitest'
import { mergeNames, nameTip, refreshNames, resetNamesForTests, setLevels, setNames, useLevels, useNames } from './names'

function envelope(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}

afterEach(() => {
  vi.unstubAllGlobals()
  resetNamesForTests()
})

describe('shared names', () => {
  it('loads /api/backlog/names and gives the tooltip of a code', async () => {
    const fetchMock = vi.fn(async () =>
      envelope({
        levels: ['module', 'step', 'task'],
        names: { M01: { title: 'Core', level: 'module' }, 'M01-S01-T01': { title: 'Schema', level: 'task' } },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await refreshNames()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/backlog/names')
    expect(nameTip('M01')).toBe('Modul: Core')
    expect(nameTip('M01-S01-T01')).toBe('Task: Schema')
    expect(useLevels().top.value).toBe('module')
    expect(useLevels().step.value).toBe('step')
  })

  it('a reload shows a renamed task', async () => {
    let title = 'Schema'
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => envelope({ levels: ['project', 'step', 'task'], names: { T1: { title, level: 'task' } } })),
    )
    await refreshNames()
    const tip = useNames().tip
    expect(tip('T1')).toBe('Task: Schema')
    title = 'Schema v2'
    await refreshNames()
    expect(tip('T1')).toBe('Task: Schema v2')
  })

  it('keeps the last names when a load fails', async () => {
    setNames({ names: { T1: { title: 'Schema', level: 'task' } } })
    vi.stubGlobal('fetch', vi.fn(async () => new Response('nope', { status: 500 })))
    await refreshNames()
    expect(nameTip('T1')).toBe('Task: Schema')
  })

  it('drops malformed entries, merges names and sets levels', () => {
    setNames({ names: { A: { title: 'A', level: 'task' }, B: { title: 1 }, C: null } })
    expect(Object.keys(useNames().names.value)).toEqual(['A'])
    mergeNames({ B: { title: 'Bee', level: 'step' } })
    expect(nameTip('A')).toBe('Task: A')
    expect(nameTip('B')).toBe('Step: Bee')
    setLevels(['area', 'task'])
    expect(useLevels().top.value).toBe('area')
    expect(useLevels().step.value).toBe('area')
    expect(useLevels().containers.value).toEqual(['area'])
  })
})
