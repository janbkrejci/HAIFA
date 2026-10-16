import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import TaskDocuments from './TaskDocuments.vue'
import type { TaskDocument } from '@/lib/backlog'

const api = vi.hoisted(() => ({ postApi: vi.fn(), getApi: vi.fn() }))
vi.mock('@/lib/api', () => api)

afterEach(() => {
  api.getApi.mockReset()
  document.body.innerHTML = ''
})

function doc(kind: TaskDocument['kind'], content: string | null, extra: Partial<TaskDocument> = {}): TaskDocument {
  const label = { backlog: 'Položka backlogu', spec: 'Spec', doc: 'Dokumentace' }[kind]
  return {
    kind,
    label,
    path: `factory/${kind}/P/S/T1-x.md`,
    exists: content !== null,
    content,
    problem: null,
    ...extra,
  }
}

const BACKLOG = '---\nid: T1\ntitle: X\n---\n\n## Zadání\nUdělej to.\n'

describe('TaskDocuments', () => {
  it('opens the task body as the first tab, rendered without a source tab', async () => {
    api.getApi.mockResolvedValue({ task_id: 'T1', documents: [doc('spec', '# Plán')] })
    const wrapper = mount(TaskDocuments, { props: { taskId: 'T1', body: '## Cíl\n\nUdělat **to**.' } })
    await flushPromises()
    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs.map((t) => t.text())).toEqual(['Zadání', 'Spec'])
    expect(wrapper.get('[data-test="doc-task"]').attributes('aria-selected')).toBe('true')
    const body = wrapper.get('.mdview[data-test="body"]')
    expect(body.find('h2').text()).toBe('Cíl')
    expect(body.find('strong').text()).toBe('to')
    expect(body.find('[data-test="md-tab-source"]').exists()).toBe(false)
    expect(body.find('[data-test="md-source"]').exists()).toBe(false)

    await wrapper.get('[data-test="doc-spec"]').trigger('click')
    expect(wrapper.find('[data-test="body"]').exists()).toBe(false)
    await wrapper.get('[data-test="doc-task"]').trigger('click')
    expect(wrapper.find('[data-test="body"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('shows an empty task body', async () => {
    api.getApi.mockResolvedValue({ task_id: 'T1', documents: [] })
    const wrapper = mount(TaskDocuments, { props: { taskId: 'T1', body: '  ' } })
    await flushPromises()
    expect(wrapper.get('[data-test="md-empty"]').text()).toBe('Zadání je prázdné.')
    wrapper.unmount()
  })

  it('lists backlog item, spec and doc and renders the chosen one', async () => {
    api.getApi.mockResolvedValue({
      task_id: 'T1',
      documents: [doc('backlog', BACKLOG), doc('spec', '# Plán\n\nKroky'), doc('doc', '# Popis')],
    })
    const wrapper = mount(TaskDocuments, { props: { taskId: 'T1', body: '## Cíl\n\nUdělat **to**.' } })
    await flushPromises()
    expect(api.getApi).toHaveBeenCalledWith('/backlog/tasks/T1/documents')
    expect(wrapper.findAll('[data-test="doc-missing"]')).toHaveLength(0)
    expect(wrapper.find('[data-test="doc-content"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="body"]').exists()).toBe(true)

    await wrapper.get('[data-test="doc-spec"]').trigger('click')
    expect(wrapper.get('[data-test="doc-path"]').text()).toBe('factory/spec/P/S/T1-x.md')
    expect(wrapper.get('[data-test="md-preview"] h1').text()).toBe('Plán')

    await wrapper.get('[data-test="doc-backlog"]').trigger('click')
    const preview = wrapper.get('[data-test="md-preview"]')
    expect(preview.find('pre').text()).toContain('id: T1')
    expect(preview.find('h2').text()).toBe('Zadání')

    await wrapper.get('[data-test="doc-backlog"]').trigger('click')
    expect(wrapper.find('[data-test="doc-content"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('marks a missing spec and doc and does not open them', async () => {
    api.getApi.mockResolvedValue({
      task_id: 'T1',
      documents: [doc('backlog', BACKLOG), doc('spec', null), doc('doc', null)],
    })
    const wrapper = mount(TaskDocuments, { props: { taskId: 'T1', body: '## Cíl\n\nUdělat **to**.' } })
    await flushPromises()
    const spec = wrapper.get('[data-test="doc-spec"]')
    expect(spec.attributes('disabled')).toBeDefined()
    expect(spec.text()).toContain('chybí')
    expect(wrapper.findAll('[data-test="doc-missing"]')).toHaveLength(2)
    await spec.trigger('click')
    expect(wrapper.find('[data-doc]').exists()).toBe(false)
    expect(wrapper.find('[data-test="body"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('shows why content of an existing document is not shown', async () => {
    api.getApi.mockResolvedValue({
      task_id: 'T1',
      documents: [doc('backlog', null, { exists: true, problem: 'file too large to show' })],
    })
    const wrapper = mount(TaskDocuments, { props: { taskId: 'T1', body: '## Cíl\n\nUdělat **to**.' } })
    await flushPromises()
    await wrapper.get('[data-test="doc-backlog"]').trigger('click')
    expect(wrapper.get('[data-test="doc-problem"]').text()).toContain('file too large to show')
    wrapper.unmount()
  })

  it('shows a load error and reloads for another task', async () => {
    api.getApi.mockRejectedValueOnce(new Error('offline'))
    const wrapper = mount(TaskDocuments, { props: { taskId: 'T1', body: '## Cíl\n\nUdělat **to**.' } })
    await flushPromises()
    expect(wrapper.get('[data-test="docs-error"]').text()).toContain('offline')
    expect(wrapper.find('[data-test="body"]').exists()).toBe(true)
    api.getApi.mockResolvedValue({ task_id: 'T2', documents: [doc('backlog', BACKLOG)] })
    await wrapper.setProps({ taskId: 'T2' })
    await flushPromises()
    expect(api.getApi).toHaveBeenLastCalledWith('/backlog/tasks/T2/documents')
    expect(wrapper.find('[data-test="docs-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="doc-backlog"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
