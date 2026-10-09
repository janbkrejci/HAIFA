import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import WorkflowAdvice from './WorkflowAdvice.vue'
import TaskForm from './TaskForm.vue'
import { backlogData } from '@/test/backlogFixtures'
import { chooseOption } from '@/test/select'

const api = vi.hoisted(() => ({ postApi: vi.fn(), getApi: vi.fn() }))
vi.mock('@/lib/api', () => api)
const recommendation = {
  workflow_name: 'research', decision: 'new', reason: 'Analysis is sufficient.',
  workflow_yaml: '<script>alert(1)</script>', outline: [{ name: 'plan' }],
}
beforeEach(() => {
  window.location.hash = '#/r/repo/backlog/new'
  api.postApi.mockReset().mockResolvedValue({ job_id: 'job' })
  api.getApi.mockReset().mockResolvedValue({ state: 'succeeded', recommendation })
})
afterEach(() => { vi.useRealTimers(); document.body.innerHTML = '' })

describe('workflow advice', () => {
  it.each(['task', 'repo'])('ignores a late polling result after a %s switch', async (scope) => {
    let resolve!: (value: unknown) => void
    api.getApi.mockImplementation(() => new Promise((done) => { resolve = done }))
    const wrapper = mount(WorkflowAdvice, { props: { draft: { title: 'Draft' }, taskId: 'T01' } })
    await wrapper.find('button').trigger('click')
    await flushPromises()
    const signal = api.getApi.mock.calls[0]?.[1] as AbortSignal
    if (scope === 'task') await wrapper.setProps({ taskId: 'T02' })
    else {
      window.location.hash = '#/r/other/backlog/T01'
      window.dispatchEvent(new HashChangeEvent('hashchange'))
    }
    resolve({ state: 'succeeded', recommendation })
    await flushPromises()
    expect(signal.aborted).toBe(true)
    expect(wrapper.emitted('result')).toBeUndefined()
    expect(wrapper.find('pre').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows explained result and renders YAML as text', async () => {
    const wrapper = mount(WorkflowAdvice, { props: { draft: { title: 'Draft', step: 'S01' } } })
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('result')?.[0]).toEqual([recommendation, 'job'])
    expect(wrapper.find('pre').text()).toBe(recommendation.workflow_yaml)
    expect(wrapper.find('script').exists()).toBe(false)
    wrapper.unmount()
  })
  it('shows the cost of every proposal like the task advice', async () => {
    api.getApi.mockResolvedValueOnce({ state: 'succeeded', recommendation, usage: { tokens: 42, cost_usd: 0.0105 } })
    api.getApi.mockResolvedValueOnce({ state: 'failed', recommendation: null, error: 'boom', usage: null })
    const wrapper = mount(WorkflowAdvice, { props: { draft: { title: 'Draft', step: 'S01' } } })
    await wrapper.find('button').trigger('click')
    await flushPromises()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    const costs = wrapper.findAll('[data-test="workflow-advice-cost"]').map((c) => c.text())
    expect(costs).toEqual([
      'Návrh 1: $0.0105 USD · 42 tokenů (vykázané providerem)',
      'Návrh 2: Provider náklady nevykázal.',
    ])
    wrapper.unmount()
  })

  it('ignores late replies when inputs change', async () => {
    let resolve!: (value: unknown) => void
    api.postApi.mockImplementation(() => new Promise((done) => { resolve = done }))
    const wrapper = mount(WorkflowAdvice, { props: { draft: { title: 'Draft' } } })
    await wrapper.find('button').trigger('click')
    expect(wrapper.text()).toContain('Agent vybírá workflow')
    await wrapper.setProps({ draft: { title: 'Changed' } })
    resolve({ job_id: 'late' })
    await flushPromises()
    expect(api.getApi).not.toHaveBeenCalled()
    expect(wrapper.emitted('result')).toBeUndefined()
    expect(wrapper.text()).toContain('Zadání se změnilo')
    wrapper.unmount()
  })
  it('cancels polling and requests on unmount', async () => {
    vi.useFakeTimers()
    api.getApi.mockResolvedValue({ state: 'running' })
    const wrapper = mount(WorkflowAdvice, { props: { draft: { title: 'Draft' } } })
    await wrapper.find('button').trigger('click')
    await flushPromises()
    const signal = api.getApi.mock.calls[0]?.[1] as AbortSignal
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(2000)
    expect(api.getApi).toHaveBeenCalledTimes(1)
    expect(signal.aborted).toBe(true)
  })
  it('offers retry after a failed job', async () => {
    api.getApi.mockResolvedValueOnce({ state: 'failed', error: 'Planner unavailable' })
    const wrapper = mount(WorkflowAdvice, { props: { draft: { title: 'Draft' } } })
    await wrapper.find('button').trigger('click'); await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toBe('Planner unavailable')
    await wrapper.find('button').trigger('click'); await flushPromises()
    expect(wrapper.emitted('result')).toHaveLength(1)
    wrapper.unmount()
  })
  it('submits the current new draft and attaches the saved recommendation', async () => {
    const data = backlogData()
    const wrapper = mount(TaskForm, { props: { mode: 'add', steps: data.steps, workflows: data.workflows, busy: false, error: null } })
    await wrapper.find('[data-test="title"]').setValue('Unsaved title')
    await wrapper.find('[data-test="body"]').setValue('Unsaved instructions')
    await wrapper.find('[data-test="workflow-advice"] button').trigger('click')
    await flushPromises()
    expect(api.postApi.mock.calls[0]?.[1].draft).toMatchObject({ title: 'Unsaved title', body: 'Unsaved instructions' })
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ workflow: 'research', workflow_advice_id: 'job' })
    await chooseOption(wrapper, '[data-test="workflow"]', data.workflows[0]!)
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[1]?.[0]).not.toHaveProperty('workflow_advice_id')
    wrapper.unmount()
  })
})
