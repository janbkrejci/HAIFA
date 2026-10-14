import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ImproveButton from './ImproveButton.vue'

const api = vi.hoisted(() => ({ postApi: vi.fn(), getApi: vi.fn() }))
vi.mock('@/lib/api', () => api)
const proposal = {
  title: 'Improved task', body: 'Acceptance criteria', writes: ['src/'],
  depends_on: ['P01-S01-T02'], related: [], workflow: 'plan', reason: 'Clear scope',
  parameters: { auto_merge: false, test_timeout: 120 },
  usage: { tokens: 50, cost_usd: 0.0123 },
}
const advisor = { harness: 'codex', model: 'gpt-5.5', thinking: 'high' }
beforeEach(() => {
  api.postApi.mockReset().mockResolvedValue({ job_id: 'job', state: 'queued', advisor })
  api.getApi.mockReset().mockResolvedValue({ state: 'succeeded', recommendation: proposal, advisor })
})
afterEach(() => { vi.useRealTimers(); document.body.innerHTML = '' })

describe('ImproveButton', () => {
  it('starts without a harness choice and emits the proposal with its note', async () => {
    const wrapper = mount(ImproveButton, { props: { draft: { title: 'Original' }, taskId: 'P01-S01-T01' } })
    expect(wrapper.get('[data-test="improve"]').text()).toContain('Vylepšit agentem')
    await wrapper.get('[data-test="improve"]').trigger('click')
    await flushPromises()
    expect(api.postApi).toHaveBeenCalledWith('/backlog/task-advice', {
      task_id: 'P01-S01-T01', draft: { title: 'Original' },
    }, expect.any(AbortSignal))
    expect(wrapper.emitted('result')?.[0]).toEqual([proposal])
    expect(wrapper.emitted('busy')).toEqual([[true], [false]])
    const note = wrapper.get('[data-test="improve-note"]')
    expect(note.text()).toContain('Clear scope')
    expect(wrapper.get('[data-test="improve-advisor"]').text()).toContain('codex · gpt-5.5 · high')
    expect(wrapper.get('[data-test="improve-cost"]').text()).toContain('$0.0123 USD')
    await wrapper.get('[data-test="improve-note-close"]').trigger('click')
    expect(wrapper.find('[data-test="improve-note"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows a spinner while the agent works', async () => {
    api.getApi.mockResolvedValue({ state: 'running', recommendation: null })
    vi.useFakeTimers()
    const wrapper = mount(ImproveButton, { props: { draft: { title: 'Original' } } })
    await wrapper.get('[data-test="improve"]').trigger('click')
    await flushPromises()
    const button = wrapper.get('[data-test="improve"]')
    expect(button.text()).toContain('Agent vylepšuje')
    expect(button.attributes('aria-busy')).toBe('true')
    expect(button.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('reports a failed job', async () => {
    api.getApi.mockResolvedValue({ state: 'failed', recommendation: null, error: 'Agent selhal.' })
    const wrapper = mount(ImproveButton, { props: { draft: { title: 'Original' } } })
    await wrapper.get('[data-test="improve"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="improve-error"]').text()).toBe('Agent selhal.')
    expect(wrapper.emitted('result')).toBeUndefined()
    wrapper.unmount()
  })

  it('shows unavailable cost instead of zero', async () => {
    api.getApi.mockResolvedValue({ state: 'succeeded', recommendation: { ...proposal, usage: { tokens: 50, cost_usd: null } } })
    const wrapper = mount(ImproveButton, { props: { draft: { title: 'Original' } } })
    await wrapper.get('[data-test="improve"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Provider cenu nevykázal')
    expect(wrapper.text()).not.toContain('$0.0000')
    wrapper.unmount()
  })

  it('starts on mount with autostart, but not when blocked', async () => {
    const auto = mount(ImproveButton, { props: { draft: { title: 'Original' }, autostart: true } })
    await flushPromises()
    expect(api.postApi).toHaveBeenCalledTimes(1)
    expect(auto.emitted('result')).toHaveLength(1)
    auto.unmount()
    const blocked = mount(ImproveButton, { props: { draft: { title: '' }, autostart: true, blocker: 'Vyplň titulek.' } })
    await flushPromises()
    expect(api.postApi).toHaveBeenCalledTimes(1)
    expect(blocked.get('[data-test="improve"]').attributes('disabled')).toBeDefined()
    blocked.unmount()
  })

  it('drops the job when the draft changes while it runs', async () => {
    api.getApi.mockResolvedValue({ state: 'running', recommendation: null })
    vi.useFakeTimers()
    const wrapper = mount(ImproveButton, { props: { draft: { title: 'Original' } } })
    await wrapper.get('[data-test="improve"]').trigger('click')
    await flushPromises()
    await wrapper.setProps({ draft: { title: 'Changed' } })
    await flushPromises()
    expect(wrapper.get('[data-test="improve-error"]').text()).toContain('Zadání se změnilo')
    expect(wrapper.get('[data-test="improve"]').attributes('aria-busy')).toBeUndefined()
    api.getApi.mockResolvedValue({ state: 'succeeded', recommendation: proposal })
    await vi.advanceTimersByTimeAsync(2000)
    expect(wrapper.emitted('result')).toBeUndefined()
    wrapper.unmount()
  })
})
