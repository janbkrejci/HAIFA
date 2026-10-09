import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import TaskAdvice from './TaskAdvice.vue'
import TaskForm from './TaskForm.vue'
import { chooseOption } from '@/test/select'

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
    ? { agents: [{ name: 'planner', provider: 'claude', model: 'sonnet' }] }
    : { state: 'succeeded', recommendation: proposal })
})
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
      draft: { title: 'Original' }, agent: 'planner',
    }, expect.any(AbortSignal))
    expect(localStorage.getItem('haifa.task-advice.agent.haifa')).toBe('planner')
    await wrapper.get('[data-test="task-advice-apply"]').trigger('click')
    expect(wrapper.emitted('result')?.[0]).toEqual([proposal])
    await wrapper.get('[data-test="task-advice-start"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-test="task-advice-cost"]')).toHaveLength(2)
    await wrapper.setProps({ draft: { title: 'Changed' } })
    expect(wrapper.get('[data-test="task-advice-apply"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('explains an empty roster instead of an empty selection', async () => {
    window.location.hash = '#/r/haifa/backlog/new'
    api.getApi.mockResolvedValue({ agents: [] })
    const wrapper = mount(TaskAdvice, { props: { draft: { title: 'Original' } } })
    await flushPromises()
    const note = wrapper.get('[data-test="advice-no-agents"]')
    expect(note.text()).toContain('roster je prázdný')
    expect(note.get('a').attributes('href')).toBe('#/r/haifa/factory')
    expect(wrapper.find('[data-test="advice-agent"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="task-advice-start"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('restores the last configured selection', async () => {
    localStorage.setItem('haifa.task-advice.agent.haifa', 'coder')
    api.getApi.mockResolvedValue({ agents: [
      { name: 'planner', provider: 'claude', model: 'sonnet' },
      { name: 'coder', provider: 'codex', model: 'gpt-5' },
    ] })
    const wrapper = mount(TaskAdvice, { props: { draft: { title: 'Original' } } })
    await flushPromises()
    expect(wrapper.get('[data-test="advice-agent"]').text()).toContain('codex')
    wrapper.unmount()
  })

  it('shows unavailable cost instead of zero for providers that do not report it', async () => {
    api.getApi.mockImplementation(async (path: string) => path.endsWith('/options')
      ? { agents: [{ name: 'planner', provider: 'codex', model: 'gpt-5' }] }
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
