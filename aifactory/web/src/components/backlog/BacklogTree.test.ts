import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import BacklogTree from './BacklogTree.vue'
import { backlogData, containerDetail, expandTree } from '@/test/backlogFixtures'
import { mergeNames, resetNamesForTests } from '@/lib/names'
import { TREE_EXPANDED_KEY, pruneDone, resetTreeForTests, revealSettings } from '@/lib/backlog'

beforeEach(() => {
  localStorage.clear()
  resetTreeForTests()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function envelope(data: unknown, ok = true) {
  return new Response(
    JSON.stringify(
      ok
        ? { ok: true, data, error: null, warnings: [] }
        : { ok: false, data: null, error: { code: 'write_failed', message: 'disk full' }, warnings: [] },
    ),
    { status: ok ? 200 : 500 },
  )
}

describe('BacklogTree', () => {
  it('renders containers with level names from levels and task links', () => {
    expandTree()
    const data = backlogData()
    const wrapper = mount(BacklogTree, { props: { items: data.items, levels: data.levels } })
    const module = wrapper.find('[data-node="M01"]')
    expect(module.find('.level').text()).toBe('Modul')
    expect(module.find('[data-test="state-counts"]').exists()).toBe(true)
    expect(module.text()).not.toContain('@')
    const step = wrapper.find('[data-node="M01-S01"]')
    expect(step.find('.level').text()).toBe('Step')
    const links = step.findAll('a.task-link')
    expect(links.map((a) => a.attributes('href'))).toEqual([
      '#/r/haifa/backlog/M01-S01-T01',
      '#/r/haifa/backlog/M01-S01-T02',
      '#/r/haifa/backlog/M01-S01-T03',
    ])
    const t3 = wrapper.find('[data-task="M01-S01-T03"]')
    expect(t3.find('[data-state]').text()).toBe('Blokováno')
    expect(wrapper.find('[data-task="M02-S01-T01"]').text()).toContain('bez workflow')
  })

  it('links every container to its graph and marks auto-continue', () => {
    expandTree()
    const data = backlogData()
    const wrapper = mount(BacklogTree, { props: { items: data.items, levels: data.levels } })
    const step = wrapper.find('[data-node="M01-S01"] > .row')
    expect(step.find('[data-test="graph-link"]').attributes('href')).toBe('#/r/haifa/backlog/graph/M01-S01')
    expect(step.find('[data-test="auto-badge"]').text()).toBe('auto')
    expect(step.find('[data-test="auto-badge"]').attributes('title')).toBeUndefined()
    expect(step.find('[data-test="auto-badge"]').attributes('tabindex')).toBe('0')
    expect(wrapper.find('[title]').exists()).toBe(false)
    const module = wrapper.find('[data-node="M02"] > .row')
    expect(module.find('[data-test="graph-link"]').attributes('href')).toBe('#/r/haifa/backlog/graph/M02')
    expect(module.find('[data-test="auto-badge"]').exists()).toBe(false)
  })

  it('uses custom level names', () => {
    const data = backlogData()
    const wrapper = mount(BacklogTree, { props: { items: data.items, levels: ['area', 'story'] } })
    expect(wrapper.find('[data-node="M01"] .level').text()).toBe('area')
  })

  it('names the project level in Czech and shows the title of a code in a tooltip', async () => {
    mergeNames({ M01: { title: 'Core', level: 'project' } })
    const data = backlogData()
    const wrapper = mount(BacklogTree, {
      props: { items: data.items, levels: ['project', 'step', 'task'] },
      attachTo: document.body,
    })
    const row = wrapper.find('[data-node="M01"] > .row')
    expect(row.find('.level').text()).toBe('Projekt')
    row.find('.id').element.parentElement!.dispatchEvent(new MouseEvent('mouseenter'))
    await flushPromises()
    expect(document.body.querySelector('[data-test="tooltip"]')?.textContent?.trim()).toBe('Projekt: Core')
    wrapper.unmount()
    resetNamesForTests()
    document.body.innerHTML = ''
  })

  it('offers the first project in an empty backlog', () => {
    window.location.hash = '#/r/haifa/backlog'
    const wrapper = mount(BacklogTree, { props: { items: [], levels: ['project', 'step', 'task'] } })
    expect(wrapper.get('[data-test="empty-tree"] p').text()).toBe('Backlog je prázdný. Založ první projekt.')
    expect(wrapper.get('[data-test="empty-new-project"]').attributes('href')).toBe('#/r/haifa/backlog/new-container')
    expect(wrapper.find('[data-test="empty-filter"]').exists()).toBe(false)
    const modules = mount(BacklogTree, { props: { items: [], levels: ['module', 'task'] } })
    expect(modules.get('[data-test="empty-tree"] p').text()).toBe('Backlog je prázdný. Založ první modul.')
  })

  it('tells a filter that hides everything apart from an empty backlog', async () => {
    const wrapper = mount(BacklogTree, { props: { items: [], levels: ['project', 'step', 'task'], filtered: true } })
    expect(wrapper.find('[data-test="empty-tree"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="empty-filter"] p').text()).toBe('Filtru nic neodpovídá.')
    await wrapper.get('[data-test="clear-filter"]').trigger('click')
    expect(wrapper.emitted('clear-filter')).toHaveLength(1)
  })

  it('explains the Blokováno badge with a tooltip listing blocked_by', async () => {
    expandTree()
    const data = backlogData()
    const wrapper = mount(BacklogTree, { props: { items: data.items, levels: data.levels }, attachTo: document.body })
    const t3 = wrapper.find('[data-task="M01-S01-T03"]')
    t3.find('[data-test="blocked-chip"]').element.parentElement!.dispatchEvent(new MouseEvent('mouseenter'))
    await flushPromises()
    const tip = document.body.querySelector('[data-test="tooltip"]')
    expect(tip?.textContent?.trim()).toBe('Blokuje:\nM01-S01-T02 – task není hotový')
    expect(wrapper.find('[data-task="M01-S01-T02"] [data-test="blocked-chip"]').exists()).toBe(false)
    wrapper.unmount()
    document.body.innerHTML = ''
  })

  it('starts folded with the projects visible and folds a branch with its arrow', async () => {
    const data = backlogData()
    const wrapper = mount(BacklogTree, { props: { items: data.items, levels: data.levels } })
    expect(wrapper.find('[data-node="M01"]').exists()).toBe(true)
    expect(wrapper.find('[data-node="M02"]').exists()).toBe(true)
    expect(wrapper.find('[data-node="M01-S01"]').exists()).toBe(false)
    expect(wrapper.findAll('a.task-link')).toHaveLength(0)
    const toggle = () => wrapper.find('[data-node="M01"] > .row [data-test="toggle"]')
    expect(toggle().attributes('aria-expanded')).toBe('false')
    await toggle().trigger('click')
    expect(toggle().attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('[data-node="M01-S01"]').exists()).toBe(true)
    expect(wrapper.findAll('a.task-link')).toHaveLength(0)
    await wrapper.find('[data-node="M01-S01"] > .row [data-test="toggle"]').trigger('click')
    expect(wrapper.findAll('a.task-link').map((a) => a.attributes('href'))).toEqual([
      '#/r/haifa/backlog/M01-S01-T01',
      '#/r/haifa/backlog/M01-S01-T02',
      '#/r/haifa/backlog/M01-S01-T03',
    ])
    expect(JSON.parse(localStorage.getItem(TREE_EXPANDED_KEY) ?? '[]')).toEqual(['M01', 'M01-S01'])
    // folding the project hides its tasks; the step stays unfolded inside
    await toggle().trigger('click')
    expect(wrapper.find('[data-task="M01-S01-T01"]').exists()).toBe(false)
    expect(wrapper.find('[data-node="M01-S01"]').exists()).toBe(false)
    await toggle().trigger('click')
    expect(wrapper.find('[data-task="M01-S01-T01"]').exists()).toBe(true)
  })

  it('remembers the folding in the browser', () => {
    localStorage.setItem(TREE_EXPANDED_KEY, JSON.stringify(['M02', 'M02-S01']))
    resetTreeForTests()
    const data = backlogData()
    const wrapper = mount(BacklogTree, { props: { items: data.items, levels: data.levels } })
    expect(wrapper.find('[data-task="M02-S01-T01"]').exists()).toBe(true)
    expect(wrapper.find('[data-node="M01-S01"]').exists()).toBe(false)
  })

  it('folds a project or step on a click anywhere on its row, only Graf opens the graph', async () => {
    window.location.hash = '#/r/haifa/backlog'
    expandTree(['M01'])
    const data = backlogData()
    const wrapper = mount(BacklogTree, { props: { items: data.items, levels: data.levels } })
    const row = wrapper.find('[data-node="M01"] > .row')
    expect(row.attributes('role')).toBeUndefined()
    expect(row.classes()).toContain('clickable')
    await row.find('.title').trigger('click')
    expect(window.location.hash).toBe('#/r/haifa/backlog')
    expect(wrapper.find('[data-node="M01-S01"]').exists()).toBe(false)
    await row.trigger('click')
    expect(wrapper.find('[data-node="M01-S01"]').exists()).toBe(true)
    await wrapper.find('[data-node="M01-S01"] > .row [data-test="state-counts"]').trigger('click')
    expect(wrapper.find('[data-task="M01-S01-T01"]').exists()).toBe(true)
    expect(window.location.hash).toBe('#/r/haifa/backlog')
    // the arrow folds the row once, not twice
    await wrapper.find('[data-node="M01-S01"] > .row [data-test="toggle"]').trigger('click')
    expect(wrapper.find('[data-task="M01-S01-T01"]').exists()).toBe(false)
    const graph = row.find('[data-test="graph-link"]')
    expect(graph.attributes('tabindex')).toBeUndefined()
    await graph.trigger('click')
    expect(wrapper.find('[data-node="M01-S01"]').exists()).toBe(true)
  })

  it('opens the task detail on a click anywhere on a task row', async () => {
    window.location.hash = '#/r/haifa/backlog'
    expandTree()
    const data = backlogData()
    const wrapper = mount(BacklogTree, { props: { items: data.items, levels: data.levels } })
    const row = wrapper.find('[data-task="M01-S01-T03"] > .row')
    expect(row.classes()).toContain('clickable')
    await row.find('.workflow').trigger('click')
    expect(window.location.hash).toBe('#/r/haifa/backlog/M01-S01-T03')
    window.location.hash = '#/r/haifa/backlog'
    await row.trigger('click')
    expect(window.location.hash).toBe('#/r/haifa/backlog/M01-S01-T03')
  })

  it('counts the tasks of a project or step per state after the title and badges', () => {
    expandTree()
    const data = backlogData()
    const wrapper = mount(BacklogTree, { props: { items: data.items, levels: data.levels } })
    const counts = (node: string) =>
      wrapper.findAll(`[data-node="${node}"] > .row [data-test="state-counts"] [data-state]`).map((c) => c.text())
    // kanban order, empty states left out
    expect(counts('M01')).toEqual(['Připraveno 1', 'Blokováno 1', 'Hotovo 1'])
    expect(counts('M01-S01')).toEqual(['Připraveno 1', 'Blokováno 1', 'Hotovo 1'])
    expect(counts('M02')).toEqual(['Bez workflow 1'])
    const step = wrapper.find('[data-node="M01-S01"] > .row')
    const follows = (a: string, b: string) =>
      !!(step.find(a).element.compareDocumentPosition(step.find(b).element) & Node.DOCUMENT_POSITION_FOLLOWING)
    expect(follows('.title', '[data-test="auto-badge"]')).toBe(true)
    expect(follows('[data-test="auto-badge"]', '[data-test="state-counts"]')).toBe(true)
    expect(follows('[data-test="state-counts"]', '[data-test="graph-link"]')).toBe(true)
    expect(wrapper.find('[data-test="progress"]').exists()).toBe(false)
  })

  it('counts every task of a container, done ones too, when the tree hides them', () => {
    expandTree()
    const data = backlogData()
    const wrapper = mount(BacklogTree, { props: { items: pruneDone(data.items), levels: data.levels } })
    expect(wrapper.find('[data-task="M01-S01-T01"]').exists()).toBe(false)
    expect(
      wrapper.findAll('[data-node="M01-S01"] > .row [data-test="state-counts"] [data-state]').map((c) => c.text()),
    ).toEqual(['Připraveno 1', 'Blokováno 1', 'Hotovo 1'])
  })
  it('opens the Nastavení panel of a project or step under its row, with the switches and the form', async () => {
    expandTree(['M01'])
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => envelope(containerDetail()))
    vi.stubGlobal('fetch', fetchMock)
    const data = backlogData()
    const wrapper = mount(BacklogTree, { props: { items: data.items, levels: data.levels, workflows: ['plan'] } })
    const step = () => wrapper.find('[data-node="M01-S01"] > .row')
    expect(wrapper.find('[data-test="settings-panel"]').exists()).toBe(false)
    await step().get('[data-test="settings"]').trigger('click')
    await flushPromises()
    // the button neither folds the row nor opens the graph
    expect(wrapper.find('[data-task="M01-S01-T01"]').exists()).toBe(false)
    expect(fetchMock.mock.calls[0]![0]).toBe('/api/repos/haifa/backlog/containers/M01-S01')
    const panel = wrapper.get('[data-node="M01-S01"] > [data-test="settings-panel"]')
    expect(panel.get('[data-test="auto-on"]').attributes('aria-pressed')).toBe('true')
    expect(panel.get('[data-test="auto-effective"]').text()).toContain('zapnuto')
    expect(panel.get('[data-test="merge-inherit"]').attributes('aria-pressed')).toBe('true')
    expect(panel.get('[data-test="merge-effective"]').text()).toContain('vypnuto')
    expect(step().get('[data-test="settings"]').attributes('aria-expanded')).toBe('true')
    // the whole form with inherited values; auto-continue only once, in its switch
    const form = panel.get('[data-test="container-settings"]')
    expect(form.get('[data-test="value-workflow"]').text()).toContain('plan')
    expect(form.get('[data-setting="writes"] [data-test="origin"]').text()).toContain('Modul M01')
    expect(form.find('[data-setting="auto_continue"]').exists()).toBe(false)
    expect(panel.findAll('[data-test="auto-toggle"]')).toHaveLength(1)
    await step().get('[data-test="settings"]').trigger('click')
    expect(wrapper.find('[data-test="settings-panel"]').exists()).toBe(false)
  })

  it('saves the settings through the API and asks for the tree again', async () => {
    expandTree(['M01'])
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        const detail = containerDetail({ own: { workflow: 'plan', writes: ['docs/'] } }).container
        detail.effective.writes = { value: ['docs/'], origin: detail.effective.workflow!.origin }
        return envelope({ action: 'edit', changed: true, path: 'x', container: detail, issues: [] })
      }
      return envelope(url.endsWith('/M01-S01') ? containerDetail() : null)
    })
    vi.stubGlobal('fetch', fetchMock)
    const data = backlogData()
    const wrapper = mount(BacklogTree, { props: { items: data.items, levels: data.levels } })
    await wrapper.get('[data-node="M01-S01"] > .row [data-test="settings"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="inherit-writes"]').setValue(false)
    await wrapper.get('[data-test="edit-writes"]').setValue('docs/')
    await wrapper.get('[data-test="container-settings"]').trigger('submit')
    await flushPromises()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')!
    expect(post[0]).toBe('/api/repos/haifa/backlog/containers/M01-S01/edit')
    expect(post[1]?.body).toBe('{"writes":["docs/"]}')
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.get('[data-test="value-writes"]').text()).toContain('docs/')
    expect(wrapper.get('[data-setting="writes"]').attributes('data-source')).toBe('own')
  })

  it('shows a save that failed and a spinner while it runs', async () => {
    expandTree(['M01'])
    let answer: (r: Response) => void = () => {}
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') return new Promise<Response>((resolve) => (answer = resolve))
      return envelope(containerDetail())
    }))
    const data = backlogData()
    const wrapper = mount(BacklogTree, { props: { items: data.items, levels: data.levels } })
    await wrapper.get('[data-node="M01-S01"] > .row [data-test="settings"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="settings-title"]').setValue('Jiný')
    await wrapper.get('[data-test="container-settings"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-test="settings-save"]').attributes('aria-busy')).toBe('true')
    answer(envelope(null, false))
    await flushPromises()
    expect(wrapper.get('[data-test="settings-save"]').attributes('aria-busy')).toBeUndefined()
    expect(wrapper.get('[data-test="container-settings"]').text()).toContain('disk full')
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  it('reports settings that could not be loaded', async () => {
    expandTree(['M01'])
    vi.stubGlobal('fetch', vi.fn(async () => envelope(null, false)))
    const data = backlogData()
    const wrapper = mount(BacklogTree, { props: { items: data.items, levels: data.levels } })
    await wrapper.get('[data-node="M01"] > .row [data-test="settings"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-node="M01"] > [data-test="settings-panel"] [data-test="settings-error"]').text()).toContain(
      'disk full',
    )
  })

  it('writes a switch and asks for the tree again', async () => {
    expandTree(['M01'])
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) =>
      url.endsWith('/auto-merge')
        ? envelope({ changed: true, id: 'M01-S01', level: 'step', path: 'x', mode: 'on' })
        : envelope(containerDetail()),
    )
    vi.stubGlobal('fetch', fetchMock)
    const data = backlogData()
    const wrapper = mount(BacklogTree, { props: { items: data.items, levels: data.levels } })
    await wrapper.get('[data-node="M01-S01"] > .row [data-test="settings"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-node="M01-S01"] > [data-test="settings-panel"] [data-test="merge-on"]').trigger('click')
    await flushPromises()
    const [url, init] = fetchMock.mock.calls.find(([, i]) => i?.method === 'POST')!
    expect(url).toBe('/api/repos/haifa/backlog/containers/M01-S01/auto-merge')
    expect(JSON.parse(String(init?.body))).toEqual({ mode: 'on' })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('reports a switch that could not be written', async () => {
    expandTree(['M01'])
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === 'POST' ? envelope(null, false) : envelope(containerDetail({ id: 'M01', parent: null })),
    ))
    const data = backlogData()
    const wrapper = mount(BacklogTree, { props: { items: data.items, levels: data.levels } })
    await wrapper.get('[data-node="M01"] > .row [data-test="settings"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-node="M01"] > [data-test="settings-panel"] [data-test="auto-off"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="switches-error"]').text()).toBe('disk full')
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  it('unfolds the tree to a container revealed from the graph page and opens its settings', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => envelope(containerDetail())))
    revealSettings('M01-S01')
    const data = backlogData()
    const wrapper = mount(BacklogTree, { props: { items: data.items, levels: data.levels } })
    await flushPromises()
    expect(wrapper.find('[data-node="M01-S01"] > [data-test="settings-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-task="M01-S01-T01"]').exists()).toBe(false)
    expect(JSON.parse(localStorage.getItem(TREE_EXPANDED_KEY) ?? '[]')).toEqual(['M01'])
  })
})
