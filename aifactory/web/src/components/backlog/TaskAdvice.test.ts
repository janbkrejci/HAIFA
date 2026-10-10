import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import TaskAdvice from './TaskAdvice.vue'
import TaskForm from './TaskForm.vue'
import { chooseOption, selectLabels } from '@/test/select'

const api = vi.hoisted(() => ({ postApi: vi.fn(), getApi: vi.fn() }))
vi.mock('@/lib/api', () => api)
const proposal = {
  title: 'Improved task', body: 'Acceptance criteria', writes: ['src/'],
  depends_on: ['P01-S01-T02'], related: [], workflow: 'plan', reason: 'Clear scope',
  parameters: { auto_merge: false, test_timeout: 120 },
  usage: { tokens: 50, cost_usd: 0.0123 },
}
beforeEach(() => {
  localStorage.clear()
  api.postApi.mockReset().mockResolvedValue({ job_id: 'job' })
  api.getApi.mockReset().mockImplementation(async (path: string) => path.endsWith('/options')
    ? options
    : { state: 'succeeded', recommendation: proposal })
})
const options = {
  default: { harness: 'claude', model: 'sonnet' },
  harnesses: [
    { name: 'claude', default_model: 'sonnet', models: ['sonnet', 'opus'] },
    { name: 'codex', default_model: 'gpt-5', models: ['gpt-5', 'gpt-5-mini'] },
  ],
}
afterEach(() => { vi.useRealTimers(); document.body.innerHTML = '' })

describe('TaskAdvice', () => {
  it('previews, applies explicitly, repeats and remembers the selection with cost history', async () => {
    const wrapper = mount(TaskAdvice, { props: { draft: { title: 'Original' } } })
    await flushPromises()
    await wrapper.get('[data-test="task-advice-start"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('result')).toBeUndefined()
    expect(wrapper.text()).toContain('$0.0123 USD')
    expect(api.postApi).toHaveBeenCalledWith('/backlog/task-advice', {
      draft: { title: 'Original' },
    }, expect.any(AbortSignal))
    expect(wrapper.get('[data-test="advice-harness"]').text()).toContain('Systémový default (claude · sonnet)')
    expect(wrapper.find('[data-test="advice-model"]').exists()).toBe(false)
    await wrapper.get('[data-test="task-advice-apply"]').trigger('click')
    expect(wrapper.emitted('result')?.[0]).toEqual([proposal])
    await wrapper.get('[data-test="task-advice-start"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-test="task-advice-cost"]')).toHaveLength(2)
    await wrapper.setProps({ draft: { title: 'Changed' } })
    expect(wrapper.get('[data-test="task-advice-apply"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('sends a chosen harness and model and remembers them', async () => {
    window.location.hash = '#/r/haifa/backlog/new'
    const wrapper = mount(TaskAdvice, { props: { draft: { title: 'Original' } } })
    await flushPromises()
    await chooseOption(wrapper, '[data-test="advice-harness"]', 'codex')
    expect(await selectLabels(wrapper, '[data-test="advice-model"]')).toEqual(['Default harnessu (gpt-5)', 'gpt-5', 'gpt-5-mini'])
    await chooseOption(wrapper, '[data-test="advice-model"]', 'gpt-5-mini')
    await wrapper.get('[data-test="task-advice-start"]').trigger('click')
    await flushPromises()
    expect(api.postApi).toHaveBeenCalledWith('/backlog/task-advice', {
      draft: { title: 'Original' }, harness: 'codex', model: 'gpt-5-mini',
    }, expect.any(AbortSignal))
    expect(JSON.parse(localStorage.getItem('haifa.task-advice.choice.haifa') ?? '')).toEqual({ harness: 'codex', model: 'gpt-5-mini' })
    wrapper.unmount()
  })

  it('resets the model when the harness changes', async () => {
    const wrapper = mount(TaskAdvice, { props: { draft: { title: 'Original' } } })
    await flushPromises()
    await chooseOption(wrapper, '[data-test="advice-harness"]', 'codex')
    await chooseOption(wrapper, '[data-test="advice-model"]', 'gpt-5')
    await chooseOption(wrapper, '[data-test="advice-harness"]', 'claude')
    expect(wrapper.get('[data-test="advice-model"]').text()).toContain('Default harnessu (sonnet)')
    wrapper.unmount()
  })

  it('explains missing harnesses instead of an empty selection', async () => {
    window.location.hash = '#/r/haifa/backlog/new'
    api.getApi.mockResolvedValue({ default: null, harnesses: [] })
    const wrapper = mount(TaskAdvice, { props: { draft: { title: 'Original' } } })
    await flushPromises()
    expect(wrapper.get('[data-test="advice-no-agents"]').text()).toContain('povolený harness')
    expect(wrapper.find('[data-test="advice-harness"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="task-advice-start"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('restores a stored choice that is still offered', async () => {
    window.location.hash = '#/r/haifa/backlog/new'
    localStorage.setItem('haifa.task-advice.choice.haifa', JSON.stringify({ harness: 'codex', model: 'gpt-5-mini' }))
    const wrapper = mount(TaskAdvice, { props: { draft: { title: 'Original' } } })
    await flushPromises()
    expect(wrapper.get('[data-test="advice-harness"]').text()).toContain('codex')
    expect(wrapper.get('[data-test="advice-model"]').text()).toContain('gpt-5-mini')
    wrapper.unmount()
  })

  it('drops a stored choice whose harness is no longer offered', async () => {
    window.location.hash = '#/r/haifa/backlog/new'
    localStorage.setItem('haifa.task-advice.choice.haifa', JSON.stringify({ harness: 'pi', model: 'x/y' }))
    const wrapper = mount(TaskAdvice, { props: { draft: { title: 'Original' } } })
    await flushPromises()
    expect(wrapper.get('[data-test="advice-harness"]').text()).toContain('Systémový default')
    expect(wrapper.find('[data-test="advice-model"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows unavailable cost instead of zero for providers that do not report it', async () => {
    api.getApi.mockImplementation(async (path: string) => path.endsWith('/options')
      ? options
      : { state: 'succeeded', recommendation: { ...proposal, usage: { tokens: 50, cost_usd: null } } })
    const wrapper = mount(TaskAdvice, { props: { draft: { title: 'Original' } } })
    await flushPromises()
    await wrapper.get('[data-test="task-advice-start"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Provider cenu nevykázal')
    expect(wrapper.text()).not.toContain('$0.0000')
    wrapper.unmount()
  })

  it('applies the proposal to a new task and submits its parameters and relationships', async () => {
    const wrapper = mount(TaskForm, { props: {
      mode: 'add', steps: [{ id: 'P01-S01', title: 'Step', path: 'backlog/P01/S01', project: 'P01' }], workflows: ['plan'],
      busy: false, error: null, initialTitle: 'Original',
    } })
    await flushPromises()
    await wrapper.get('[data-test="task-advice-start"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="task-advice-apply"]').trigger('click')
    await chooseOption(wrapper, '[data-test="parameter-auto_continue"]', 'true')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({
      step: 'P01-S01', title: proposal.title, body: proposal.body,
      writes: proposal.writes, depends_on: proposal.depends_on,
      workflow: 'plan', parameters: { ...proposal.parameters, auto_continue: true },
    })
    wrapper.unmount()
  })
})
