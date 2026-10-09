import { describe, expect, it } from 'vitest'
import {
  codeTooltip,
  codeWithTitle,
  levelLabel,
  levelNoun,
  levelsOf,
  levelsText,
  namesFromBacklog,
  type CodeNames,
} from './backlog'
import type { ContainerNode } from './backlog'
import { taskNode } from '@/test/backlogFixtures'

describe('level names', () => {
  it.each([
    ['project', 'Projekt'],
    ['module', 'Modul'],
    ['step', 'Step'],
    ['task', 'Task'],
    ['area', 'area'],
    ['Epic', 'Epic'],
  ])('labels %s as %s', (level, label) => {
    expect(levelLabel(level)).toBe(label)
  })

  it('declines the known levels and keeps other names', () => {
    expect(levelNoun('project')).toBe('projekt')
    expect(levelNoun('module', 'gen')).toBe('modulu')
    expect(levelNoun('step', 'gen')).toBe('stepu')
    expect(levelNoun('task', 'gen')).toBe('tasku')
    expect(levelNoun('area', 'gen')).toBe('area')
    expect(levelsText(['project', 'step'], 'gen')).toBe('projektu nebo stepu')
    expect(levelsText(['module', 'step'])).toBe('modul nebo step')
  })

  it('falls back to the default levels', () => {
    expect(levelsOf(undefined)).toEqual(['project', 'step', 'task'])
    expect(levelsOf([])).toEqual(['project', 'step', 'task'])
    expect(levelsOf(['area', 'task'])).toEqual(['area', 'task'])
  })
})

describe('code tooltip', () => {
  const names: CodeNames = {
    HAIFA: { title: 'Helios AI Factory', level: 'project' },
    M01: { title: 'Core', level: 'module' },
    'HAIFA-S01': { title: 'Dashboard UX', level: 'step' },
    'HAIFA-S01-T06': { title: 'Názvy úrovní', level: 'task' },
    A1: { title: null, level: 'area' },
  }

  it('names the title and the level', () => {
    expect(codeTooltip('HAIFA', names)).toBe('Projekt: Helios AI Factory')
    expect(codeTooltip('M01', names)).toBe('Modul: Core')
    expect(codeTooltip('HAIFA-S01', names)).toBe('Step: Dashboard UX')
    expect(codeTooltip('HAIFA-S01-T06', names)).toBe('Task: Názvy úrovní')
    expect(codeTooltip('A1', names)).toBe('area')
  })

  it('is empty for an unknown code', () => {
    expect(codeTooltip('X99', names)).toBe('')
    expect(codeTooltip(null, names)).toBe('')
    expect(codeTooltip('toString', names)).toBe('')
  })

  it('adds the title to a code in text', () => {
    expect(codeWithTitle('M01', names)).toBe('M01 (Core)')
    expect(codeWithTitle('X99', names)).toBe('X99')
  })

  it('collects the names of a backlog tree', () => {
    const tree = [
      {
        kind: 'container',
        id: 'M01',
        title: 'Core',
        level: 'module',
        path: 'backlog/M01-core',
        progress: { done: 0, total: 1 },
        done: false,
        blocks: [],
        children: [taskNode({ id: 'M01-T01', title: 'Schema' })],
      } satisfies ContainerNode,
    ]
    expect(namesFromBacklog(tree, [taskNode({ id: 'M02-T01', title: 'Web' })])).toEqual({
      M01: { title: 'Core', level: 'module' },
      'M01-T01': { title: 'Schema', level: 'task' },
      'M02-T01': { title: 'Web', level: 'task' },
    })
  })
})
