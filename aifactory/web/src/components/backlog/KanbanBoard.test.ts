import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import KanbanBoard from './KanbanBoard.vue'
import { BOARD_STATES, kanbanColumns } from '@/lib/backlog'
import { backlogData, taskNode } from '@/test/backlogFixtures'

function readyTasks() {
  return [
    taskNode({ id: 'R-1', path: 'r1.md', queue_rank: 0 }),
    taskNode({ id: 'R-2', path: 'r2.md', queue_rank: 1 }),
    taskNode({ id: 'R-3', path: 'r3.md' }),
    taskNode({ id: 'D-1', path: 'd1.md', auto_excluded: true }),
    taskNode({ id: 'B-1', path: 'b1.md', board_state: 'blocked', auto_excluded: true }),
    taskNode({ id: 'X-1', path: 'x1.md', board_state: 'running', auto_excluded: true }),
    taskNode({ id: 'T-1', path: 't1.md', board_state: 'todo' }),
  ]
}

function dataTransfer() {
  const store = new Map<string, string>()
  return {
    setData: (k: string, v: string) => store.set(k, v),
    getData: (k: string) => store.get(k) ?? '',
    effectAllowed: 'all',
    dropEffect: 'move',
  }
}

const cards = (wrapper: ReturnType<typeof mount>, column: string) =>
  wrapper.find(`[data-column="${column}"]`).findAll('[data-card]').map((c) => c.attributes('data-card'))

