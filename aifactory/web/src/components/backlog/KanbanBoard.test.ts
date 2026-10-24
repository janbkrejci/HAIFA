import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import KanbanBoard from './KanbanBoard.vue'
import { BOARD_STATES, kanbanColumns, presentStates, resetShowArchivedForTests } from '@/lib/backlog'
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

beforeEach(() => {
  localStorage.clear()
  resetShowArchivedForTests()
})

afterEach(() => {
  localStorage.clear()
  resetShowArchivedForTests()
})

describe('KanbanBoard', () => {
  it('hides archived cards and toggles each terminal column with visible counts', async () => {
    const tasks = [
      taskNode({ id: 'done', path: 'done.md', board_state: 'done' }),
      taskNode({ id: 'archived', path: 'archived.md', board_state: 'done', archived: true }),
      taskNode({ id: 'cancelled', path: 'cancelled.md', board_state: 'cancelled', archived: true }),
      taskNode({ id: 'ready', path: 'ready.md' }),
    ]
    const wrapper = mount(KanbanBoard, { props: { tasks, states: BOARD_STATES } })
    const column = (id: string) => wrapper.get(`[data-column="${id}"]`)
    const toggle = (id: string) => column(id).get('[data-test="show-archived"]')
    expect(wrapper.findAll('[data-test="show-archived"]')).toHaveLength(2)
    expect(cards(wrapper, 'ready')).toEqual(['ready'])
    expect(cards(wrapper, 'done')).toEqual(['done'])
    expect(cards(wrapper, 'cancelled')).toEqual([])
    expect(column('done').get('[data-test="count"]').text()).toBe('1')
    expect(column('cancelled').get('[data-test="count"]').text()).toBe('0')
    expect(toggle('done').attributes('aria-label')).toBe('Zobrazit archivované (1)')
    expect(toggle('cancelled').text()).toBe('1')
    expect(toggle('done').attributes('aria-pressed')).toBe('false')
    await toggle('done').trigger('click')
    expect(cards(wrapper, 'done')).toEqual(['done', 'archived'])
    expect(column('done').get('[data-test="count"]').text()).toBe('2')
    expect(wrapper.get('[data-item="archived"]').classes()).toContain('archived')
    expect(cards(wrapper, 'cancelled')).toEqual([])
    await toggle('cancelled').trigger('click')
    expect(toggle('cancelled').attributes('aria-pressed')).toBe('true')
    expect(cards(wrapper, 'cancelled')).toEqual(['cancelled'])
    expect(wrapper.get('[data-item="cancelled"]').classes()).toContain('archived')
    const restoreCancelled = wrapper.get('[data-item="cancelled"] [data-test="archive-toggle"]')
    expect(restoreCancelled.attributes('aria-label')).toBe('Obnovit')
    await restoreCancelled.trigger('click')
    const archive = wrapper.get('[data-item="done"] [data-test="archive-toggle"]')
    const restore = wrapper.get('[data-item="archived"] [data-test="archive-toggle"]')
    expect(archive.attributes('aria-label')).toBe('Archivovat')
    expect(restore.attributes('aria-label')).toBe('Obnovit')
    await archive.trigger('click')
    await restore.trigger('click')
    expect(wrapper.emitted('archive')).toEqual([['cancelled', false], ['done', true], ['archived', false]])
    await wrapper.setProps({ busy: true })
    expect(archive.attributes('disabled')).toBeDefined()
    expect(restore.attributes('disabled')).toBeDefined()
    await archive.trigger('click')
    await restore.trigger('click')
    expect(wrapper.emitted('archive')).toHaveLength(3)
    await toggle('done').trigger('click')
    expect(cards(wrapper, 'done')).toEqual(['done'])
    expect(cards(wrapper, 'cancelled')).toEqual(['cancelled'])
    wrapper.unmount()
  })

  it('shows the approved column only while a task is waiting for CI', () => {
    const task = taskNode({ board_state: 'approved' })
    const wrapper = mount(KanbanBoard, { props: { tasks: [task], states: presentStates(BOARD_STATES, { approved: 1 }) } })
    expect(cards(wrapper, 'approved')).toEqual([task.id])
    expect(wrapper.get('[data-column="approved"] h2').text()).toContain('Schváleno, čeká na CI')
    expect(presentStates(BOARD_STATES, {})).not.toContain('approved')
    wrapper.unmount()
  })

  it('renders long unbroken titles, IDs and workflows in full alongside labels and controls', () => {
    const task = taskNode({
      id: `HAIFA-REFINEMENT-${'T50'.repeat(40)}`,
      title: 'a'.repeat(120),
      workflow: 'workflow'.repeat(30),
      invalid: true,
      priority_rank: 0,
      priority_of: ['HAIFA-REFINEMENT-T49'],
    })
    const wrapper = mount(KanbanBoard, { props: { tasks: [task], states: BOARD_STATES } })
    const card = wrapper.get('[data-card]')
    expect(card.get('.title').text()).toBe(task.title)
    expect(card.get('.id').text()).toBe(`1. ${task.id}`)
    expect(card.get('.meta').text()).toBe(task.workflow)
    expect(card.get('[data-test="invalid"]').text()).toBe('neplatný status')
    expect(card.get('[data-test="priority"]').text()).toBe('přednostně')
    expect(wrapper.get('.tools').findAll('button')).toHaveLength(4)
  })

  it('puts every task into the column of its board state', () => {
    const tasks = [...backlogData().tasks, taskNode({ id: 'X-1', path: 'x.md', board_state: 'todo', invalid: true })]
    const wrapper = mount(KanbanBoard, { props: { tasks, states: BOARD_STATES } })
    const columns = wrapper.findAll('[data-column]')
    expect(columns.map((c) => c.attributes('data-column'))).toEqual(kanbanColumns(BOARD_STATES))
    expect(columns.map((c) => c.attributes('data-column'))).toEqual([
      'todo', 'ready', 'deferred', 'human', 'blocked', 'running', 'in review', 'approved', 'awaiting merge', 'done', 'cancelled',
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
    expect(wrapper.get('[data-item="X-1"]').attributes('draggable')).toBe('false')
    await drag('X-1', '[data-column="ready"]')
    expect(wrapper.emitted('reorder')).toBeUndefined()
    expect(wrapper.emitted('exclude')).toBeUndefined()
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

  it('puts tasks with priority on top with the label přednostně and clears it', async () => {
    const tasks = [
      ...readyTasks(),
      taskNode({ id: 'P-1', path: 'p1.md', priority_rank: 0, priority_of: ['P-2'] }),
      taskNode({ id: 'P-2', path: 'p2.md', board_state: 'blocked', priority_blockers: ['P-1'] }),
    ]
    const wrapper = mount(KanbanBoard, { props: { tasks, states: BOARD_STATES } })
    expect(cards(wrapper, 'ready')).toEqual(['P-1', 'R-1', 'R-2', 'R-3'])
    expect(cards(wrapper, 'blocked')).toEqual(['P-2'])
    expect(wrapper.get('[data-item="P-1"] [data-test="priority"]').text()).toBe('přednostně')
    expect(wrapper.find('[data-item="P-2"] [data-test="priority"]').exists()).toBe(true)
    expect(wrapper.find('[data-item="R-1"] [data-test="priority"]').exists()).toBe(false)
    expect(wrapper.find('[data-item="R-1"] [data-test="priority-clear"]').exists()).toBe(false)
    // the queue order the ↑/↓ buttons send starts with the task with priority
    await wrapper.get('[data-item="R-1"] [data-test="move-up"]').trigger('click')
    expect(wrapper.emitted('reorder')).toEqual([[['R-1', 'P-1', 'R-2', 'R-3']]])
    const clear = wrapper.get('[data-item="P-2"] [data-test="priority-clear"]')
    expect(clear.attributes('aria-label')).toBe('Zrušit přednost')
    await clear.trigger('click')
    await wrapper.get('[data-item="P-1"] [data-test="priority-clear"]').trigger('click')
    expect(wrapper.emitted('clearPriority')).toEqual([['P-2'], ['P-1']])
  })
})