describe('KanbanBoard', () => {
  it('puts every task into the column of its board state', () => {
    const tasks = [...backlogData().tasks, taskNode({ id: 'X-1', path: 'x.md', board_state: 'todo', invalid: true })]
    const wrapper = mount(KanbanBoard, { props: { tasks, states: BOARD_STATES } })
    const columns = wrapper.findAll('[data-column]')
    expect(columns.map((c) => c.attributes('data-column'))).toEqual(kanbanColumns(BOARD_STATES))
    expect(columns.map((c) => c.attributes('data-column'))).toEqual([
      'todo', 'ready', 'deferred', 'blocked', 'running', 'in review', 'done', 'cancelled',
    ])
    expect(columns[0].find('h2').text()).toContain('Bez workflow')
    expect(cards(wrapper, 'todo')).toEqual(['M02-S01-T01', 'X-1'])
    expect(cards(wrapper, 'ready')).toEqual(['M01-S01-T02'])
    expect(cards(wrapper, 'blocked')).toEqual(['M01-S01-T03'])
    expect(cards(wrapper, 'done')).toEqual(['M01-S01-T01'])
    expect(wrapper.find('[data-column="todo"] [data-test="count"]').text()).toBe('2')
    expect(wrapper.find('[data-column="running"] [data-test="count"]').text()).toBe('0')
    expect(wrapper.find('[data-column="running"]').text()).toContain('—')
    expect(wrapper.find('a.card[data-card="M01-S01-T02"]').attributes('href')).toBe('#/r/haifa/backlog/M01-S01-T02')
    expect(wrapper.find('[data-card="X-1"] [data-test="invalid"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="queue-help"]').text()).toBe(
      'Auto continue bere tasky ze sloupce Připraveno shora dolů. Odložené tasky nespustí, ručně je spustit jde.',
    )
  })

  it('explains the Bez workflow column in a tooltip and shows only the given columns', async () => {
    const wrapper = mount(KanbanBoard, {
      props: { tasks: backlogData().tasks, states: ['todo', 'ready'] },
      attachTo: document.body,
    })
    expect(wrapper.findAll('[data-column]').map((c) => c.attributes('data-column'))).toEqual(['todo', 'ready', 'deferred'])
    expect(wrapper.find('[data-column="ready"] [data-test="column-tip"]').exists()).toBe(false)
    await wrapper.find('[data-column="todo"] [data-test="tip-anchor"]').trigger('mouseenter')
    await flushPromises()
    expect(document.body.querySelector('[data-test="tooltip"]')?.textContent?.trim()).toBe(
      'Task nejde spustit, dokud nemá workflow (vlastní nebo zděděné z projektu či stepu).',
    )
    wrapper.unmount()
    document.body.innerHTML = ''
  })

  it('shows excluded tasks that have not started in Odloženo, numbers the queue', () => {
    const wrapper = mount(KanbanBoard, { props: { tasks: readyTasks(), states: BOARD_STATES } })
    expect(cards(wrapper, 'ready')).toEqual(['R-1', 'R-2', 'R-3'])
    expect(cards(wrapper, 'deferred')).toEqual(['D-1', 'B-1'])
    expect(cards(wrapper, 'running')).toEqual(['X-1'])
    expect(wrapper.find('[data-column="deferred"] h2').text()).toContain('Odloženo')
    expect(wrapper.findAll('[data-column="ready"] [data-test="queue-rank"]').map((r) => r.text())).toEqual([
      '1.', '2.', '3.',
    ])
    expect(wrapper.find('[data-column="deferred"] [data-test="queue-rank"]').exists()).toBe(false)
    // the switch on waiting tasks only, ↑/↓ in Připraveno only
    expect(wrapper.find('[data-item="X-1"] [data-test="exclude-toggle"]').exists()).toBe(false)
    expect(wrapper.find('[data-item="T-1"] [data-test="exclude-toggle"]').exists()).toBe(true)
    expect(wrapper.find('[data-item="D-1"] [data-test="move-up"]').exists()).toBe(false)
    expect(wrapper.get('[data-item="R-1"] [data-test="move-up"]').attributes('aria-label')).toBe('Posunout výš')
    expect(wrapper.get('[data-item="R-1"] [data-test="move-down"]').attributes('aria-label')).toBe('Posunout níž')
    expect(wrapper.get('[data-item="R-1"] [data-test="move-up"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-item="R-3"] [data-test="move-down"]').attributes('disabled')).toBeDefined()
  })

  it('shows Odloženo even when nothing is excluded', () => {
    const wrapper = mount(KanbanBoard, { props: { tasks: [], states: ['ready', 'done'] } })
    expect(wrapper.findAll('[data-column]').map((c) => c.attributes('data-column'))).toEqual(['ready', 'deferred', 'done'])
  })

  it('emits the whole new order of Připraveno from ↑ and ↓', async () => {
    const wrapper = mount(KanbanBoard, { props: { tasks: readyTasks(), states: BOARD_STATES } })
    await wrapper.get('[data-item="R-3"] [data-test="move-up"]').trigger('click')
    await wrapper.get('[data-item="R-1"] [data-test="move-down"]').trigger('click')
    expect(wrapper.emitted('reorder')).toEqual([[['R-1', 'R-3', 'R-2']], [['R-2', 'R-1', 'R-3']]])
  })

  it('excludes and returns a task with its switch', async () => {
    const wrapper = mount(KanbanBoard, { props: { tasks: readyTasks(), states: BOARD_STATES } })
    const exclude = wrapper.get('[data-item="R-2"] [data-test="exclude-toggle"]')
    expect(exclude.attributes('aria-label')).toBe('Vyloučit z auto continue')
    await exclude.trigger('click')
    const back = wrapper.get('[data-item="D-1"] [data-test="exclude-toggle"]')
    expect(back.attributes('aria-label')).toBe('Vrátit do auto continue')
    await back.trigger('click')
    await wrapper.get('[data-item="B-1"] [data-test="exclude-toggle"]').trigger('click')
    expect(wrapper.emitted('exclude')).toEqual([['R-2', true], ['D-1', false], ['B-1', false]])
  })

  it('reorders and excludes by drag and drop', async () => {
    const wrapper = mount(KanbanBoard, { props: { tasks: readyTasks(), states: BOARD_STATES } })
    const drag = async (id: string, target: string) => {
      const dt = dataTransfer()
      await wrapper.get(`[data-item="${id}"]`).trigger('dragstart', { dataTransfer: dt })
      await wrapper.get(target).trigger('dragover', { dataTransfer: dt })
      await wrapper.get(target).trigger('drop', { dataTransfer: dt })
    }
    expect(wrapper.get('[data-item="R-1"]').attributes('draggable')).toBe('true')
    expect(wrapper.get('[data-item="T-1"]').attributes('draggable')).toBe('false')
    // onto a card of Připraveno: before it
    await drag('R-3', '[data-item="R-1"]')
    // onto the column: at the end
    await drag('R-1', '[data-column="ready"]')
    await drag('R-2', '[data-column="deferred"]')
    await drag('D-1', '[data-column="ready"]')
    expect(wrapper.emitted('reorder')).toEqual([[['R-3', 'R-1', 'R-2']], [['R-2', 'R-3', 'R-1']]])
    expect(wrapper.emitted('exclude')).toEqual([['R-2', true], ['D-1', false]])
  })

  it('waits with the controls while a queue write runs', () => {
    const wrapper = mount(KanbanBoard, { props: { tasks: readyTasks(), states: BOARD_STATES, busy: true } })
    expect(wrapper.get('[data-item="R-2"] [data-test="move-up"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-item="R-2"] [data-test="exclude-toggle"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-item="R-2"]').attributes('draggable')).toBe('false')
  })
})
